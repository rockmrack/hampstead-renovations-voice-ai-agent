"""
WhatsApp message handling routes.
Handles incoming text messages and voice notes via 360dialog webhook.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from config import settings
from models.conversation import WhatsAppMessage
from services.claude_service import claude_service
from services.conversation_service import conversation_service
from services.deepgram_service import deepgram_service
from services.elevenlabs_service import elevenlabs_service
from services.hubspot_service import hubspot_service
from services.notification_service import notification_service
from services.whatsapp_service import whatsapp_service

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """
    Handle incoming WhatsApp webhooks from 360dialog.
    Processes text messages and voice notes.
    """
    body = await request.json()

    # Handle webhook verification challenge
    if body.get("hub.mode") == "subscribe":
        challenge = body.get("hub.challenge", "")
        logger.info("webhook_verification", challenge=challenge)
        return {"challenge": int(challenge) if challenge else 0}

    # Extract messages from webhook payload
    messages = body.get("messages", [])
    contacts = body.get("contacts", [])

    if not messages:
        logger.debug("webhook_no_messages")
        return {"status": "no_messages"}

    for message in messages:
        try:
            # Parse incoming message
            msg = WhatsAppMessage(
                message_id=message.get("id"),
                from_number=message.get("from"),
                message_type=message.get("type"),
                text=message.get("text", {}).get("body") if message.get("type") == "text" else None,
                audio_id=message.get("audio", {}).get("id") if message.get("type") == "audio" else None,
                contact_name=contacts[0].get("profile", {}).get("name") if contacts else None,
                timestamp=message.get("timestamp"),
            )

            logger.info(
                "whatsapp_message_received",
                message_id=msg.message_id,
                from_number=msg.from_number,
                message_type=msg.message_type,
            )

            # Process message in background to return quickly
            background_tasks.add_task(process_whatsapp_message, msg)

        except Exception as e:
            logger.error("whatsapp_message_parse_error", error=str(e), message=message)
            continue

    return {"status": "received", "count": len(messages)}


async def process_whatsapp_message(msg: WhatsAppMessage) -> None:
    """
    Process incoming WhatsApp message and send response.
    Handles both text and voice note messages.
    """
    try:
        logger.info(
            "processing_whatsapp_message",
            message_id=msg.message_id,
            message_type=msg.message_type,
        )

        # Get conversation history
        history = await conversation_service.get_conversation_history(msg.from_number)

        # Process based on message type
        if msg.message_type == "text":
            response = await handle_text_message(msg, history)
            await whatsapp_service.send_text_message(msg.from_number, response)

        elif msg.message_type == "audio":
            response = await handle_voice_note(msg, history)
            # Generate voice note response
            audio_url = await elevenlabs_service.generate_voice_note(response)
            await whatsapp_service.send_audio_message(msg.from_number, audio_url)

        else:
            # Unsupported message type - send text acknowledgment
            response = (
                "Thanks for your message! I can best help you with text messages "
                "or voice notes. How can I help you today?"
            )
            await whatsapp_service.send_text_message(msg.from_number, response)

        # Log conversation in CRM and local storage
        await conversation_service.log_message(
            phone=msg.from_number,
            direction="inbound",
            content=msg.text or "[Voice Note]",
            response=response,
            channel="whatsapp",
        )

        # Extract and update lead qualification
        await update_lead_qualification(msg.from_number, msg.text or "", response, history)

        logger.info(
            "whatsapp_message_processed",
            message_id=msg.message_id,
            response_length=len(response),
        )

    except Exception as e:
        logger.error(
            "whatsapp_message_processing_error",
            message_id=msg.message_id,
            error=str(e),
        )
        # Send fallback response
        await send_fallback_response(msg.from_number)


async def handle_text_message(msg: WhatsAppMessage, history: str) -> str:
    """Generate AI response to text message."""
    try:
        # Build prompt context
        context = {
            "phone_number": msg.from_number,
            "customer_name": msg.contact_name or "",
            "message": msg.text,
            "conversation_history": history,
            "time_of_day": get_time_of_day(),
            "is_existing_contact": await hubspot_service.contact_exists(msg.from_number),
        }

        # Generate response using Claude
        response = await claude_service.generate_whatsapp_response(context)

        # Analyze sentiment for escalation
        if settings.enable_sentiment_analysis:
            sentiment = await claude_service.analyze_sentiment(f"Customer: {msg.text}\nAgent: {response}")
            if sentiment.get("escalation_assessment", {}).get("requires_escalation"):
                await notification_service.notify_escalation(
                    phone=msg.from_number,
                    reason=sentiment.get("escalation_assessment", {}).get("escalation_reason"),
                    conversation=f"Customer: {msg.text}\nAgent: {response}",
                )

        return response

    except Exception as e:
        logger.error("text_message_handler_error", error=str(e))
        raise


async def handle_voice_note(msg: WhatsAppMessage, history: str) -> str:
    """Transcribe voice note and generate spoken response."""
    try:
        # Download audio from WhatsApp
        audio_data = await whatsapp_service.download_media(msg.audio_id)

        # Transcribe with Deepgram
        transcript = await deepgram_service.transcribe(audio_data)
        logger.info("voice_note_transcribed", transcript_length=len(transcript))

        # Build prompt context
        context = {
            "phone_number": msg.from_number,
            "customer_name": msg.contact_name or "",
            "transcript": transcript,
            "conversation_history": history,
            "time_of_day": get_time_of_day(),
        }

        # Generate spoken response using Claude
        response = await claude_service.generate_voice_response(context)

        return response

    except Exception as e:
        logger.error("voice_note_handler_error", error=str(e))
        raise


async def update_lead_qualification(
    phone: str,
    customer_message: str,
    agent_response: str,
    history: str,
) -> None:
    """Extract and update lead qualification data."""
    try:
        full_conversation = f"History:\n{history}\n\nCustomer: {customer_message}\nAgent: {agent_response}"

        qualification = await claude_service.extract_qualification(full_conversation)

        if qualification:
            await hubspot_service.update_lead_qualification(phone, qualification)
            logger.info(
                "lead_qualification_updated",
                phone=phone,
                score=qualification.get("qualification", {}).get("lead_score"),
            )

    except Exception as e:
        logger.error("lead_qualification_error", error=str(e))


async def send_fallback_response(to_number: str) -> None:
    """Send fallback response when processing fails."""
    fallback_message = (
        "Sorry, I'm having a technical issue right now. "
        "Please call us on 020 7946 0958 or try again in a moment."
    )
    try:
        await whatsapp_service.send_text_message(to_number, fallback_message)
    except Exception as e:
        logger.error("fallback_response_failed", error=str(e))


def get_time_of_day() -> str:
    """Get current time of day as string."""
    from datetime import datetime

    import pytz

    london_tz = pytz.timezone(settings.business_timezone)
    hour = datetime.now(london_tz).hour

    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"

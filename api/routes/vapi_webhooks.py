"""
VAPI webhook handlers for voice call integration.
Handles assistant configuration, function calls, and call events.
"""

import hmac
import hashlib
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from config import settings
from services.calendar_service import calendar_service
from services.claude_service import claude_service
from services.hubspot_service import hubspot_service
from services.notification_service import notification_service

logger = structlog.get_logger(__name__)

router = APIRouter()


class FunctionCallRequest(BaseModel):
    """Generic function call request from VAPI."""
    name: str
    parameters: dict


def verify_vapi_signature(payload: bytes, signature: Optional[str]) -> bool:
    """Verify VAPI webhook signature for security."""
    if not settings.vapi_webhook_secret:
        logger.warning("vapi_webhook_secret_not_configured")
        return True  # Allow in development
    
    if not signature:
        return False
    
    expected = hmac.new(
        settings.vapi_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_vapi_signature: Optional[str] = Header(default=None),
) -> dict:
    """
    Main VAPI webhook endpoint.
    Handles various event types from VAPI during and after calls.
    """
    body = await request.body()
    
    # Verify signature in production
    if settings.is_production and not verify_vapi_signature(body, x_vapi_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    event_type = payload.get("type")
    
    logger.info("vapi_webhook_received", event_type=event_type)
    
    # Route to appropriate handler
    if event_type == "assistant-request":
        return await handle_assistant_request(payload)
    
    elif event_type == "function-call":
        return await handle_function_call(payload)
    
    elif event_type == "end-of-call-report":
        background_tasks.add_task(process_call_report, payload)
        return {"received": True}
    
    elif event_type == "transcript":
        background_tasks.add_task(process_transcript, payload)
        return {"received": True}
    
    elif event_type == "status-update":
        logger.info("call_status_update", status=payload.get("status"))
        return {"received": True}
    
    else:
        logger.debug("unhandled_vapi_event", event_type=event_type)
        return {"received": True}


async def handle_assistant_request(payload: dict) -> dict:
    """
    Handle assistant configuration request.
    Returns dynamic configuration based on context.
    """
    call_data = payload.get("call", {})
    customer_number = call_data.get("customer", {}).get("number")
    
    logger.info("assistant_request", customer_number=customer_number)
    
    # Check if existing customer
    is_existing = await hubspot_service.contact_exists(customer_number) if customer_number else False
    
    # Load system prompt
    with open("prompts/phone-call-agent.txt", "r") as f:
        system_prompt = f.read()
    
    # Load knowledge base
    knowledge = load_knowledge_base()
    
    # Customize greeting based on time
    from datetime import datetime
    import pytz
    
    london_tz = pytz.timezone(settings.business_timezone)
    hour = datetime.now(london_tz).hour
    
    if hour < 12:
        greeting = "Good morning, Hampstead Renovations, how can I help you?"
    elif hour < 18:
        greeting = "Good afternoon, Hampstead Renovations, how can I help you?"
    else:
        greeting = "Good evening, Hampstead Renovations, how can I help you?"
    
    return {
        "assistant": {
            "firstMessage": greeting,
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250514",
                "systemPrompt": f"{system_prompt}\n\nKNOWLEDGE BASE:\n{knowledge}",
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "EXAVITQu4vr4xnSDxMaL",
            },
        }
    }


async def handle_function_call(payload: dict) -> dict:
    """
    Handle function calls from VAPI during conversations.
    Routes to appropriate function handler.
    """
    function_call = payload.get("functionCall", {})
    function_name = function_call.get("name")
    parameters = function_call.get("parameters", {})
    
    logger.info("function_call", function_name=function_name, parameters=parameters)
    
    handlers = {
        "check_availability": handle_check_availability,
        "book_survey": handle_book_survey,
        "get_pricing": handle_get_pricing,
        "transfer_to_human": handle_transfer_to_human,
        "check_service_area": handle_check_service_area,
    }
    
    handler = handlers.get(function_name)
    if not handler:
        logger.warning("unknown_function", function_name=function_name)
        return {"error": f"Unknown function: {function_name}"}
    
    try:
        result = await handler(parameters, payload)
        return {"result": result}
    except Exception as e:
        logger.error("function_call_error", function_name=function_name, error=str(e))
        return {"error": str(e)}


async def handle_check_availability(params: dict, payload: dict) -> dict:
    """Check calendar availability."""
    date = params.get("date")
    preference = params.get("time_preference", "any")
    
    if not date:
        return {"message": "What date would you like me to check?"}
    
    slots = await calendar_service.get_available_slots(date, preference)
    
    if slots:
        slot_times = [s["time"] for s in slots[:4]]
        times_str = ", ".join(slot_times[:-1]) + f" or {slot_times[-1]}" if len(slot_times) > 1 else slot_times[0]
        return {
            "available": True,
            "slots": slots[:4],
            "message": f"Ross is free on {date} at {times_str}. Which would work best for you?",
        }
    else:
        return {
            "available": False,
            "slots": [],
            "message": f"Unfortunately {date} is fully booked. Would you like me to check another day?",
        }


async def handle_book_survey(params: dict, payload: dict) -> dict:
    """Book a survey appointment."""
    required = ["name", "phone", "address", "date", "time"]
    missing = [f for f in required if not params.get(f)]
    
    if missing:
        return {"message": f"I still need your {', '.join(missing)} to complete the booking."}
    
    try:
        # Create calendar event
        event_id = await calendar_service.create_survey_booking(
            name=params["name"],
            phone=params["phone"],
            email=params.get("email"),
            address=params["address"],
            date=params["date"],
            time=params["time"],
            project_type=params.get("project_type", "General enquiry"),
            notes=params.get("notes"),
        )
        
        # Create HubSpot contact
        await hubspot_service.create_or_update_contact(
            phone=params["phone"],
            name=params["name"],
            email=params.get("email"),
            project_type=params.get("project_type"),
            source="phone_call",
        )
        
        # Format confirmation
        from datetime import datetime
        dt = datetime.strptime(f"{params['date']} {params['time']}", "%Y-%m-%d %H:%M")
        friendly_date = dt.strftime("%A at %I:%M %p").replace(" 0", " ")
        
        return {
            "success": True,
            "booking_id": event_id,
            "message": (
                f"Perfect, I've booked you in for {friendly_date}. "
                f"Ross will visit {params['address']}. "
                "You'll receive a WhatsApp confirmation shortly."
            ),
        }
        
    except Exception as e:
        logger.error("booking_failed", error=str(e))
        return {
            "success": False,
            "message": "I'm having trouble with the booking system. Let me have Ross call you back to confirm the appointment.",
        }


async def handle_get_pricing(params: dict, payload: dict) -> dict:
    """Get pricing information for a service type."""
    service_type = params.get("service_type", "").lower().replace(" ", "-")
    
    pricing = {
        "kitchen-extension": {
            "min": 80000,
            "max": 200000,
            "duration": "10-14 weeks",
            "message": "A kitchen extension typically ranges from around eighty thousand to two hundred thousand pounds, depending on size and specification. Usually takes about ten to fourteen weeks.",
        },
        "loft-conversion": {
            "min": 60000,
            "max": 150000,
            "duration": "10-12 weeks",
            "message": "A loft conversion is usually between sixty and a hundred and fifty thousand, depending on whether it's a simple dormer or something more complex like a mansard. Takes about ten to twelve weeks.",
        },
        "bathroom": {
            "min": 15000,
            "max": 45000,
            "duration": "3-5 weeks",
            "message": "A bathroom refurbishment typically runs from fifteen to forty-five thousand depending on the specification. Usually three to five weeks.",
        },
        "full-renovation": {
            "min": 150000,
            "max": 500000,
            "duration": "4-6 months",
            "message": "Full renovations vary quite a bit depending on the property size. For a typical three-bed house, usually between a hundred and fifty thousand and three hundred thousand. Can take four to six months.",
        },
        "basement": {
            "min": 150000,
            "max": 450000,
            "duration": "5-7 months",
            "message": "Basement conversions typically range from a hundred and fifty thousand for a basic conversion up to four hundred thousand or more for a full dig-out. Usually takes five to seven months.",
        },
    }
    
    info = pricing.get(service_type)
    if not info:
        return {
            "message": "I don't have specific pricing for that type of project. Would you like me to have Ross call you to discuss it in more detail?",
        }
    
    return {
        "service_type": service_type,
        "min_price": info["min"],
        "max_price": info["max"],
        "duration": info["duration"],
        "message": info["message"] + " For an accurate quote, Ross would need to see the property. Would you like to book a free site visit?",
    }


async def handle_transfer_to_human(params: dict, payload: dict) -> dict:
    """Handle transfer request to Ross."""
    reason = params.get("reason", "Customer requested transfer")
    urgency = params.get("urgency", "same-day")
    
    call_data = payload.get("call", {})
    customer_number = call_data.get("customer", {}).get("number")
    
    # Notify Ross of transfer request
    await notification_service.notify_transfer_request(
        customer_phone=customer_number,
        reason=reason,
        urgency=urgency,
    )
    
    if urgency == "immediate":
        return {
            "action": "transfer",
            "destination": settings.ross_mobile_number,
            "message": "I'll transfer you to Ross now. Just one moment.",
        }
    else:
        return {
            "action": "callback",
            "message": f"I'll have Ross call you back {urgency.replace('-', ' ')}. Is there anything else I can help with in the meantime?",
        }


async def handle_check_service_area(params: dict, payload: dict) -> dict:
    """Check if a location is within service area."""
    postcode = params.get("postcode", "").upper().strip()
    area_name = params.get("area_name", "").lower()
    
    # Primary postcodes
    primary_postcodes = ["NW3", "NW6", "NW11"]
    secondary_postcodes = ["NW2", "NW8", "N6", "N2", "N10"]
    
    # Check postcode
    postcode_prefix = postcode.split()[0] if postcode else ""
    
    if postcode_prefix in primary_postcodes:
        return {
            "in_area": True,
            "area_type": "primary",
            "message": f"Yes, {postcode} is right in our core area. We do lots of work there.",
        }
    elif postcode_prefix in secondary_postcodes:
        return {
            "in_area": True,
            "area_type": "secondary",
            "message": f"Yes, we regularly work in {postcode}. That's within our service area.",
        }
    elif postcode_prefix.startswith(("NW", "N")):
        return {
            "in_area": "borderline",
            "area_type": "borderline",
            "message": f"{postcode} is at the edge of our usual area. Let me note that down and Ross can confirm when he calls.",
        }
    else:
        return {
            "in_area": False,
            "message": "Unfortunately we focus specifically on North West London for quality reasons. I'd recommend the Federation of Master Builders website to find builders in your area. Sorry we can't help on this one.",
        }


async def process_call_report(payload: dict) -> None:
    """Process end-of-call report for CRM update and analytics."""
    try:
        call_data = payload.get("call", {})
        customer_number = call_data.get("customer", {}).get("number")
        transcript = payload.get("transcript", "")
        summary = payload.get("summary", "")
        duration = call_data.get("duration")
        
        logger.info(
            "processing_call_report",
            customer_number=customer_number,
            duration=duration,
        )
        
        # Extract qualification from transcript
        qualification = await claude_service.extract_qualification(transcript)
        
        # Update HubSpot
        if customer_number:
            await hubspot_service.log_call(
                phone=customer_number,
                transcript=transcript,
                summary=summary,
                duration=duration,
                qualification=qualification,
            )
        
        logger.info("call_report_processed", customer_number=customer_number)
        
    except Exception as e:
        logger.error("call_report_processing_error", error=str(e))


async def process_transcript(payload: dict) -> None:
    """Process real-time transcript for sentiment monitoring."""
    try:
        # Could implement real-time sentiment analysis here
        # for live escalation during calls
        pass
    except Exception as e:
        logger.error("transcript_processing_error", error=str(e))


def load_knowledge_base() -> str:
    """Load all knowledge base files into a single string."""
    import os
    
    knowledge = []
    kb_dir = "knowledge-base"
    
    if os.path.exists(kb_dir):
        for filename in sorted(os.listdir(kb_dir)):
            if filename.endswith(".md"):
                with open(os.path.join(kb_dir, filename), "r", encoding="utf-8") as f:
                    knowledge.append(f.read())
    
    return "\n\n---\n\n".join(knowledge)

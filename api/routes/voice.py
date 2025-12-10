"""
Voice-related routes for handling voice notes and call data.
"""

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from services.deepgram_service import deepgram_service
from services.elevenlabs_service import elevenlabs_service

logger = structlog.get_logger(__name__)

router = APIRouter()


class TranscribeRequest(BaseModel):
    """Request model for URL-based transcription."""

    audio_url: str
    language: str = "en-GB"


class TextToSpeechRequest(BaseModel):
    """Request model for text-to-speech generation."""

    text: str
    voice_id: str | None = None


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    """
    Transcribe an audio file to text using Deepgram.

    Args:
        file: Audio file to transcribe (mp3, wav, ogg, etc.)

    Returns:
        Transcription result with text and metadata
    """
    try:
        # Read file content
        audio_data = await file.read()

        if not audio_data:
            raise HTTPException(status_code=400, detail="Empty audio file")

        logger.info(
            "transcription_request",
            filename=file.filename,
            content_type=file.content_type,
            size=len(audio_data),
        )

        # Transcribe using Deepgram
        transcript = await deepgram_service.transcribe(audio_data)

        return {
            "success": True,
            "transcript": transcript,
            "filename": file.filename,
        }

    except Exception as e:
        logger.error("transcription_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/transcribe/url")
async def transcribe_from_url(request: TranscribeRequest) -> dict:
    """
    Transcribe audio from a URL using Deepgram.

    Args:
        request: Contains audio_url and optional language

    Returns:
        Transcription result
    """
    try:
        logger.info("transcription_url_request", url=request.audio_url)

        transcript = await deepgram_service.transcribe_url(request.audio_url)

        return {
            "success": True,
            "transcript": transcript,
            "audio_url": request.audio_url,
        }

    except Exception as e:
        logger.error("transcription_url_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/synthesize")
async def synthesize_speech(request: TextToSpeechRequest) -> dict:
    """
    Generate speech audio from text using ElevenLabs.

    Args:
        request: Contains text and optional voice_id

    Returns:
        URL to generated audio file
    """
    try:
        if not request.text or len(request.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text is required")

        if len(request.text) > 5000:
            raise HTTPException(
                status_code=400, detail="Text exceeds maximum length of 5000 characters"
            )

        logger.info(
            "tts_request",
            text_length=len(request.text),
            voice_id=request.voice_id,
        )

        # Generate voice audio
        audio_url = await elevenlabs_service.generate_voice_note(
            text=request.text,
            voice_id=request.voice_id,
        )

        return {
            "success": True,
            "audio_url": audio_url,
            "text_length": len(request.text),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("tts_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {str(e)}")


@router.get("/voices")
async def list_available_voices() -> dict:
    """
    List available voice options for text-to-speech.

    Returns:
        List of available voices with their IDs and descriptions
    """
    return {
        "voices": [
            {
                "id": "EXAVITQu4vr4xnSDxMaL",
                "name": "Sarah",
                "description": "Professional British female voice - warm and friendly",
                "gender": "female",
                "accent": "British",
                "use_case": "Primary voice for all interactions",
            },
            {
                "id": "pNInz6obpgDQGcFmaJgB",
                "name": "Adam",
                "description": "Professional British male voice - clear and trustworthy",
                "gender": "male",
                "accent": "British",
                "use_case": "Alternative/fallback voice",
            },
        ],
        "default_voice_id": "EXAVITQu4vr4xnSDxMaL",
    }

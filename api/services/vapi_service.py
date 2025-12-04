"""
VAPI voice call service.
Handles live phone calls via VAPI integration.
"""

import hmac
import hashlib
from typing import Any, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

logger = structlog.get_logger(__name__)


class VAPIService:
    """Service for VAPI voice call integration."""

    def __init__(self):
        self.api_key = settings.vapi_api_key
        self.assistant_id = settings.vapi_assistant_id
        self.webhook_secret = settings.vapi_webhook_secret
        self.base_url = "https://api.vapi.ai"

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
    ) -> bool:
        """
        Verify VAPI webhook signature.
        
        Args:
            payload: Raw request body bytes
            signature: X-Vapi-Signature header value
            
        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.warning("vapi_webhook_secret_not_configured")
            return True  # Skip verification if not configured

        try:
            expected = hmac.new(
                self.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()
            
            return hmac.compare_digest(expected, signature)
            
        except Exception as e:
            logger.error("vapi_signature_verification_error", error=str(e))
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_call(
        self,
        phone_number: str,
        assistant_id: Optional[str] = None,
        first_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Initiate an outbound call.
        
        Args:
            phone_number: Number to call (E.164 format)
            assistant_id: Override default assistant
            first_message: Custom first message
            metadata: Additional call metadata
            
        Returns:
            Call object from VAPI
        """
        url = f"{self.base_url}/call/phone"
        
        payload = {
            "assistantId": assistant_id or self.assistant_id,
            "phoneNumberId": settings.vapi_phone_number_id,
            "customer": {
                "number": phone_number,
            },
        }
        
        if first_message:
            payload["assistantOverrides"] = {
                "firstMessage": first_message,
            }
            
        if metadata:
            payload["metadata"] = metadata

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                
                call_data = response.json()
                logger.info(
                    "vapi_call_created",
                    call_id=call_data.get("id"),
                    phone=phone_number[-4:],
                )
                
                return call_data

        except Exception as e:
            logger.error("vapi_create_call_error", error=str(e))
            raise

    async def get_call(self, call_id: str) -> Optional[dict]:
        """Get call details by ID."""
        url = f"{self.base_url}/call/{call_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error("vapi_get_call_error", error=str(e), call_id=call_id)
            return None

    async def end_call(self, call_id: str) -> bool:
        """End an active call."""
        url = f"{self.base_url}/call/{call_id}/end"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self._get_headers())
                response.raise_for_status()
                
                logger.info("vapi_call_ended", call_id=call_id)
                return True

        except Exception as e:
            logger.error("vapi_end_call_error", error=str(e), call_id=call_id)
            return False

    async def transfer_call(
        self,
        call_id: str,
        destination: str,
        message: Optional[str] = None,
    ) -> bool:
        """
        Transfer call to another number.
        
        Args:
            call_id: Active call ID
            destination: Number to transfer to
            message: Message to play before transfer
        """
        url = f"{self.base_url}/call/{call_id}/transfer"
        
        payload = {
            "destination": {
                "type": "number",
                "number": destination,
            }
        }
        
        if message:
            payload["message"] = message

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                
                logger.info(
                    "vapi_call_transferred",
                    call_id=call_id,
                    destination=destination[-4:],
                )
                return True

        except Exception as e:
            logger.error("vapi_transfer_error", error=str(e), call_id=call_id)
            return False

    def handle_function_call(
        self,
        function_name: str,
        parameters: dict[str, Any],
        call_id: str,
    ) -> dict:
        """
        Handle VAPI function call webhook.
        
        Args:
            function_name: Name of function to execute
            parameters: Function parameters
            call_id: Associated call ID
            
        Returns:
            Function result to return to VAPI
        """
        logger.info(
            "vapi_function_call",
            function=function_name,
            call_id=call_id,
        )

        # Route to appropriate handler
        handlers = {
            "check_availability": self._handle_check_availability,
            "book_survey": self._handle_book_survey,
            "get_pricing": self._handle_get_pricing,
            "transfer_to_human": self._handle_transfer_to_human,
            "send_information": self._handle_send_information,
        }

        handler = handlers.get(function_name)
        if handler:
            return handler(parameters, call_id)
        
        logger.warning("unknown_function_call", function=function_name)
        return {"error": f"Unknown function: {function_name}"}

    def _handle_check_availability(self, params: dict, call_id: str) -> dict:
        """Handle availability check function."""
        # This would integrate with calendar_service
        return {
            "available": True,
            "next_available": "Tomorrow at 10am",
            "slots": ["10:00", "14:00", "16:00"],
        }

    def _handle_book_survey(self, params: dict, call_id: str) -> dict:
        """Handle survey booking function."""
        return {
            "success": True,
            "message": "Survey booked successfully",
            "confirmation_number": f"HR-{call_id[:8].upper()}",
        }

    def _handle_get_pricing(self, params: dict, call_id: str) -> dict:
        """Handle pricing inquiry function."""
        project_type = params.get("project_type", "general")
        
        pricing_info = {
            "kitchen": "Kitchen renovations typically range from £25,000 to £75,000",
            "bathroom": "Bathroom renovations typically range from £15,000 to £40,000",
            "extension": "Extensions typically range from £50,000 to £150,000",
            "general": "Projects typically range from £15,000 to £150,000 depending on scope",
        }
        
        return {
            "pricing": pricing_info.get(project_type.lower(), pricing_info["general"]),
            "note": "We provide free detailed quotes after a site survey",
        }

    def _handle_transfer_to_human(self, params: dict, call_id: str) -> dict:
        """Handle transfer to human request."""
        return {
            "action": "transfer",
            "destination": settings.ross_mobile_number,
            "message": "Transferring you to Ross now. Please hold.",
        }

    def _handle_send_information(self, params: dict, call_id: str) -> dict:
        """Handle send information request."""
        return {
            "success": True,
            "message": "I'll send you our brochure and portfolio via WhatsApp after this call.",
        }


# Singleton instance
vapi_service = VAPIService()

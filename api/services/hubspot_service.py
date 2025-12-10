"""
HubSpot CRM service.
Handles contact management, deal creation, and activity logging.
"""

from datetime import datetime
from typing import Any

import httpx
import structlog
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class HubSpotService:
    """Service for HubSpot CRM integration."""

    def __init__(self):
        self.api_key = settings.hubspot_api_key
        self.base_url = "https://api.hubapi.com"
        self.portal_id = settings.hubspot_portal_id

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def contact_exists(self, phone: str) -> bool:
        """Check if a contact exists by phone number."""
        url = f"{self.base_url}/crm/v3/objects/contacts/search"

        # Clean phone number
        phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")

        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "phone",
                            "operator": "CONTAINS_TOKEN",
                            "value": phone_clean[-10:],  # Last 10 digits
                        }
                    ]
                }
            ],
            "properties": ["phone", "firstname", "lastname", "email"],
            "limit": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("total", 0) > 0

        except Exception as e:
            logger.error("hubspot_contact_search_error", error=str(e))
            return False

    async def get_contact_by_phone(self, phone: str) -> dict | None:
        """Get contact details by phone number."""
        url = f"{self.base_url}/crm/v3/objects/contacts/search"

        phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")

        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "phone",
                            "operator": "CONTAINS_TOKEN",
                            "value": phone_clean[-10:],
                        }
                    ]
                }
            ],
            "properties": [
                "phone",
                "firstname",
                "lastname",
                "email",
                "address",
                "city",
                "zip",
                "lifecyclestage",
                "hs_lead_status",
                "project_type",
                "lead_score",
            ],
            "limit": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("total", 0) > 0:
                    return data["results"][0]
                return None

        except Exception as e:
            logger.error("hubspot_get_contact_error", error=str(e))
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_or_update_contact(
        self,
        phone: str,
        name: str | None = None,
        email: str | None = None,
        project_type: str | None = None,
        address: str | None = None,
        postcode: str | None = None,
        source: str = "voice_agent",
        **extra_properties,
    ) -> dict:
        """Create or update a contact in HubSpot."""

        # Parse name
        firstname = ""
        lastname = ""
        if name:
            parts = name.strip().split(" ", 1)
            firstname = parts[0]
            lastname = parts[1] if len(parts) > 1 else ""

        properties = {
            "phone": phone,
            "lifecyclestage": "lead",
            "hs_lead_status": "NEW",
            "lead_source": source,
        }

        if firstname:
            properties["firstname"] = firstname
        if lastname:
            properties["lastname"] = lastname
        if email:
            properties["email"] = email
        if project_type:
            properties["project_type"] = project_type
        if address:
            properties["address"] = address
        if postcode:
            properties["zip"] = postcode

        # Add any extra properties
        properties.update(extra_properties)

        # Check if contact exists
        existing = await self.get_contact_by_phone(phone)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if existing:
                    # Update existing contact
                    contact_id = existing["id"]
                    url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
                    response = await client.patch(
                        url,
                        headers=self._get_headers(),
                        json={"properties": properties},
                    )
                    logger.info("hubspot_contact_updated", contact_id=contact_id)
                else:
                    # Create new contact
                    url = f"{self.base_url}/crm/v3/objects/contacts"
                    response = await client.post(
                        url,
                        headers=self._get_headers(),
                        json={"properties": properties},
                    )
                    logger.info("hubspot_contact_created", phone=phone)

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(
                "hubspot_contact_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error("hubspot_contact_error", error=str(e))
            raise

    async def update_lead_qualification(
        self,
        phone: str,
        qualification: dict[str, Any],
    ) -> dict | None:
        """Update contact with qualification data from AI analysis."""
        contact = await self.get_contact_by_phone(phone)
        if not contact:
            logger.warning("hubspot_qualification_no_contact", phone=phone)
            return None

        contact_id = contact["id"]

        # Extract qualification data
        qual_data = qualification.get("qualification", {})
        project_data = qualification.get("project", {})
        contact_data = qualification.get("contact", {})

        properties = {}

        # Lead score and tier
        if qual_data.get("lead_score"):
            properties["lead_score"] = str(qual_data["lead_score"])
        if qual_data.get("lead_tier"):
            properties["lead_tier"] = qual_data["lead_tier"]
        if qual_data.get("urgency"):
            properties["urgency"] = qual_data["urgency"]

        # Project info
        if project_data.get("type"):
            properties["project_type"] = project_data["type"]
        if project_data.get("timeline"):
            properties["project_timeline"] = project_data["timeline"]
        if project_data.get("budget_range"):
            properties["budget_range"] = project_data["budget_range"]
        if project_data.get("property_type"):
            properties["property_type"] = project_data["property_type"]

        # Contact info updates
        if contact_data.get("email") and not contact.get("properties", {}).get("email"):
            properties["email"] = contact_data["email"]
        if contact_data.get("address"):
            properties["address"] = contact_data["address"]
        if contact_data.get("postcode"):
            properties["zip"] = contact_data["postcode"]

        if not properties:
            return None

        url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    url,
                    headers=self._get_headers(),
                    json={"properties": properties},
                )
                response.raise_for_status()

                logger.info(
                    "hubspot_qualification_updated",
                    contact_id=contact_id,
                    lead_score=qual_data.get("lead_score"),
                )

                return response.json()

        except Exception as e:
            logger.error("hubspot_qualification_error", error=str(e))
            return None

    async def log_call(
        self,
        phone: str,
        transcript: str,
        summary: str,
        duration: int | None = None,
        qualification: dict | None = None,
    ) -> dict | None:
        """Log a phone call as an engagement in HubSpot."""
        contact = await self.get_contact_by_phone(phone)
        if not contact:
            logger.warning("hubspot_log_call_no_contact", phone=phone)
            return None

        contact_id = contact["id"]

        # Create call engagement
        url = f"{self.base_url}/crm/v3/objects/calls"

        # Build call body
        body = f"**Summary:**\n{summary}\n\n**Full Transcript:**\n{transcript}"

        if qualification:
            qual = qualification.get("qualification", {})
            body += "\n\n**AI Qualification:**\n"
            body += f"- Lead Score: {qual.get('lead_score', 'N/A')}\n"
            body += f"- Lead Tier: {qual.get('lead_tier', 'N/A')}\n"
            body += f"- Urgency: {qual.get('urgency', 'N/A')}"

        properties = {
            "hs_call_title": "AI Voice Agent Call",
            "hs_call_body": body[:65535],  # HubSpot limit
            "hs_call_direction": "INBOUND",
            "hs_call_disposition": "connected",
            "hs_call_status": "COMPLETED",
            "hs_timestamp": datetime.utcnow().isoformat() + "Z",
        }

        if duration:
            properties["hs_call_duration"] = str(duration * 1000)  # milliseconds

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create call
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json={"properties": properties},
                )
                response.raise_for_status()
                call_data = response.json()
                call_id = call_data["id"]

                # Associate with contact
                assoc_url = (
                    f"{self.base_url}/crm/v4/objects/calls/{call_id}"
                    f"/associations/contacts/{contact_id}"
                )
                await client.put(
                    assoc_url,
                    headers=self._get_headers(),
                    json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 194}],
                )

                logger.info("hubspot_call_logged", call_id=call_id, contact_id=contact_id)

                return call_data

        except Exception as e:
            logger.error("hubspot_log_call_error", error=str(e))
            return None

    async def create_deal(
        self,
        contact_id: str,
        deal_name: str,
        pipeline: str = "default",
        stage: str = "appointmentscheduled",
        amount: float | None = None,
    ) -> dict | None:
        """Create a deal associated with a contact."""
        url = f"{self.base_url}/crm/v3/objects/deals"

        properties = {
            "dealname": deal_name,
            "pipeline": pipeline,
            "dealstage": stage,
        }

        if amount:
            properties["amount"] = str(amount)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create deal
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json={"properties": properties},
                )
                response.raise_for_status()
                deal_data = response.json()
                deal_id = deal_data["id"]

                # Associate with contact
                assoc_url = (
                    f"{self.base_url}/crm/v4/objects/deals/{deal_id}"
                    f"/associations/contacts/{contact_id}"
                )
                await client.put(
                    assoc_url,
                    headers=self._get_headers(),
                    json=[{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
                )

                logger.info("hubspot_deal_created", deal_id=deal_id)
                return deal_data

        except Exception as e:
            logger.error("hubspot_create_deal_error", error=str(e))
            return None


# Singleton instance
hubspot_service = HubSpotService()

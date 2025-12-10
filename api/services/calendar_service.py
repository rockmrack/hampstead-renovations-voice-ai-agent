"""
Microsoft Graph Calendar service.
Handles booking management via Microsoft Bookings/Calendar.
"""

from datetime import datetime, timedelta

import httpx
import structlog
from config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class CalendarService:
    """Service for Microsoft Graph Calendar/Bookings integration."""

    def __init__(self):
        self.client_id = settings.microsoft_client_id
        self.client_secret = settings.microsoft_client_secret
        self.tenant_id = settings.microsoft_tenant_id
        self.ross_email = settings.ross_email
        self.base_url = "https://graph.microsoft.com/v1.0"
        self._access_token: str | None = None
        self._token_expires: datetime | None = None

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth access token."""
        if self._access_token and self._token_expires and datetime.utcnow() < self._token_expires:
            return self._access_token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                token_data = response.json()

            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in - 300)

            return self._access_token

        except Exception as e:
            logger.error("microsoft_auth_error", error=str(e))
            raise

    async def _get_headers(self) -> dict[str, str]:
        """Get authenticated headers."""
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def get_available_slots(
        self,
        date: str,
        time_preference: str = "any",
        duration_minutes: int = 60,
    ) -> list[dict]:
        """
        Get available time slots for a given date.

        Args:
            date: Date in YYYY-MM-DD format
            time_preference: 'morning', 'afternoon', 'any'
            duration_minutes: Required duration

        Returns:
            List of available slots
        """
        headers = await self._get_headers()

        # Parse date
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            logger.error("invalid_date_format", date=date)
            return []

        # Set time ranges based on preference and business hours
        if time_preference == "morning":
            start_hour = settings.office_open_hour
            end_hour = 12
        elif time_preference == "afternoon":
            start_hour = 12
            end_hour = settings.office_close_hour
        else:
            start_hour = settings.office_open_hour
            end_hour = settings.office_close_hour

        # Check if Saturday
        if target_date.weekday() == 5:  # Saturday
            start_hour = settings.saturday_open_hour
            end_hour = settings.saturday_close_hour
        elif target_date.weekday() == 6:  # Sunday
            return []  # Closed on Sundays

        start_datetime = target_date.replace(hour=start_hour, minute=0)
        end_datetime = target_date.replace(hour=end_hour, minute=0)

        # Get calendar free/busy
        url = f"{self.base_url}/users/{self.ross_email}/calendar/getSchedule"

        payload = {
            "schedules": [self.ross_email],
            "startTime": {
                "dateTime": start_datetime.isoformat(),
                "timeZone": settings.business_timezone,
            },
            "endTime": {
                "dateTime": end_datetime.isoformat(),
                "timeZone": settings.business_timezone,
            },
            "availabilityViewInterval": 30,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            # Parse availability
            schedule = data.get("value", [{}])[0]
            availability_view = schedule.get("availabilityView", "")

            # Find free slots (0 = free, 1 = tentative, 2 = busy, 3 = OOF)
            available_slots = []
            current_time = start_datetime

            for i, status in enumerate(availability_view):
                if status == "0":  # Free
                    slot_time = current_time + timedelta(minutes=i * 30)
                    if slot_time.hour < end_hour:
                        available_slots.append(
                            {
                                "date": date,
                                "time": slot_time.strftime("%H:%M"),
                                "datetime": slot_time.isoformat(),
                                "duration": duration_minutes,
                            }
                        )

            # Return reasonable number of slots
            return available_slots[:6]

        except Exception as e:
            logger.error("calendar_get_slots_error", error=str(e))
            return await self._generate_fallback_slots(date, time_preference)

    async def _generate_fallback_slots(
        self,
        date: str,
        time_preference: str,
    ) -> list[dict]:
        """Generate fallback slots when calendar API is unavailable."""
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        if target_date.weekday() == 6:  # Sunday
            return []

        if time_preference == "morning":
            times = ["09:00", "10:00", "11:00"]
        elif time_preference == "afternoon":
            times = ["14:00", "15:00", "16:00"]
        else:
            times = ["10:00", "11:00", "14:00", "15:00"]

        if target_date.weekday() == 5:  # Saturday
            times = ["09:00", "10:00", "11:00", "12:00"]

        return [
            {
                "date": date,
                "time": t,
                "datetime": f"{date}T{t}:00",
                "duration": 60,
            }
            for t in times
        ]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def create_survey_booking(
        self,
        name: str,
        phone: str,
        address: str,
        date: str,
        time: str,
        email: str | None = None,
        project_type: str | None = None,
        notes: str | None = None,
    ) -> str:
        """
        Create a survey booking in the calendar.

        Returns:
            Event ID
        """
        headers = await self._get_headers()

        # Parse datetime
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)

        # Build event body
        body_content = f"""
<b>Site Survey Booking</b><br><br>
<b>Customer:</b> {name}<br>
<b>Phone:</b> {phone}<br>
<b>Email:</b> {email or "Not provided"}<br>
<b>Address:</b> {address}<br>
<b>Project Type:</b> {project_type or "General enquiry"}<br>
<b>Notes:</b> {notes or "None"}<br><br>
<i>Booked via AI Voice Agent</i>
"""

        event = {
            "subject": f"Site Survey - {name} - {address.split(',')[0]}",
            "body": {
                "contentType": "HTML",
                "content": body_content,
            },
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": settings.business_timezone,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": settings.business_timezone,
            },
            "location": {
                "displayName": address,
            },
            "attendees": [],
            "isReminderOn": True,
            "reminderMinutesBeforeStart": 60,
        }

        if email:
            event["attendees"].append(
                {
                    "emailAddress": {"address": email, "name": name},
                    "type": "optional",
                }
            )

        url = f"{self.base_url}/users/{self.ross_email}/events"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=event)
                response.raise_for_status()
                data = response.json()

            event_id = data["id"]

            logger.info(
                "survey_booking_created",
                event_id=event_id,
                name=name,
                date=date,
                time=time,
            )

            return event_id

        except Exception as e:
            logger.error("calendar_create_booking_error", error=str(e))
            raise

    async def cancel_booking(self, event_id: str, reason: str | None = None) -> bool:
        """Cancel an existing booking."""
        headers = await self._get_headers()
        url = f"{self.base_url}/users/{self.ross_email}/events/{event_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()

            logger.info("booking_cancelled", event_id=event_id, reason=reason)
            return True

        except Exception as e:
            logger.error("calendar_cancel_error", error=str(e), event_id=event_id)
            return False

    async def reschedule_booking(
        self,
        event_id: str,
        new_date: str,
        new_time: str,
    ) -> bool:
        """Reschedule an existing booking."""
        headers = await self._get_headers()

        start_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)

        url = f"{self.base_url}/users/{self.ross_email}/events/{event_id}"

        patch_data = {
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": settings.business_timezone,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": settings.business_timezone,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(url, headers=headers, json=patch_data)
                response.raise_for_status()

            logger.info(
                "booking_rescheduled",
                event_id=event_id,
                new_date=new_date,
                new_time=new_time,
            )
            return True

        except Exception as e:
            logger.error("calendar_reschedule_error", error=str(e))
            return False

    async def get_upcoming_bookings(self, days: int = 7) -> list[dict]:
        """Get upcoming survey bookings."""
        headers = await self._get_headers()

        start_dt = datetime.utcnow()
        end_dt = start_dt + timedelta(days=days)

        url = (
            f"{self.base_url}/users/{self.ross_email}/calendarView"
            f"?startDateTime={start_dt.isoformat()}Z"
            f"&endDateTime={end_dt.isoformat()}Z"
            f"&$filter=contains(subject,'Site Survey')"
            f"&$orderby=start/dateTime"
            f"&$top=50"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

            return data.get("value", [])

        except Exception as e:
            logger.error("calendar_get_bookings_error", error=str(e))
            return []


# Singleton instance
calendar_service = CalendarService()

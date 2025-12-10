"""
Reminder service for appointment notifications.
Sends WhatsApp/SMS reminders 24hr and 2hr before site visits.
"""

from datetime import datetime, timedelta

import structlog
from config import settings

logger = structlog.get_logger()


class ReminderService:
    """Service for managing appointment reminders."""

    def __init__(self) -> None:
        self._redis = None

    def _get_redis(self):
        """Lazy load Redis connection."""
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    async def get_upcoming_appointments(self, hours_ahead: int = 48) -> list[dict]:
        """
        Get appointments in the next X hours.

        Args:
            hours_ahead: Number of hours to look ahead

        Returns:
            List of appointment dictionaries
        """
        redis = self._get_redis()
        now = datetime.now()
        cutoff = now + timedelta(hours=hours_ahead)

        # Get all appointment keys
        appointment_keys = await redis.keys("appointment:*")
        appointments = []

        for key in appointment_keys:
            appt_data = await redis.hgetall(key)
            if not appt_data:
                continue

            # Decode bytes to strings
            appt = {k.decode(): v.decode() for k, v in appt_data.items()}
            appt["id"] = key.decode().split(":")[-1]

            # Parse appointment time
            appt_time_str = appt.get("appointment_time")
            if not appt_time_str:
                continue

            appt_time = datetime.fromisoformat(appt_time_str)

            # Check if within range and confirmed
            if appt_time <= now or appt_time > cutoff:
                continue

            if appt.get("status") != "confirmed":
                continue

            appt["appointment_time_dt"] = appt_time

            # Get reminder status
            reminder_key = f"appointment_reminder:{appt['id']}"
            reminder_data = await redis.hgetall(reminder_key)
            if reminder_data:
                appt["reminder_24h_sent"] = (
                    reminder_data.get(b"reminder_24h_sent", b"false").decode() == "true"
                )
                appt["reminder_2h_sent"] = (
                    reminder_data.get(b"reminder_2h_sent", b"false").decode() == "true"
                )
            else:
                appt["reminder_24h_sent"] = False
                appt["reminder_2h_sent"] = False

            appointments.append(appt)

        # Sort by appointment time
        appointments.sort(key=lambda x: x["appointment_time_dt"])

        return appointments

    async def send_reminder(
        self,
        appointment: dict,
        reminder_type: str,
        whatsapp_service,
    ) -> bool:
        """
        Send reminder via WhatsApp.

        Args:
            appointment: Appointment data dictionary
            reminder_type: Type of reminder ("24h" or "2h")
            whatsapp_service: WhatsApp service instance

        Returns:
            True if sent successfully
        """
        appt_time = appointment["appointment_time_dt"]
        formatted_date = appt_time.strftime("%A, %d %B")
        formatted_time = appt_time.strftime("%I:%M %p").lstrip("0")

        name = appointment.get("name", "there")
        location = appointment.get("location", "Your property")
        phone = appointment.get("phone")

        if not phone:
            logger.warning("reminder_no_phone", appointment_id=appointment.get("id"))
            return False

        if reminder_type == "24h":
            message = f"""Hi {name}!

Just a reminder that Ross from Hampstead Renovations is visiting tomorrow for your site survey.

{formatted_date}
{formatted_time}
{location}

Please let us know if you need to reschedule. Otherwise, see you tomorrow!"""

        else:  # 2h reminder
            message = f"""Hi {name}!

Ross is on his way and will be with you in about 2 hours for your site survey at {formatted_time}.

If anything's come up, just reply to this message.

See you soon!"""

        success = await whatsapp_service.send_message(phone, message)

        if success:
            redis = self._get_redis()
            reminder_key = f"appointment_reminder:{appointment['id']}"

            # Mark reminder as sent
            field = "reminder_24h_sent" if reminder_type == "24h" else "reminder_2h_sent"
            await redis.hset(reminder_key, field, "true")

            logger.info(
                "reminder_sent",
                appointment_id=appointment.get("id"),
                reminder_type=reminder_type,
                phone=phone,
            )

        return success

    async def process_reminders(self, whatsapp_service) -> dict:
        """
        Main job - process all pending reminders.

        Args:
            whatsapp_service: WhatsApp service instance

        Returns:
            Results dictionary with counts
        """
        appointments = await self.get_upcoming_appointments(hours_ahead=48)
        now = datetime.now()

        results = {"24h_sent": 0, "2h_sent": 0, "errors": 0}

        for appt in appointments:
            time_until = appt["appointment_time_dt"] - now
            hours_until = time_until.total_seconds() / 3600

            try:
                # 24h reminder: send if 23-25 hours away and not sent
                if 23 <= hours_until <= 25 and not appt["reminder_24h_sent"]:
                    success = await self.send_reminder(appt, "24h", whatsapp_service)
                    if success:
                        results["24h_sent"] += 1
                    else:
                        results["errors"] += 1

                # 2h reminder: send if 1.5-2.5 hours away and not sent
                elif 1.5 <= hours_until <= 2.5 and not appt["reminder_2h_sent"]:
                    success = await self.send_reminder(appt, "2h", whatsapp_service)
                    if success:
                        results["2h_sent"] += 1
                    else:
                        results["errors"] += 1

            except Exception as e:
                logger.error(
                    "reminder_processing_error", appointment_id=appt.get("id"), error=str(e)
                )
                results["errors"] += 1

        logger.info("reminder_processing_complete", **results)
        return results

    async def create_appointment(
        self,
        lead_id: str,
        name: str,
        phone: str,
        appointment_time: datetime,
        location: str,
        appointment_type: str = "site_survey",
        notes: str | None = None,
        calendar_event_id: str | None = None,
    ) -> str:
        """
        Create a new appointment.

        Args:
            lead_id: Lead ID
            name: Customer name
            phone: Customer phone
            appointment_time: Scheduled time
            location: Appointment location
            appointment_type: Type of appointment
            notes: Additional notes
            calendar_event_id: External calendar event ID

        Returns:
            Appointment ID
        """
        import uuid

        redis = self._get_redis()
        appointment_id = str(uuid.uuid4())[:8]

        await redis.hset(
            f"appointment:{appointment_id}",
            mapping={
                "lead_id": lead_id,
                "name": name,
                "phone": phone,
                "appointment_time": appointment_time.isoformat(),
                "location": location,
                "appointment_type": appointment_type,
                "notes": notes or "",
                "calendar_event_id": calendar_event_id or "",
                "status": "confirmed",
                "created_at": datetime.now().isoformat(),
            },
        )

        logger.info(
            "appointment_created",
            appointment_id=appointment_id,
            lead_id=lead_id,
            appointment_time=appointment_time.isoformat(),
        )

        return appointment_id

    async def cancel_appointment(self, appointment_id: str, reason: str | None = None) -> bool:
        """
        Cancel an appointment.

        Args:
            appointment_id: Appointment ID to cancel
            reason: Optional cancellation reason

        Returns:
            True if cancelled successfully
        """
        redis = self._get_redis()
        key = f"appointment:{appointment_id}"

        exists = await redis.exists(key)
        if not exists:
            return False

        await redis.hset(key, "status", "cancelled")
        if reason:
            await redis.hset(key, "cancellation_reason", reason)
        await redis.hset(key, "cancelled_at", datetime.now().isoformat())

        logger.info("appointment_cancelled", appointment_id=appointment_id, reason=reason)
        return True


# Singleton instance
reminder_service = ReminderService()

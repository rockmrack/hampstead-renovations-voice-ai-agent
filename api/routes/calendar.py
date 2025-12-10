"""
Calendar management routes for survey booking.
"""

from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from services.calendar_service import calendar_service
from services.hubspot_service import hubspot_service
from services.notification_service import notification_service

logger = structlog.get_logger(__name__)

router = APIRouter()


class AvailabilityRequest(BaseModel):
    """Request model for checking availability."""

    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD format")
    time_preference: str | None = Field(default="any", pattern="^(morning|afternoon|any)$")


class BookingRequest(BaseModel):
    """Request model for booking a survey."""

    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    email: EmailStr | None = None
    address: str = Field(..., min_length=5, max_length=500)
    postcode: str | None = Field(default=None, max_length=10)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    project_type: str = Field(..., min_length=2, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class RescheduleRequest(BaseModel):
    """Request model for rescheduling a booking."""

    booking_id: str
    new_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    new_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    reason: str | None = None


@router.post("/availability")
async def check_availability(request: AvailabilityRequest) -> dict:
    """
    Check Ross's calendar availability for a specific date.

    Args:
        request: Contains date and optional time preference

    Returns:
        Available time slots for the requested date
    """
    try:
        logger.info("checking_availability", date=request.date, preference=request.time_preference)

        # Parse and validate date
        try:
            check_date = datetime.strptime(request.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

        # Don't allow booking in the past
        if check_date < datetime.now().date():
            raise HTTPException(status_code=400, detail="Cannot check availability for past dates")

        # Don't allow booking too far in the future (90 days)
        if check_date > (datetime.now() + timedelta(days=90)).date():
            raise HTTPException(status_code=400, detail="Cannot book more than 90 days in advance")

        # Get available slots from calendar service
        slots = await calendar_service.get_available_slots(
            date=request.date,
            time_preference=request.time_preference,
        )

        # Format response
        available = len(slots) > 0

        return {
            "date": request.date,
            "available": available,
            "slots": slots[:6],  # Return up to 6 slots
            "slot_count": len(slots),
            "message": (
                f"Ross has {len(slots)} slots available on {request.date}"
                if available
                else f"Unfortunately {request.date} is fully booked. Would you like to check another day?"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("availability_check_error", error=str(e))
        raise HTTPException(status_code=500, detail="Unable to check calendar availability")


@router.post("/book")
async def book_survey(request: BookingRequest) -> dict:
    """
    Book a site survey appointment.

    Args:
        request: Booking details including name, contact info, and preferred time

    Returns:
        Booking confirmation with details
    """
    try:
        logger.info(
            "booking_survey",
            name=request.name,
            date=request.date,
            time=request.time,
            project_type=request.project_type,
        )

        # Validate date/time
        try:
            booking_datetime = datetime.strptime(f"{request.date} {request.time}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date or time format")

        if booking_datetime < datetime.now():
            raise HTTPException(status_code=400, detail="Cannot book appointments in the past")

        # Check slot is still available
        slots = await calendar_service.get_available_slots(request.date)
        if request.time not in [s.get("time") for s in slots]:
            raise HTTPException(
                status_code=409,
                detail="This time slot is no longer available. Please choose another time.",
            )

        # Create calendar event
        event_id = await calendar_service.create_survey_booking(
            name=request.name,
            phone=request.phone,
            email=request.email,
            address=request.address,
            date=request.date,
            time=request.time,
            project_type=request.project_type,
            notes=request.notes,
        )

        # Create/update HubSpot contact and deal
        contact_id = await hubspot_service.create_or_update_contact(
            phone=request.phone,
            name=request.name,
            email=request.email,
            postcode=request.postcode or extract_postcode(request.address),
            project_type=request.project_type,
            source="survey_booking",
        )

        await hubspot_service.create_survey_deal(
            contact_id=contact_id,
            project_type=request.project_type,
            postcode=request.postcode or extract_postcode(request.address),
            survey_date=request.date,
        )

        # Send notifications
        await notification_service.send_booking_confirmation(
            phone=request.phone,
            name=request.name,
            date=request.date,
            time=request.time,
            address=request.address,
        )

        await notification_service.notify_new_booking(
            name=request.name,
            phone=request.phone,
            date=request.date,
            time=request.time,
            address=request.address,
            project_type=request.project_type,
        )

        # Format friendly date
        friendly_date = booking_datetime.strftime("%A, %d %B")
        friendly_time = booking_datetime.strftime("%I:%M %p").lstrip("0").replace(" 0", " ")

        return {
            "success": True,
            "booking_id": event_id,
            "message": (
                f"Perfect, I've booked you in for {friendly_date} at {friendly_time}. "
                f"Ross will visit {request.address}. You'll receive a WhatsApp confirmation shortly."
            ),
            "booking": {
                "date": friendly_date,
                "time": friendly_time,
                "address": request.address,
                "project_type": request.project_type,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("booking_error", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unable to complete booking. Please try again or call us directly.",
        )


@router.post("/reschedule")
async def reschedule_booking(request: RescheduleRequest) -> dict:
    """
    Reschedule an existing survey booking.

    Args:
        request: Contains booking ID and new date/time

    Returns:
        Updated booking confirmation
    """
    try:
        logger.info(
            "rescheduling_booking",
            booking_id=request.booking_id,
            new_date=request.new_date,
            new_time=request.new_time,
        )

        # Check new slot is available
        slots = await calendar_service.get_available_slots(request.new_date)
        if request.new_time not in [s.get("time") for s in slots]:
            raise HTTPException(
                status_code=409,
                detail="This time slot is not available. Please choose another time.",
            )

        # Update calendar event
        updated = await calendar_service.reschedule_booking(
            booking_id=request.booking_id,
            new_date=request.new_date,
            new_time=request.new_time,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Booking not found")

        return {
            "success": True,
            "message": f"Your appointment has been rescheduled to {request.new_date} at {request.new_time}.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("reschedule_error", error=str(e))
        raise HTTPException(status_code=500, detail="Unable to reschedule booking")


@router.delete("/cancel/{booking_id}")
async def cancel_booking(booking_id: str, reason: str | None = None) -> dict:
    """
    Cancel a survey booking.

    Args:
        booking_id: ID of the booking to cancel
        reason: Optional cancellation reason

    Returns:
        Cancellation confirmation
    """
    try:
        logger.info("cancelling_booking", booking_id=booking_id, reason=reason)

        cancelled = await calendar_service.cancel_booking(booking_id, reason)

        if not cancelled:
            raise HTTPException(status_code=404, detail="Booking not found")

        return {
            "success": True,
            "message": "Your appointment has been cancelled.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("cancellation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Unable to cancel booking")


def extract_postcode(address: str) -> str | None:
    """Extract UK postcode from address string."""
    import re

    postcode_pattern = r"[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}"
    match = re.search(postcode_pattern, address.upper())
    return match.group(0) if match else None

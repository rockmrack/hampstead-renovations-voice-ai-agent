#!/usr/bin/env python3
"""
Appointment reminder script.
Run every 30 minutes via cron or scheduler.

Usage:
    python -m scripts.run_reminders
"""

import asyncio
import sys
from pathlib import Path

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import structlog  # noqa: E402
from services.reminder_service import reminder_service  # noqa: E402
from services.whatsapp_service import whatsapp_service  # noqa: E402

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Process pending appointment reminders."""
    logger.info("starting_reminder_processing")

    try:
        results = await reminder_service.process_reminders(whatsapp_service)

        logger.info(
            "reminder_processing_complete",
            reminders_24h_sent=results["24h_sent"],
            reminders_2h_sent=results["2h_sent"],
            errors=results["errors"],
        )

        # Print summary for cron log
        print(
            f"Reminders complete: {results['24h_sent']} 24h sent, "
            f"{results['2h_sent']} 2h sent, {results['errors']} errors"
        )

    except Exception as e:
        logger.error("reminder_processing_error", error=str(e))
        print(f"Error processing reminders: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

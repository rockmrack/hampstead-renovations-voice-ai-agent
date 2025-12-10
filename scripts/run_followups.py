#!/usr/bin/env python3
"""
Daily follow-up script for re-engaging stale leads.
Run daily at 10am via cron or scheduler.

Usage:
    python -m scripts.run_followups
"""

import asyncio
import sys
from pathlib import Path

# Add api directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import structlog  # noqa: E402
from services.followup_service import followup_service  # noqa: E402
from services.whatsapp_service import whatsapp_service  # noqa: E402

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Run daily follow-up job."""
    logger.info("starting_daily_followups")

    try:
        results = await followup_service.run_daily_followups(whatsapp_service)

        logger.info(
            "daily_followups_complete",
            sent=results["sent"],
            failed=results["failed"],
            skipped=results["skipped"],
        )

        # Print summary for cron log
        print(
            f"Follow-ups complete: {results['sent']} sent, {results['failed']} failed, {results['skipped']} skipped"
        )

    except Exception as e:
        logger.error("daily_followups_error", error=str(e))
        print(f"Error running follow-ups: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

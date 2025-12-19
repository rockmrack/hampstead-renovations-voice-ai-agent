"""
Analytics service for conversation analysis.
Handles clustering, sentiment trends, peak times, and drop-off analysis.
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ServiceInterest(str, Enum):
    """Types of services customers inquire about."""

    KITCHEN_EXTENSION = "kitchen_extension"
    LOFT_CONVERSION = "loft_conversion"
    BATHROOM = "bathroom"
    FULL_RENOVATION = "full_renovation"
    BASEMENT = "basement"
    GARDEN = "garden"
    OTHER = "other"
    UNKNOWN = "unknown"


class ConversationOutcome(str, Enum):
    """Possible conversation outcomes."""

    BOOKING_MADE = "booking_made"
    FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
    INFORMATION_PROVIDED = "information_provided"
    OUT_OF_AREA = "out_of_area"
    BUDGET_MISMATCH = "budget_mismatch"
    NOT_READY = "not_ready"
    DROPPED_OFF = "dropped_off"
    ESCALATED = "escalated"


@dataclass
class ConversationAnalytics:
    """Analytics data for a single conversation."""

    conversation_id: str
    channel: str
    started_at: datetime
    ended_at: datetime | None = None
    message_count: int = 0
    customer_messages: int = 0
    agent_messages: int = 0
    avg_response_time_ms: float = 0
    sentiment_scores: list[float] = field(default_factory=list)
    service_interests: list[ServiceInterest] = field(default_factory=list)
    outcome: ConversationOutcome = ConversationOutcome.DROPPED_OFF
    drop_off_point: str | None = None
    keywords: list[str] = field(default_factory=list)
    postcode_area: str | None = None
    lead_score: int = 0

    @property
    def duration_seconds(self) -> float:
        """Calculate conversation duration."""
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return 0

    @property
    def avg_sentiment(self) -> float:
        """Calculate average sentiment."""
        return (
            sum(self.sentiment_scores) / len(self.sentiment_scores) if self.sentiment_scores else 0
        )


class AnalyticsService:
    """Service for conversation analytics and insights."""

    def __init__(self, storage_path: str = "analytics"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.conversations: dict[str, ConversationAnalytics] = {}
        self._hourly_stats: dict[str, dict] = defaultdict(
            lambda: {
                "conversations": 0,
                "messages": 0,
                "bookings": 0,
            }
        )
        self._daily_stats: dict[str, dict] = defaultdict(
            lambda: {
                "conversations": 0,
                "messages": 0,
                "bookings": 0,
                "avg_sentiment": 0,
                "sentiment_sum": 0,
            }
        )
        self._load_data()

    def _load_data(self) -> None:
        """Load analytics data from storage."""
        data_file = self.storage_path / "analytics_data.json"
        if data_file.exists():
            try:
                data = json.loads(data_file.read_text())
                self._hourly_stats = defaultdict(
                    lambda: {"conversations": 0, "messages": 0, "bookings": 0},
                    data.get("hourly_stats", {}),
                )
                self._daily_stats = defaultdict(
                    lambda: {
                        "conversations": 0,
                        "messages": 0,
                        "bookings": 0,
                        "avg_sentiment": 0,
                        "sentiment_sum": 0,
                    },
                    data.get("daily_stats", {}),
                )
                logger.info("loaded_analytics_data")
            except Exception as e:
                logger.error("load_analytics_error", error=str(e))

    def _save_data(self) -> None:
        """Save analytics data to storage."""
        try:
            data = {
                "hourly_stats": dict(self._hourly_stats),
                "daily_stats": dict(self._daily_stats),
                "updated_at": datetime.utcnow().isoformat(),
            }
            data_file = self.storage_path / "analytics_data.json"
            data_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error("save_analytics_error", error=str(e))

    def start_conversation(
        self,
        conversation_id: str,
        channel: str,
    ) -> ConversationAnalytics:
        """Start tracking a new conversation."""
        now = datetime.utcnow()
        analytics = ConversationAnalytics(
            conversation_id=conversation_id,
            channel=channel,
            started_at=now,
        )
        self.conversations[conversation_id] = analytics

        # Update stats
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")
        self._hourly_stats[hour_key]["conversations"] += 1
        self._daily_stats[day_key]["conversations"] += 1

        logger.debug("conversation_tracking_started", conversation_id=conversation_id)
        return analytics

    def record_message(
        self,
        conversation_id: str,
        direction: str,
        content: str,
        response_time_ms: float = 0,
        sentiment_score: float = 0,
    ) -> None:
        """Record a message in a conversation."""
        if conversation_id not in self.conversations:
            return

        conv = self.conversations[conversation_id]
        conv.message_count += 1

        if direction == "inbound":
            conv.customer_messages += 1
        else:
            conv.agent_messages += 1

        # Update response time average
        if response_time_ms > 0:
            current_avg = conv.avg_response_time_ms
            count = conv.agent_messages
            conv.avg_response_time_ms = (current_avg * (count - 1) + response_time_ms) / count

        # Record sentiment
        if sentiment_score != 0:
            conv.sentiment_scores.append(sentiment_score)

        # Extract keywords and service interests
        self._extract_insights(conv, content)

        # Update stats
        now = datetime.utcnow()
        hour_key = now.strftime("%Y-%m-%d-%H")
        day_key = now.strftime("%Y-%m-%d")
        self._hourly_stats[hour_key]["messages"] += 1
        self._daily_stats[day_key]["messages"] += 1

    def _extract_insights(self, conv: ConversationAnalytics, content: str) -> None:
        """Extract service interests and keywords from message content."""
        content_lower = content.lower()

        # Service interest detection
        service_keywords = {
            ServiceInterest.KITCHEN_EXTENSION: [
                "kitchen",
                "extension",
                "open plan",
                "rear extension",
            ],
            ServiceInterest.LOFT_CONVERSION: ["loft", "attic", "dormer", "mansard"],
            ServiceInterest.BATHROOM: ["bathroom", "en-suite", "ensuite", "wet room", "shower"],
            ServiceInterest.FULL_RENOVATION: [
                "full renovation",
                "whole house",
                "complete renovation",
                "gut renovation",
            ],
            ServiceInterest.BASEMENT: ["basement", "cellar", "underpinning"],
            ServiceInterest.GARDEN: ["garden", "landscaping", "patio", "decking"],
        }

        for service, keywords in service_keywords.items():
            if (
                any(kw in content_lower for kw in keywords)
                and service not in conv.service_interests
            ):
                conv.service_interests.append(service)

        # Postcode extraction
        import re

        postcode_match = re.search(r"\b(NW\d{1,2}|N\d{1,2}|W\d{1,2})\b", content.upper())
        if postcode_match and not conv.postcode_area:
            conv.postcode_area = postcode_match.group(1)

        # Common keywords
        important_keywords = [
            "price",
            "cost",
            "budget",
            "quote",
            "timeline",
            "planning",
            "survey",
            "visit",
            "appointment",
            "urgent",
            "asap",
            "quickly",
        ]
        for kw in important_keywords:
            if kw in content_lower and kw not in conv.keywords:
                conv.keywords.append(kw)

    def end_conversation(
        self,
        conversation_id: str,
        outcome: ConversationOutcome,
        drop_off_point: str | None = None,
    ) -> None:
        """Mark conversation as ended with outcome."""
        if conversation_id not in self.conversations:
            return

        conv = self.conversations[conversation_id]
        conv.ended_at = datetime.utcnow()
        conv.outcome = outcome
        conv.drop_off_point = drop_off_point

        # Update booking stats if applicable
        if outcome == ConversationOutcome.BOOKING_MADE:
            day_key = conv.started_at.strftime("%Y-%m-%d")
            hour_key = conv.started_at.strftime("%Y-%m-%d-%H")
            self._hourly_stats[hour_key]["bookings"] += 1
            self._daily_stats[day_key]["bookings"] += 1

        # Update sentiment stats
        if conv.sentiment_scores:
            day_key = conv.started_at.strftime("%Y-%m-%d")
            self._daily_stats[day_key]["sentiment_sum"] += conv.avg_sentiment
            sentiment_count = self._daily_stats[day_key].get("sentiment_count", 0) + 1
            self._daily_stats[day_key]["sentiment_count"] = sentiment_count
            self._daily_stats[day_key]["avg_sentiment"] = (
                self._daily_stats[day_key]["sentiment_sum"] / sentiment_count
            )

        self._save_data()

        logger.info(
            "conversation_ended",
            conversation_id=conversation_id,
            outcome=outcome.value,
            duration_seconds=conv.duration_seconds,
        )

    def get_peak_hours_analysis(self, days: int = 30) -> dict:
        """Analyze peak inquiry hours."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        hourly_totals = defaultdict(int)

        for hour_key, stats in self._hourly_stats.items():
            if hour_key >= cutoff_str:
                hour = int(hour_key.split("-")[-1])
                hourly_totals[hour] += stats["conversations"]

        # Find peak hours
        sorted_hours = sorted(hourly_totals.items(), key=lambda x: x[1], reverse=True)

        return {
            "peak_hours": [h for h, _ in sorted_hours[:3]],
            "quiet_hours": [h for h, _ in sorted_hours[-3:]],
            "hourly_distribution": dict(hourly_totals),
            "analysis_period_days": days,
        }

    def get_service_interest_breakdown(self, days: int = 30) -> dict:
        """Get breakdown of service interests."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        interest_counts = Counter()
        for conv in self.conversations.values():
            if conv.started_at >= cutoff:
                for interest in conv.service_interests:
                    interest_counts[interest.value] += 1

        total = sum(interest_counts.values())

        return {
            "breakdown": {
                service: {
                    "count": count,
                    "percentage": round(count / total * 100, 1) if total > 0 else 0,
                }
                for service, count in interest_counts.most_common()
            },
            "total_conversations": total,
            "analysis_period_days": days,
        }

    def get_sentiment_trends(self, days: int = 30) -> dict:
        """Get sentiment trends over time."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        daily_sentiment = {}
        for day_key, stats in self._daily_stats.items():
            if day_key >= cutoff_str:
                daily_sentiment[day_key] = stats.get("avg_sentiment", 0)

        values = list(daily_sentiment.values())

        return {
            "daily_sentiment": daily_sentiment,
            "avg_sentiment": sum(values) / len(values) if values else 0,
            "trend": "improving" if len(values) > 1 and values[-1] > values[0] else "stable",
            "analysis_period_days": days,
        }

    def get_drop_off_analysis(self, days: int = 30) -> dict:
        """Analyze where conversations drop off."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        drop_off_points = Counter()
        outcome_counts = Counter()

        for conv in self.conversations.values():
            if conv.started_at >= cutoff and conv.outcome:
                outcome_counts[conv.outcome.value] += 1
                if conv.outcome == ConversationOutcome.DROPPED_OFF and conv.drop_off_point:
                    drop_off_points[conv.drop_off_point] += 1

        return {
            "outcomes": dict(outcome_counts),
            "drop_off_points": dict(drop_off_points.most_common(10)),
            "conversion_rate": round(
                outcome_counts.get("booking_made", 0) / sum(outcome_counts.values()) * 100, 1
            )
            if outcome_counts
            else 0,
            "analysis_period_days": days,
        }

    def get_postcode_distribution(self, days: int = 30) -> dict:
        """Get geographic distribution of inquiries."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        postcode_counts = Counter()
        for conv in self.conversations.values():
            if conv.started_at >= cutoff and conv.postcode_area:
                postcode_counts[conv.postcode_area] += 1

        return {
            "distribution": dict(postcode_counts.most_common(20)),
            "top_areas": [pc for pc, _ in postcode_counts.most_common(5)],
            "analysis_period_days": days,
        }

    def get_response_time_analysis(self, days: int = 30) -> dict:
        """Analyze response times."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        response_times = []
        for conv in self.conversations.values():
            if conv.started_at >= cutoff and conv.avg_response_time_ms > 0:
                response_times.append(conv.avg_response_time_ms)

        if not response_times:
            return {"avg_response_time_ms": 0, "analysis_period_days": days}

        response_times.sort()

        return {
            "avg_response_time_ms": round(sum(response_times) / len(response_times), 2),
            "median_response_time_ms": round(response_times[len(response_times) // 2], 2),
            "p95_response_time_ms": round(response_times[int(len(response_times) * 0.95)], 2),
            "min_response_time_ms": round(min(response_times), 2),
            "max_response_time_ms": round(max(response_times), 2),
            "analysis_period_days": days,
        }

    def get_common_questions(self, days: int = 30, top_n: int = 10) -> dict:
        """Get most common keywords/questions."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        keyword_counts = Counter()
        for conv in self.conversations.values():
            if conv.started_at >= cutoff:
                for kw in conv.keywords:
                    keyword_counts[kw] += 1

        return {
            "common_topics": dict(keyword_counts.most_common(top_n)),
            "analysis_period_days": days,
        }

    def get_full_dashboard_report(self, days: int = 30) -> dict:
        """Get comprehensive dashboard report."""
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "period_days": days,
            "peak_hours": self.get_peak_hours_analysis(days),
            "service_interests": self.get_service_interest_breakdown(days),
            "sentiment_trends": self.get_sentiment_trends(days),
            "drop_off_analysis": self.get_drop_off_analysis(days),
            "postcode_distribution": self.get_postcode_distribution(days),
            "response_times": self.get_response_time_analysis(days),
            "common_topics": self.get_common_questions(days),
        }


# Global instance
analytics_service = AnalyticsService()

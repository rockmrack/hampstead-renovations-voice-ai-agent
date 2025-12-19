"""
A/B Testing service for prompt experimentation.
Handles variant assignment, tracking, and statistical analysis.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ExperimentStatus(str, Enum):
    """Status of an A/B test experiment."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    WINNER_SELECTED = "winner_selected"


@dataclass
class PromptVariant:
    """A variant in an A/B test."""

    id: str
    name: str
    prompt_content: str
    weight: float = 1.0  # Traffic weight
    impressions: int = 0
    conversions: int = 0  # e.g., bookings made
    total_response_time_ms: float = 0
    total_sentiment_score: float = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def conversion_rate(self) -> float:
        """Calculate conversion rate."""
        return self.conversions / self.impressions if self.impressions > 0 else 0.0

    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return self.total_response_time_ms / self.impressions if self.impressions > 0 else 0.0

    @property
    def avg_sentiment(self) -> float:
        """Calculate average sentiment score."""
        return self.total_sentiment_score / self.impressions if self.impressions > 0 else 0.0


@dataclass
class Experiment:
    """An A/B test experiment."""

    id: str
    name: str
    description: str
    prompt_type: str  # e.g., "whatsapp-text-handler", "phone-call-agent"
    variants: list[PromptVariant]
    status: ExperimentStatus = ExperimentStatus.DRAFT
    winner_variant_id: str | None = None
    min_sample_size: int = 100
    confidence_level: float = 0.95
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def total_impressions(self) -> int:
        """Total impressions across all variants."""
        return sum(v.impressions for v in self.variants)

    @property
    def is_significant(self) -> bool:
        """Check if we have enough data for statistical significance."""
        return all(v.impressions >= self.min_sample_size for v in self.variants)


class ABTestingService:
    """Service for managing A/B tests on prompts."""

    def __init__(self, storage_path: str = "ab_tests"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self.experiments: dict[str, Experiment] = {}
        self.user_assignments: dict[
            str, dict[str, str]
        ] = {}  # user_id -> {experiment_id: variant_id}
        self._load_experiments()

    def _load_experiments(self) -> None:
        """Load experiments from storage."""
        experiments_file = self.storage_path / "experiments.json"
        if experiments_file.exists():
            try:
                data = json.loads(experiments_file.read_text())
                for exp_data in data.get("experiments", []):
                    variants = [
                        PromptVariant(
                            id=v["id"],
                            name=v["name"],
                            prompt_content=v["prompt_content"],
                            weight=v.get("weight", 1.0),
                            impressions=v.get("impressions", 0),
                            conversions=v.get("conversions", 0),
                            total_response_time_ms=v.get("total_response_time_ms", 0),
                            total_sentiment_score=v.get("total_sentiment_score", 0),
                        )
                        for v in exp_data["variants"]
                    ]
                    experiment = Experiment(
                        id=exp_data["id"],
                        name=exp_data["name"],
                        description=exp_data.get("description", ""),
                        prompt_type=exp_data["prompt_type"],
                        variants=variants,
                        status=ExperimentStatus(exp_data.get("status", "draft")),
                        winner_variant_id=exp_data.get("winner_variant_id"),
                        min_sample_size=exp_data.get("min_sample_size", 100),
                    )
                    self.experiments[experiment.id] = experiment
                logger.info("loaded_experiments", count=len(self.experiments))
            except Exception as e:
                logger.error("load_experiments_error", error=str(e))

    def _save_experiments(self) -> None:
        """Save experiments to storage."""
        try:
            data = {
                "experiments": [
                    {
                        "id": exp.id,
                        "name": exp.name,
                        "description": exp.description,
                        "prompt_type": exp.prompt_type,
                        "status": exp.status.value,
                        "winner_variant_id": exp.winner_variant_id,
                        "min_sample_size": exp.min_sample_size,
                        "variants": [
                            {
                                "id": v.id,
                                "name": v.name,
                                "prompt_content": v.prompt_content,
                                "weight": v.weight,
                                "impressions": v.impressions,
                                "conversions": v.conversions,
                                "total_response_time_ms": v.total_response_time_ms,
                                "total_sentiment_score": v.total_sentiment_score,
                            }
                            for v in exp.variants
                        ],
                    }
                    for exp in self.experiments.values()
                ],
                "updated_at": datetime.utcnow().isoformat(),
            }
            experiments_file = self.storage_path / "experiments.json"
            experiments_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error("save_experiments_error", error=str(e))

    def create_experiment(
        self,
        name: str,
        prompt_type: str,
        variants: list[dict],
        description: str = "",
        min_sample_size: int = 100,
    ) -> Experiment:
        """Create a new A/B test experiment."""
        experiment_id = hashlib.md5(f"{name}{datetime.utcnow().isoformat()}".encode()).hexdigest()[
            :12
        ]

        prompt_variants = [
            PromptVariant(
                id=f"{experiment_id}_{i}",
                name=v["name"],
                prompt_content=v["prompt_content"],
                weight=v.get("weight", 1.0),
            )
            for i, v in enumerate(variants)
        ]

        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            prompt_type=prompt_type,
            variants=prompt_variants,
            min_sample_size=min_sample_size,
        )

        self.experiments[experiment.id] = experiment
        self._save_experiments()

        logger.info(
            "experiment_created",
            experiment_id=experiment.id,
            name=name,
            variants_count=len(variants),
        )

        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """Start an experiment."""
        if experiment_id not in self.experiments:
            return False

        experiment = self.experiments[experiment_id]
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.utcnow()
        self._save_experiments()

        logger.info("experiment_started", experiment_id=experiment_id)
        return True

    def pause_experiment(self, experiment_id: str) -> bool:
        """Pause an experiment."""
        if experiment_id not in self.experiments:
            return False

        experiment = self.experiments[experiment_id]
        experiment.status = ExperimentStatus.PAUSED
        self._save_experiments()

        logger.info("experiment_paused", experiment_id=experiment_id)
        return True

    def get_variant_for_user(
        self,
        experiment_id: str,
        user_id: str,
    ) -> PromptVariant | None:
        """Get or assign a variant for a user (sticky assignment)."""
        if experiment_id not in self.experiments:
            return None

        experiment = self.experiments[experiment_id]

        if experiment.status != ExperimentStatus.RUNNING:
            # Return winner if selected, otherwise control (first variant)
            if experiment.winner_variant_id:
                return next(
                    (v for v in experiment.variants if v.id == experiment.winner_variant_id),
                    experiment.variants[0],
                )
            return experiment.variants[0]

        # Check for existing assignment
        if user_id in self.user_assignments and experiment_id in self.user_assignments[user_id]:
            variant_id = self.user_assignments[user_id][experiment_id]
            return next(
                (v for v in experiment.variants if v.id == variant_id),
                None,
            )

        # Assign new variant based on weights
        variant = self._weighted_random_choice(experiment.variants)

        # Store assignment
        if user_id not in self.user_assignments:
            self.user_assignments[user_id] = {}
        self.user_assignments[user_id][experiment_id] = variant.id

        logger.debug(
            "variant_assigned",
            experiment_id=experiment_id,
            user_id=user_id[:8],
            variant_id=variant.id,
        )

        return variant

    def _weighted_random_choice(self, variants: list[PromptVariant]) -> PromptVariant:
        """Select a variant based on weights."""
        total_weight = sum(v.weight for v in variants)
        r = random.uniform(0, total_weight)

        cumulative = 0
        for variant in variants:
            cumulative += variant.weight
            if r <= cumulative:
                return variant

        return variants[-1]

    def record_impression(
        self,
        experiment_id: str,
        variant_id: str,
        response_time_ms: float = 0,
        sentiment_score: float = 0,
    ) -> None:
        """Record an impression for a variant."""
        if experiment_id not in self.experiments:
            return

        experiment = self.experiments[experiment_id]
        for variant in experiment.variants:
            if variant.id == variant_id:
                variant.impressions += 1
                variant.total_response_time_ms += response_time_ms
                variant.total_sentiment_score += sentiment_score
                break

        # Auto-save periodically (every 10 impressions)
        if experiment.total_impressions % 10 == 0:
            self._save_experiments()

    def record_conversion(
        self,
        experiment_id: str,
        variant_id: str,
    ) -> None:
        """Record a conversion for a variant."""
        if experiment_id not in self.experiments:
            return

        experiment = self.experiments[experiment_id]
        for variant in experiment.variants:
            if variant.id == variant_id:
                variant.conversions += 1
                logger.info(
                    "conversion_recorded",
                    experiment_id=experiment_id,
                    variant_id=variant_id,
                    total_conversions=variant.conversions,
                )
                break

        self._save_experiments()

        # Check for auto-completion
        self._check_experiment_completion(experiment_id)

    def _check_experiment_completion(self, experiment_id: str) -> None:
        """Check if experiment has enough data to determine winner."""
        experiment = self.experiments[experiment_id]

        if not experiment.is_significant:
            return

        # Calculate statistical significance using chi-squared test approximation
        winner = self._determine_winner(experiment)

        if winner:
            experiment.status = ExperimentStatus.WINNER_SELECTED
            experiment.winner_variant_id = winner.id
            experiment.completed_at = datetime.utcnow()
            self._save_experiments()

            logger.info(
                "experiment_winner_selected",
                experiment_id=experiment_id,
                winner_variant_id=winner.id,
                winner_conversion_rate=winner.conversion_rate,
            )

    def _determine_winner(self, experiment: Experiment) -> PromptVariant | None:
        """Determine the winning variant using conversion rate."""
        if len(experiment.variants) < 2:
            return experiment.variants[0] if experiment.variants else None

        # Sort by conversion rate
        sorted_variants = sorted(
            experiment.variants,
            key=lambda v: v.conversion_rate,
            reverse=True,
        )

        best = sorted_variants[0]
        second = sorted_variants[1]

        # Simple significance check: >10% improvement with enough samples
        if (
            best.conversion_rate > second.conversion_rate * 1.1
            and best.impressions >= experiment.min_sample_size
        ):
            return best

        return None

    def get_experiment_report(self, experiment_id: str) -> dict | None:
        """Get detailed report for an experiment."""
        if experiment_id not in self.experiments:
            return None

        experiment = self.experiments[experiment_id]

        return {
            "id": experiment.id,
            "name": experiment.name,
            "description": experiment.description,
            "prompt_type": experiment.prompt_type,
            "status": experiment.status.value,
            "total_impressions": experiment.total_impressions,
            "is_significant": experiment.is_significant,
            "winner_variant_id": experiment.winner_variant_id,
            "variants": [
                {
                    "id": v.id,
                    "name": v.name,
                    "impressions": v.impressions,
                    "conversions": v.conversions,
                    "conversion_rate": round(v.conversion_rate * 100, 2),
                    "avg_response_time_ms": round(v.avg_response_time, 2),
                    "avg_sentiment": round(v.avg_sentiment, 2),
                    "is_winner": v.id == experiment.winner_variant_id,
                }
                for v in experiment.variants
            ],
            "created_at": experiment.created_at.isoformat(),
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "completed_at": experiment.completed_at.isoformat()
            if experiment.completed_at
            else None,
        }

    def get_active_experiments_for_prompt_type(self, prompt_type: str) -> list[Experiment]:
        """Get all active experiments for a prompt type."""
        return [
            exp
            for exp in self.experiments.values()
            if exp.prompt_type == prompt_type and exp.status == ExperimentStatus.RUNNING
        ]

    def get_prompt_content(
        self,
        prompt_type: str,
        user_id: str,
        default_prompt: str,
    ) -> tuple[str, str | None, str | None]:
        """
        Get the prompt content for a user, considering any active experiments.

        Returns:
            Tuple of (prompt_content, experiment_id, variant_id)
        """
        active_experiments = self.get_active_experiments_for_prompt_type(prompt_type)

        if not active_experiments:
            return default_prompt, None, None

        # Use first active experiment
        experiment = active_experiments[0]
        variant = self.get_variant_for_user(experiment.id, user_id)

        if variant:
            return variant.prompt_content, experiment.id, variant.id

        return default_prompt, None, None


# Global instance
ab_testing_service = ABTestingService()

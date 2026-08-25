from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .aesthetic_integrity import integrity_checks
from .aesthetic_visual import visual_checks
from .models import EditPlan, QCCheck, Transcript
from .presets import get_style


@dataclass(slots=True)
class AestheticReport:
    checks: list[QCCheck]
    metrics: dict[str, Any]
    recommendations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(not item.passed and item.severity == "error" for item in self.checks)

    @property
    def score(self) -> int:
        penalty = sum(
            18 if item.severity == "error" else 6 if item.severity == "warning" else 2
            for item in self.checks
            if not item.passed
        )
        return max(0, 100 - penalty)

    @property
    def grade(self) -> str:
        return "A" if self.score >= 92 else "B" if self.score >= 82 else "C" if self.score >= 70 else "D" if self.score >= 55 else "F"

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "grade": self.grade,
            "checks": [asdict(item) for item in self.checks],
            "metrics": self.metrics,
            "recommendations": self.recommendations,
        }


def analyze_aesthetics(
    plan: EditPlan,
    *,
    transcript: Transcript | None = None,
    source_transcript: Transcript | None = None,
) -> AestheticReport:
    try:
        profile = get_style(plan.style_profile, plan.intensity)
    except KeyError:
        profile = get_style("authority", plan.intensity)
    checks: list[QCCheck] = []
    metrics: dict[str, Any] = {}
    recommendations: list[str] = []
    visual_checks(plan, profile, checks, metrics, recommendations)
    integrity_checks(
        plan,
        transcript=transcript or source_transcript,
        source_transcript=source_transcript,
        checks=checks,
        metrics=metrics,
        recommendations=recommendations,
    )
    return AestheticReport(checks, metrics, list(dict.fromkeys(recommendations)))

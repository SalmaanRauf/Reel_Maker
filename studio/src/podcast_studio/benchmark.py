from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bridge import load_edit_plan, run_quality_control
from .exceptions import ValidationError
from .style_analysis import StyleFingerprint, compare_fingerprints, fingerprint_plan
from .util import dump_json


@dataclass(slots=True)
class BenchmarkThresholds:
    minimum_qc_score: float = 80.0
    minimum_style_match: float = 65.0
    maximum_visual_concurrency: int = 3
    maximum_broll_coverage: float = 0.45
    maximum_overlay_coverage: float = 0.55

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "BenchmarkThresholds":
        if not payload:
            return cls()
        allowed = cls.__dataclass_fields__
        return cls(**{key: value for key, value in payload.items() if key in allowed})

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(slots=True)
class BenchmarkCaseResult:
    case_id: str
    passed: bool
    checks: list[dict[str, Any]]
    metrics: dict[str, Any]
    artifacts: dict[str, str]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "checks": self.checks,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "errors": self.errors,
        }


def run_benchmark(manifest_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source = Path(manifest_path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Benchmark manifest not found: {source}")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    cases = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValidationError("Benchmark manifest requires a non-empty `cases` array")
    defaults = BenchmarkThresholds.from_dict(manifest.get("thresholds"))
    results: list[BenchmarkCaseResult] = []
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            results.append(BenchmarkCaseResult(f"case-{index + 1}", False, [], {}, {}, ["Case is not an object"]))
            continue
        results.append(run_case(raw_case, manifest_directory=source.parent, default_thresholds=defaults))
    passed = sum(item.passed for item in results)
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest": str(source),
        "summary": {
            "case_count": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": passed / len(results),
        },
        "results": [item.to_dict() for item in results],
    }
    dump_json(report, output_path)
    return report


def run_case(
    case: dict[str, Any],
    *,
    manifest_directory: Path,
    default_thresholds: BenchmarkThresholds | None = None,
) -> BenchmarkCaseResult:
    case_id = str(case.get("id") or "unnamed-case")
    thresholds = BenchmarkThresholds.from_dict(
        {**(default_thresholds.to_dict() if default_thresholds else {}), **(case.get("thresholds") or {})}
    )
    checks: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    artifacts: dict[str, str] = {}
    errors: list[str] = []

    try:
        plan_path = _resolve(manifest_directory, case.get("plan"), required=True)
        artifacts["plan"] = str(plan_path)
        load_edit_plan(plan_path)
        checks.append(_check("plan_valid", True, "Edit plan parsed successfully"))
        fingerprint = fingerprint_plan(plan_path)
        metrics["fingerprint"] = fingerprint.to_dict()
        checks.extend(
            [
                _check(
                    "visual_concurrency",
                    fingerprint.maximum_visual_concurrency <= thresholds.maximum_visual_concurrency,
                    f"{fingerprint.maximum_visual_concurrency} <= {thresholds.maximum_visual_concurrency}",
                ),
                _check(
                    "broll_coverage",
                    fingerprint.broll_coverage <= thresholds.maximum_broll_coverage,
                    f"{fingerprint.broll_coverage:.3f} <= {thresholds.maximum_broll_coverage:.3f}",
                ),
                _check(
                    "overlay_coverage",
                    fingerprint.overlay_coverage <= thresholds.maximum_overlay_coverage,
                    f"{fingerprint.overlay_coverage:.3f} <= {thresholds.maximum_overlay_coverage:.3f}",
                ),
            ]
        )
    except Exception as exc:
        errors.append(f"plan: {exc}")
        fingerprint = None
        checks.append(_check("plan_valid", False, str(exc)))

    render_value = case.get("render")
    if render_value:
        try:
            render_path = _resolve(manifest_directory, render_value, required=True)
            artifacts["render"] = str(render_path)
            qc = run_quality_control(render_path, report_path=None)
            metrics["qc"] = qc
            qc_score = _qc_score(qc)
            metrics["qc_score"] = qc_score
            checks.append(
                _check(
                    "qc_score",
                    qc_score >= thresholds.minimum_qc_score,
                    f"{qc_score:.2f} >= {thresholds.minimum_qc_score:.2f}",
                )
            )
        except Exception as exc:
            errors.append(f"render: {exc}")
            checks.append(_check("qc_score", False, str(exc)))
    else:
        checks.append(_check("render_present", False, "No render supplied; technical/aesthetic render QC was skipped", required=False))

    reference_value = case.get("reference_style")
    if reference_value and fingerprint is not None:
        try:
            reference_path = _resolve(manifest_directory, reference_value, required=True)
            artifacts["reference_style"] = str(reference_path)
            payload = json.loads(reference_path.read_text(encoding="utf-8"))
            reference = StyleFingerprint(**{key: value for key, value in payload.items() if key in StyleFingerprint.__dataclass_fields__})
            comparison = compare_fingerprints(reference, fingerprint)
            metrics["style_comparison"] = comparison
            style_score = float(comparison["style_match_score"])
            checks.append(
                _check(
                    "style_match",
                    style_score >= thresholds.minimum_style_match,
                    f"{style_score:.2f} >= {thresholds.minimum_style_match:.2f}",
                )
            )
        except Exception as exc:
            errors.append(f"reference_style: {exc}")
            checks.append(_check("style_match", False, str(exc)))

    required_failures = [item for item in checks if item["required"] and not item["passed"]]
    return BenchmarkCaseResult(
        case_id=case_id,
        passed=not required_failures and not errors,
        checks=checks,
        metrics=metrics,
        artifacts=artifacts,
        errors=errors,
    )


def build_blind_review_packet(
    candidates: list[dict[str, Any]],
    output_path: str | Path,
    *,
    seed: str = "podcast-studio",
) -> dict[str, Any]:
    if len(candidates) < 2:
        raise ValidationError("Blind review requires at least two candidate renders")
    normalized = []
    for index, item in enumerate(candidates):
        path = Path(str(item.get("path") or "")).expanduser().resolve()
        if not path.is_file():
            raise ValidationError(f"Blind-review media not found: {path}")
        normalized.append(
            {
                "private_id": str(item.get("id") or f"candidate-{index + 1}"),
                "path": str(path),
                "sha256": _sha256(path),
            }
        )
    randomizer = random.Random(hashlib.sha256(seed.encode("utf-8")).digest())
    randomizer.shuffle(normalized)
    labels = [f"Version {chr(65 + index)}" for index in range(len(normalized))]
    entries = [
        {"label": label, "path": item["path"], "sha256": item["sha256"]}
        for label, item in zip(labels, normalized, strict=True)
    ]
    key = {label: item["private_id"] for label, item in zip(labels, normalized, strict=True)}
    packet = {
        "schema_version": 1,
        "seed_hash": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "entries": entries,
        "rubric": [
            "Hook clarity and truthfulness",
            "Standalone narrative coherence",
            "Pacing and cut purpose",
            "Caption readability and hierarchy",
            "Framing and camera choices",
            "B-roll/proof specificity and timing",
            "Audio clarity and sound-design restraint",
            "Source fidelity and qualifier preservation",
            "Overall preference",
        ],
        "private_answer_key": key,
    }
    dump_json(packet, output_path)
    return packet


def _check(name: str, passed: bool, detail: str, *, required: bool = True) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "required": required, "detail": detail}


def _resolve(directory: Path, value: Any, *, required: bool) -> Path:
    if value is None:
        if required:
            raise ValidationError("Required artifact path is missing")
        return directory
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = directory / path
    path = path.resolve()
    if required and not path.is_file():
        raise ValidationError(f"Artifact not found: {path}")
    return path


def _qc_score(payload: dict[str, Any]) -> float:
    for key in ("score", "aesthetic_score", "quality_score", "overall_score"):
        if payload.get(key) is not None:
            return float(payload[key])
    if payload.get("passed") is True or payload.get("status") == "passed":
        return 100.0
    if payload.get("passed") is False or payload.get("status") == "failed":
        return 0.0
    failures = payload.get("failures") or payload.get("issues") or []
    return max(0.0, 100.0 - 12.5 * len(failures))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

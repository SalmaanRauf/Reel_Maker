from __future__ import annotations

import json
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .bridge import load_edit_plan
from .exceptions import DependencyError, ValidationError
from .process import run_command
from .util import dump_json
from .workspace import probe_media

_PTS_TIME = re.compile(r"pts_time:(?P<time>-?\d+(?:\.\d+)?)")


@dataclass(slots=True)
class StyleFingerprint:
    duration: float
    cuts_per_minute: float = 0.0
    median_shot_seconds: float = 0.0
    zooms_per_minute: float = 0.0
    text_events_per_minute: float = 0.0
    broll_events_per_minute: float = 0.0
    proof_events_per_minute: float = 0.0
    sfx_events_per_minute: float = 0.0
    transition_events_per_minute: float = 0.0
    average_zoom_delta: float = 0.0
    caption_words_per_group: float = 0.0
    caption_changes_per_minute: float = 0.0
    overlay_coverage: float = 0.0
    broll_coverage: float = 0.0
    maximum_visual_concurrency: int = 0
    cadence_variability: float = 0.0
    source: str | None = None
    method: str = "plan-events-v1"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration": round(self.duration, 4),
            "cuts_per_minute": round(self.cuts_per_minute, 4),
            "median_shot_seconds": round(self.median_shot_seconds, 4),
            "zooms_per_minute": round(self.zooms_per_minute, 4),
            "text_events_per_minute": round(self.text_events_per_minute, 4),
            "broll_events_per_minute": round(self.broll_events_per_minute, 4),
            "proof_events_per_minute": round(self.proof_events_per_minute, 4),
            "sfx_events_per_minute": round(self.sfx_events_per_minute, 4),
            "transition_events_per_minute": round(self.transition_events_per_minute, 4),
            "average_zoom_delta": round(self.average_zoom_delta, 4),
            "caption_words_per_group": round(self.caption_words_per_group, 4),
            "caption_changes_per_minute": round(self.caption_changes_per_minute, 4),
            "overlay_coverage": round(self.overlay_coverage, 4),
            "broll_coverage": round(self.broll_coverage, 4),
            "maximum_visual_concurrency": self.maximum_visual_concurrency,
            "cadence_variability": round(self.cadence_variability, 4),
            "source": self.source,
            "method": self.method,
            "notes": self.notes,
        }


def fingerprint_plan(plan_path: str | Path) -> StyleFingerprint:
    plan = _mapping(load_edit_plan(plan_path))
    duration = _plan_duration(plan)
    if duration <= 0:
        raise ValidationError("Edit plan duration could not be determined")
    minute = duration / 60.0
    segments = _list(plan, "segments", "clips", "timeline")
    transitions = _list(plan, "transitions")
    motion = _list(plan, "motion", "motion_events", "keyframes")
    captions = _list(plan, "captions", "caption_groups")
    overlays = _list(plan, "overlays", "graphics", "text_events")
    broll = _list(plan, "broll", "broll_events", "media_overlays")
    proof = _list(plan, "proof", "proof_cards", "evidence_events")
    audio = _list(plan, "audio_events", "sound_events", "sfx")

    segment_ranges = [_range(item) for item in segments]
    segment_ranges = [item for item in segment_ranges if item is not None]
    shot_durations = [end - start for start, end in segment_ranges if end > start]
    cut_count = max(0, len(segment_ranges) - 1)
    if transitions:
        cut_count = max(cut_count, len(transitions))

    zoom_deltas = []
    zoom_count = 0
    for item in motion:
        payload = _mapping(item)
        kind = str(payload.get("kind") or payload.get("type") or payload.get("property") or "").lower()
        start_scale = _float(payload.get("start_scale") or payload.get("from_scale") or payload.get("scale_from") or 1.0, 1.0)
        end_scale = _float(payload.get("end_scale") or payload.get("to_scale") or payload.get("scale_to") or payload.get("scale") or 1.0, 1.0)
        if "zoom" in kind or "scale" in kind or abs(end_scale - start_scale) >= 0.012:
            zoom_count += 1
            zoom_deltas.append(abs(end_scale - start_scale))

    text_events = [item for item in overlays if _event_kind(item) in {"text", "title", "headline", "lower_third", "label", "number", "quote"}]
    if not text_events and overlays:
        text_events = overlays
    sfx_events = [item for item in audio if _event_kind(item) in {"sfx", "sound_effect", "beep", "accent"}]
    caption_word_counts = []
    caption_ranges = []
    for item in captions:
        payload = _mapping(item)
        words = payload.get("words")
        if isinstance(words, list):
            caption_word_counts.append(len(words))
        else:
            text = str(payload.get("text") or "")
            if text:
                caption_word_counts.append(len(text.split()))
        event_range = _range(payload)
        if event_range:
            caption_ranges.append(event_range)

    overlay_ranges = [event_range for item in [*overlays, *proof] if (event_range := _range(item))]
    broll_ranges = [event_range for item in broll if (event_range := _range(item))]
    all_visual_ranges = [
        *(event_range for item in motion if (event_range := _range(item))),
        *overlay_ranges,
        *broll_ranges,
        *caption_ranges,
    ]
    cadence_points = sorted(
        {
            point
            for event_range in [*segment_ranges, *all_visual_ranges]
            for point in event_range
            if 0 <= point <= duration
        }
    )
    cadence_intervals = [right - left for left, right in zip(cadence_points, cadence_points[1:]) if right > left]
    cadence_variability = statistics.pstdev(cadence_intervals) / statistics.mean(cadence_intervals) if len(cadence_intervals) >= 2 and statistics.mean(cadence_intervals) else 0.0

    notes = []
    if not captions:
        notes.append("No caption events were found in the serialized plan.")
    if not motion:
        notes.append("No explicit motion events were found; renderer-internal movement may be omitted.")
    return StyleFingerprint(
        duration=duration,
        cuts_per_minute=cut_count / minute,
        median_shot_seconds=statistics.median(shot_durations) if shot_durations else duration,
        zooms_per_minute=zoom_count / minute,
        text_events_per_minute=len(text_events) / minute,
        broll_events_per_minute=len(broll) / minute,
        proof_events_per_minute=len(proof) / minute,
        sfx_events_per_minute=len(sfx_events) / minute,
        transition_events_per_minute=len(transitions) / minute,
        average_zoom_delta=statistics.mean(zoom_deltas) if zoom_deltas else 0.0,
        caption_words_per_group=statistics.mean(caption_word_counts) if caption_word_counts else 0.0,
        caption_changes_per_minute=len(captions) / minute,
        overlay_coverage=_coverage(overlay_ranges, duration),
        broll_coverage=_coverage(broll_ranges, duration),
        maximum_visual_concurrency=_maximum_concurrency(all_visual_ranges),
        cadence_variability=cadence_variability,
        source=str(Path(plan_path).resolve()),
    )


def analyze_reference_video(
    video_path: str | Path,
    output: str | Path | None = None,
    *,
    scene_threshold: float = 0.32,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    annotations: str | Path | None = None,
) -> StyleFingerprint:
    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Reference video not found: {source}")
    probe = probe_media(source, ffprobe=ffprobe)
    duration = float(probe.get("duration") or 0.0)
    if duration <= 0:
        raise ValidationError("Reference duration could not be determined")
    scene_times = detect_scene_changes(source, threshold=scene_threshold, ffmpeg=ffmpeg)
    boundaries = [0.0, *[time for time in scene_times if 0 < time < duration], duration]
    holds = [right - left for left, right in zip(boundaries, boundaries[1:]) if right > left]
    minute = duration / 60.0
    fingerprint = StyleFingerprint(
        duration=duration,
        cuts_per_minute=len(scene_times) / minute,
        median_shot_seconds=statistics.median(holds) if holds else duration,
        cadence_variability=statistics.pstdev(holds) / statistics.mean(holds) if len(holds) >= 2 and statistics.mean(holds) else 0.0,
        source=str(source),
        method="render-scene-detection-v1",
        notes=[
            "Scene detection measures hard visual changes only; provide annotations for zoom, text, B-roll, proof, caption, transition, and SFX classification."
        ],
    )
    if annotations:
        fingerprint = apply_annotations(fingerprint, annotations)
    if output:
        dump_json(fingerprint.to_dict(), output)
    return fingerprint


def detect_scene_changes(video_path: str | Path, *, threshold: float = 0.32, ffmpeg: str = "ffmpeg") -> list[float]:
    if not 0 < threshold < 1:
        raise ValidationError("Scene threshold must fall between 0 and 1")
    source = Path(video_path).expanduser().resolve()
    result = run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(source),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode not in {0, 255} and "showinfo" not in combined:
        raise DependencyError(f"FFmpeg scene analysis failed: {combined[-1200:]}")
    return sorted({round(float(match.group("time")), 4) for match in _PTS_TIME.finditer(combined) if float(match.group("time")) >= 0})


def apply_annotations(fingerprint: StyleFingerprint, annotations_path: str | Path) -> StyleFingerprint:
    source = Path(annotations_path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        raise ValidationError("Reference annotations must contain an `events` array")
    minute = fingerprint.duration / 60.0
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in events:
        if not isinstance(item, dict):
            continue
        kind = _event_kind(item)
        by_kind.setdefault(kind, []).append(item)
    ranges = [_range(item) for item in events]
    ranges = [item for item in ranges if item]
    zooms = by_kind.get("zoom", []) + by_kind.get("punch_in", [])
    zoom_deltas = [abs(_float(item.get("to_scale"), 1.0) - _float(item.get("from_scale"), 1.0)) for item in zooms]
    captions = by_kind.get("caption", [])
    caption_words = [len(str(item.get("text") or "").split()) for item in captions if item.get("text")]
    broll = by_kind.get("broll", [])
    overlays = by_kind.get("text", []) + by_kind.get("title", []) + by_kind.get("proof", [])
    fingerprint.zooms_per_minute = len(zooms) / minute
    fingerprint.text_events_per_minute = (len(by_kind.get("text", [])) + len(by_kind.get("title", []))) / minute
    fingerprint.broll_events_per_minute = len(broll) / minute
    fingerprint.proof_events_per_minute = len(by_kind.get("proof", [])) / minute
    fingerprint.sfx_events_per_minute = len(by_kind.get("sfx", [])) / minute
    fingerprint.transition_events_per_minute = len(by_kind.get("transition", [])) / minute
    fingerprint.average_zoom_delta = statistics.mean(zoom_deltas) if zoom_deltas else 0.0
    fingerprint.caption_words_per_group = statistics.mean(caption_words) if caption_words else 0.0
    fingerprint.caption_changes_per_minute = len(captions) / minute
    fingerprint.overlay_coverage = _coverage([item for event in overlays if (item := _range(event))], fingerprint.duration)
    fingerprint.broll_coverage = _coverage([item for event in broll if (item := _range(event))], fingerprint.duration)
    fingerprint.maximum_visual_concurrency = _maximum_concurrency(ranges)
    fingerprint.method = "render-scene-detection-plus-annotations-v1"
    fingerprint.notes = ["Annotated event classes supplement hard-cut scene detection."]
    return fingerprint


def compare_fingerprints(reference: StyleFingerprint, candidate: StyleFingerprint) -> dict[str, Any]:
    metrics = {
        "cuts_per_minute": (8.0, 0.16),
        "median_shot_seconds": (4.0, 0.10),
        "zooms_per_minute": (5.0, 0.12),
        "text_events_per_minute": (6.0, 0.10),
        "broll_events_per_minute": (4.0, 0.10),
        "proof_events_per_minute": (3.0, 0.07),
        "sfx_events_per_minute": (5.0, 0.05),
        "transition_events_per_minute": (4.0, 0.04),
        "average_zoom_delta": (0.08, 0.07),
        "caption_words_per_group": (4.0, 0.06),
        "caption_changes_per_minute": (18.0, 0.05),
        "overlay_coverage": (0.35, 0.04),
        "broll_coverage": (0.35, 0.04),
    }
    comparisons = []
    weighted_distance = 0.0
    total_weight = 0.0
    for name, (scale, weight) in metrics.items():
        reference_value = float(getattr(reference, name))
        candidate_value = float(getattr(candidate, name))
        distance = min(1.0, abs(candidate_value - reference_value) / max(scale, abs(reference_value), 1e-9))
        weighted_distance += distance * weight
        total_weight += weight
        direction = "match" if distance <= 0.12 else "higher" if candidate_value > reference_value else "lower"
        comparisons.append(
            {
                "metric": name,
                "reference": round(reference_value, 4),
                "candidate": round(candidate_value, 4),
                "normalized_distance": round(distance, 4),
                "direction": direction,
            }
        )
    score = 100.0 * (1.0 - weighted_distance / max(total_weight, 1e-9))
    recommendations = _recommendations(comparisons, candidate)
    return {
        "style_match_score": round(max(0.0, min(100.0, score)), 2),
        "reference": reference.to_dict(),
        "candidate": candidate.to_dict(),
        "comparisons": sorted(comparisons, key=lambda item: item["normalized_distance"], reverse=True),
        "recommendations": recommendations,
    }


def save_comparison(reference_path: str | Path, candidate_plan: str | Path, output: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    reference = StyleFingerprint(**{key: value for key, value in payload.items() if key in StyleFingerprint.__dataclass_fields__})
    candidate = fingerprint_plan(candidate_plan)
    result = compare_fingerprints(reference, candidate)
    dump_json(result, output)
    return result


def _recommendations(comparisons: list[dict[str, Any]], candidate: StyleFingerprint) -> list[str]:
    recommendations = []
    templates = {
        "cuts_per_minute": "Adjust semantic cut frequency; do not add cuts that lack an editorial job.",
        "zooms_per_minute": "Adjust discrete punch-in frequency while preserving the no-constant-zoom rule.",
        "text_events_per_minute": "Adjust editorial text density; keep captions and headlines in separate hierarchy lanes.",
        "broll_events_per_minute": "Adjust supporting-media frequency using only specific licensed visuals.",
        "proof_events_per_minute": "Adjust proof-card frequency to the number of source claims that genuinely need evidence.",
        "sfx_events_per_minute": "Adjust sound-design accents without masking speech or making expert content feel templated.",
        "caption_words_per_group": "Retune caption phrase grouping for similar reading rhythm.",
        "average_zoom_delta": "Retune punch-in magnitude rather than using global continuous zoom drift.",
        "broll_coverage": "Retune total B-roll coverage while preserving speaker presence and source context.",
        "overlay_coverage": "Retune total text/proof coverage and verify visual-density limits.",
        "median_shot_seconds": "Retune shot holds around thought boundaries, reactions, and evidence—not a fixed timer.",
    }
    for item in comparisons:
        if item["normalized_distance"] >= 0.28 and item["metric"] in templates:
            recommendations.append(templates[item["metric"]])
    if candidate.maximum_visual_concurrency > 3:
        recommendations.append("Reduce simultaneous visual events; the candidate exceeds the normal attention budget.")
    return recommendations[:8]


def _plan_duration(plan: dict[str, Any]) -> float:
    for key in ("duration", "output_duration", "timeline_duration"):
        if plan.get(key) is not None:
            return float(plan[key])
    ranges = [_range(item) for item in _list(plan, "segments", "clips", "timeline")]
    ends = [item[1] for item in ranges if item]
    if ends:
        return max(ends)
    event_ranges = [_range(item) for key in ("captions", "overlays", "broll", "motion", "audio_events") for item in _list(plan, key)]
    return max((item[1] for item in event_ranges if item), default=0.0)


def _list(plan: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = plan.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested in ("segments", "events", "items", "clips", "groups"):
                if isinstance(value.get(nested), list):
                    return value[nested]
    return []


def _range(value: Any) -> tuple[float, float] | None:
    payload = _mapping(value)
    start = None
    for key in ("timeline_in", "timeline_start", "start", "time", "at", "in_point", "source_in"):
        if payload.get(key) is not None:
            start = _float(payload[key], 0.0)
            break
    if start is None:
        return None
    end = None
    for key in ("timeline_out", "timeline_end", "end", "out_point", "source_out"):
        if payload.get(key) is not None:
            end = _float(payload[key], start)
            break
    if end is None and payload.get("duration") is not None:
        end = start + _float(payload["duration"], 0.0)
    if end is None:
        end = start + 0.001
    return (start, max(start + 0.001, end))


def _event_kind(value: Any) -> str:
    payload = _mapping(value)
    return str(payload.get("kind") or payload.get("type") or payload.get("event_type") or payload.get("role") or "unknown").strip().lower().replace("-", "_")


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, dict):
                return payload
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _coverage(ranges: Iterable[tuple[float, float]], duration: float) -> float:
    ordered = sorted((max(0.0, start), min(duration, end)) for start, end in ranges if end > start)
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return sum(end - start for start, end in merged) / max(duration, 1e-9)


def _maximum_concurrency(ranges: Iterable[tuple[float, float]]) -> int:
    points = []
    for start, end in ranges:
        if end <= start:
            continue
        points.append((start, 1))
        points.append((end, -1))
    active = maximum = 0
    for _, delta in sorted(points, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

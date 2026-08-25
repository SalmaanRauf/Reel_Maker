from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

from .models import EditPlan, MotionKind, OverlayKind, QCCheck, TextRole, TransitionKind
from .presets import StyleProfile

PRIMARY_TEXT = {TextRole.HEADLINE, TextRole.SUBHEAD, TextRole.STATISTIC, TextRole.EVIDENCE, TextRole.CALLOUT}
FULLSCREEN = {OverlayKind.BROLL, OverlayKind.FULLSCREEN, OverlayKind.PROOF, OverlayKind.SCREENSHOT}


def visual_checks(
    plan: EditPlan,
    profile: StyleProfile,
    checks: list[QCCheck],
    metrics: dict[str, Any],
    recommendations: list[str],
) -> None:
    _pacing(plan, profile, checks, metrics, recommendations)
    _motion(plan, profile, checks, metrics, recommendations)
    _transitions(plan, profile, checks, metrics)
    _text(plan, profile, checks, metrics, recommendations)
    _broll(plan, profile, checks, metrics, recommendations)
    _layouts(plan, checks, metrics)
    _sound(plan, profile, checks, metrics, recommendations)
    _visual_beats(plan, profile, checks, metrics, recommendations)


def _pacing(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    durations = [item.duration for item in plan.segments]
    micro = [i for i, value in enumerate(durations) if value < profile.rules.shot_min * .55]
    static = [i for i, value in enumerate(durations) if value > profile.rules.shot_max * 1.35 and plan.segments[i].motion.kind == MotionKind.HOLD]
    metrics["pacing"] = {
        "segment_count": len(durations), "durations": durations, "minimum": min(durations), "maximum": max(durations),
        "median": statistics.median(durations), "mean": statistics.fmean(durations),
        "cuts_per_minute": max(0, len(durations) - 1) / max(plan.duration / 60, 1 / 60),
    }
    checks.extend([
        QCCheck("pacing_microcuts", not micro, "warning", "No unexplained microcuts" if not micro else f"Microcut segment(s): {micro}", {"indices": micro}),
        QCCheck("pacing_static_holds", not static, "warning", "No unexplained long static holds" if not static else f"Static hold segment(s): {static}", {"indices": static}),
    ])
    if micro:
        recs.append("Merge sub-second shots unless they mark a real climax, reaction, or proof reveal.")
    if static:
        recs.append("Add a semantic reframe, proof insert, layout change, or explicit hold rationale.")


def _motion(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    drifts: list[int] = []
    excessive: list[tuple[int, float]] = []
    signatures: list[tuple[Any, ...]] = []
    amplitudes: list[float] = []
    motion_count = 0
    for index, segment in enumerate(plan.segments):
        keys = segment.motion.keyframes
        zooms = [item.zoom for item in keys] or [segment.transform.zoom]
        amplitude = max(zooms) - min(zooms)
        amplitudes.append(amplitude)
        motion_count += int(segment.motion.kind != MotionKind.HOLD or amplitude > .005)
        if len(keys) == 2 and segment.duration >= 2:
            first, last = keys
            spans = first.time <= .05 and last.time >= segment.duration * .9
            changed = abs(first.zoom - last.zoom) > .018 or abs(first.crop_x - last.crop_x) > .025 or abs(first.crop_y - last.crop_y) > .025
            if spans and changed and segment.motion.kind not in {MotionKind.KEN_BURNS, MotionKind.PAN}:
                drifts.append(index)
        if max(zooms) > 1.20:
            excessive.append((index, max(zooms)))
        signatures.append((segment.motion.kind.value, round(amplitude, 2), len(keys), tuple(round(k.time / max(segment.duration, .01), 1) for k in keys[:4])))
    repeated = _longest_run(signatures)
    metrics["motion"] = {
        "motion_segment_count": motion_count, "motion_segment_ratio": motion_count / len(plan.segments),
        "amplitudes": amplitudes, "maximum_zoom": max((max([k.zoom for k in s.motion.keyframes] or [s.transform.zoom]) for s in plan.segments), default=1),
        "constant_drift_indices": drifts, "longest_repeated_signature_run": repeated,
    }
    checks.extend([
        QCCheck("motion_constant_drift", not drifts, "error", "No constant slow zooms" if not drifts else f"Constant drift in segment(s) {drifts}", {"indices": drifts}),
        QCCheck("motion_excessive_crop", not excessive, "warning", "Digital zoom stays within 1.20x" if not excessive else f"Excessive zoom: {excessive}", {"segments": excessive}),
        QCCheck("motion_repetition", repeated <= profile.maximum_repeated_framing, "warning", f"Longest repeated motion pattern: {repeated}", {"maximum": profile.maximum_repeated_framing}),
    ])
    if drifts:
        recs.append("Replace constant drift with a hold, discrete punch-in, settle, pull-back, or semantic crop reset.")
    if repeated > profile.maximum_repeated_framing:
        recs.append("Vary shot size, crop, timing, or layout after repeated framing patterns.")


def _transitions(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any]) -> None:
    values = [item.transition_to_next for item in plan.segments[:-1]]
    noncuts = [item for item in values if item.kind != TransitionKind.CUT]
    ratio = len(noncuts) / max(1, len(values))
    metrics["transitions"] = {"total": len(values), "noncut": len(noncuts), "noncut_ratio": ratio, "kinds": [item.kind.value for item in values]}
    checks.extend([
        QCCheck("transition_style", all(item.kind in profile.allowed_transitions for item in noncuts), "warning", "Transitions fit the selected style"),
        QCCheck("transition_density", ratio <= profile.rules.transition_rate_max + .05, "warning", f"Non-cut transition ratio {ratio:.1%}", {"target": profile.rules.transition_rate_max}),
    ])


def _text(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    primary = [(i, item) for i, item in enumerate(plan.text_overlays) if item.role in PRIMARY_TEXT]
    overlaps = [(i, j) for pos, (i, left) in enumerate(primary) for j, right in primary[pos + 1:] if left.start < right.end and right.start < left.end]
    tiny = [i for i, item in enumerate(plan.text_overlays) if item.min_font_size < max(20, plan.height * .018)]
    uppercase = [i for i, item in enumerate(plan.text_overlays) if _uppercase_ratio(item.text) > .88 and len(item.text.split()) > 4]
    rate = len(plan.text_overlays) / max(plan.duration / 60, 1 / 60)
    limit = max(1, math.ceil(plan.duration / 60 * profile.rules.text_events_per_minute * 1.65 + 1))
    metrics["text"] = {"event_count": len(plan.text_overlays), "events_per_minute": rate, "event_limit": limit, "primary_overlap_pairs": overlaps, "tiny_font_indices": tiny, "uppercase_indices": uppercase}
    checks.extend([
        QCCheck("text_primary_hierarchy", not overlaps, "error", "Only one primary phrase is active" if not overlaps else f"Primary text overlaps: {overlaps}", {"pairs": overlaps}),
        QCCheck("text_minimum_size", not tiny, "warning", "Text minimum sizes are format-appropriate" if not tiny else f"Undersized text: {tiny}", {"indices": tiny}),
        QCCheck("text_uppercase_density", not uppercase, "warning", "No giant all-caps template blocks" if not uppercase else f"All-caps blocks: {uppercase}", {"indices": uppercase}),
        QCCheck("text_density", len(plan.text_overlays) <= limit, "warning", f"Text events: {len(plan.text_overlays)}; limit {limit}", {"style_target": profile.rules.text_events_per_minute}),
    ])
    if overlaps:
        recs.append("Use progressive disclosure: retire one primary phrase before introducing the next.")
    if uppercase:
        recs.append("Use sentence case or a shorter label instead of a giant centered all-caps block.")


def _broll(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    values = [item for item in plan.overlays if item.kind in FULLSCREEN]
    coverage = _union([(max(0, item.start), min(plan.duration, item.end)) for item in values]) / max(plan.duration, .01)
    low = [i for i, item in enumerate(values) if item.semantic_confidence < profile.minimum_broll_confidence]
    no_reason = [i for i, item in enumerate(values) if not item.semantic_reason]
    no_source = [i for i, item in enumerate(values) if not item.source_url or not item.license]
    fingerprints = [item.asset_fingerprint for item in values if item.asset_fingerprint]
    duplicates = sorted({item for item in fingerprints if fingerprints.count(item) > 1})
    overlaps = _overlaps(values)
    metrics["broll"] = {"count": len(values), "coverage_ratio": coverage, "low_confidence_indices": low, "missing_reason_indices": no_reason, "missing_provenance_indices": no_source, "duplicate_fingerprints": duplicates, "overlap_pairs": overlaps}
    checks.extend([
        QCCheck("broll_semantic_fit", not low and not no_reason, "error", "All inserts are semantic" if not low and not no_reason else "Decorative or low-confidence insert detected", {"low_confidence": low, "missing_reason": no_reason}),
        QCCheck("broll_provenance", not no_source, "error", "Every insert retains source/license" if not no_source else f"Missing provenance: {no_source}", {"indices": no_source}),
        QCCheck("broll_duplicate_control", not duplicates, "warning", "No repeated B-roll fingerprint" if not duplicates else f"Repeated assets: {duplicates}"),
        QCCheck("broll_simultaneous_fullscreen", not overlaps, "warning", "No competing full-frame inserts" if not overlaps else f"Overlaps: {overlaps}"),
        QCCheck("broll_coverage", coverage <= profile.rules.broll_coverage_max + .05, "warning", f"B-roll/proof coverage {coverage:.1%}", {"cap": profile.rules.broll_coverage_max}),
    ])
    if low or no_reason:
        recs.append("Remove decorative inserts; keep only footage, screenshots, or proof tied to a concrete spoken idea.")
    if no_source:
        recs.append("Attach source URL, license, and attribution before approving an insert.")


def _layouts(plan: EditPlan, checks: list[QCCheck], metrics: dict[str, Any]) -> None:
    overlaps = _overlaps(plan.layout_events)
    short = [i for i, item in enumerate(plan.layout_events) if item.end - item.start < .55]
    metrics["layouts"] = {"count": len(plan.layout_events), "overlap_pairs": overlaps, "too_short_indices": short}
    checks.extend([
        QCCheck("layout_readability", not short, "warning", "Layout changes remain readable" if not short else f"Short layouts: {short}"),
        QCCheck("layout_overlap", not overlaps, "warning", "Layout events do not conflict" if not overlaps else f"Layout overlaps: {overlaps}"),
    ])


def _sound(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    loud = [i for i, item in enumerate(plan.sound_effects) if item.gain_db > -6]
    no_reason = [i for i, item in enumerate(plan.sound_effects) if not item.reason]
    ordered = sorted(enumerate(plan.sound_effects), key=lambda pair: pair[1].start)
    clusters = [(i, j) for (i, left), (j, right) in zip(ordered, ordered[1:], strict=False) if right.start - left.start < .2]
    rate = len(plan.sound_effects) / max(plan.duration / 60, 1 / 60)
    limit = max(0, math.ceil(plan.duration / 60 * profile.rules.sfx_events_per_minute * 1.75 + .5))
    metrics["sound_design"] = {"sfx_count": len(plan.sound_effects), "events_per_minute": rate, "event_limit": limit, "loud_indices": loud, "missing_reason_indices": no_reason, "clustered_pairs": clusters, "music_gain_db": plan.music.gain_db if plan.music else None}
    checks.extend([
        QCCheck("sfx_semantic_reason", not no_reason, "warning", "Every SFX has an editorial reason" if not no_reason else f"Missing SFX reasons: {no_reason}"),
        QCCheck("sfx_peak_guard", not loud, "warning", "SFX stay below speech" if not loud else f"Loud SFX: {loud}"),
        QCCheck("sfx_stacking", not clusters, "warning", "No accidental SFX stacking" if not clusters else f"Stacked SFX: {clusters}"),
        QCCheck("sfx_density", len(plan.sound_effects) <= limit, "warning", f"SFX events: {len(plan.sound_effects)}; limit {limit}"),
    ])
    if loud or clusters:
        recs.append("Reduce or remove SFX; accents must support a semantic beat and stay below speech.")


def _visual_beats(plan: EditPlan, profile: StyleProfile, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    events = {0.0, plan.duration}
    cursor = 0.0
    for index, segment in enumerate(plan.segments):
        events.add(cursor)
        events.update(min(plan.duration, cursor + key.time) for key in segment.motion.keyframes if key.time > .05)
        cursor += segment.duration - (segment.transition_to_next.duration if index < len(plan.segments) - 1 else 0)
    for collection in (plan.text_overlays, plan.overlays, plan.evidence_cards, plan.layout_events, plan.sound_effects):
        events.update(max(0, min(plan.duration, item.start)) for item in collection)
    ordered = sorted(events)
    gaps = [right - left for left, right in zip(ordered, ordered[1:], strict=False)]
    maximum_gap = max(gaps, default=plan.duration)
    strong = [item for item in plan.metadata.get("beat_map", []) if float(item.get("strength", 0)) >= .74]
    misses: list[str] = []
    for beat in strong:
        time = _source_to_timeline(plan, float(beat.get("start", 0)))
        if time is not None and min((abs(event - time) for event in ordered), default=999) > .45:
            misses.append(str(beat.get("id", "unknown")))
    alignment = 1 - len(misses) / max(1, len(strong))
    limit = max(2.5, profile.rules.beat_interval_max * 2.4)
    metrics["visual_beats"] = {"event_count": len(ordered), "maximum_gap": maximum_gap, "median_gap": statistics.median(gaps) if gaps else plan.duration, "strong_beat_count": len(strong), "semantic_alignment": alignment, "missed_strong_beat_ids": misses}
    checks.extend([
        QCCheck("visual_beat_dead_zones", maximum_gap <= limit, "warning", f"Longest interval without a visual beat: {maximum_gap:.2f}s", {"limit": limit}),
        QCCheck("visual_beat_semantic_alignment", alignment >= .72, "warning", f"Semantic alignment {alignment:.0%}", {"misses": misses}),
    ])
    if maximum_gap > limit:
        recs.append("Review long dead zones for a justified hold, crop reset, proof insert, or concise text beat.")
    if misses:
        recs.append("Move visual events onto the actual claim, number, contrast, evidence, or payoff.")


def _source_to_timeline(plan: EditPlan, source_time: float) -> float | None:
    cursor = 0.0
    for index, segment in enumerate(plan.segments):
        if segment.source_start <= source_time <= segment.source_end:
            return cursor + source_time - segment.source_start
        cursor += segment.duration - (segment.transition_to_next.duration if index < len(plan.segments) - 1 else 0)
    return None


def _union(ranges: Sequence[tuple[float, float]]) -> float:
    values = sorted((start, end) for start, end in ranges if end > start)
    if not values:
        return 0.0
    total, start, end = 0.0, values[0][0], values[0][1]
    for next_start, next_end in values[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total, start, end = total + end - start, next_start, next_end
    return total + end - start


def _overlaps(items: Sequence[Any]) -> list[tuple[int, int]]:
    return [(i, j) for i, left in enumerate(items) for j, right in enumerate(items[i + 1:], i + 1) if left.start < right.end and right.start < left.end]


def _longest_run(values: Sequence[Any]) -> int:
    if not values:
        return 0
    best = current = 1
    for left, right in zip(values, values[1:], strict=False):
        current = current + 1 if left == right else 1
        best = max(best, current)
    return best


def _uppercase_ratio(value: str) -> float:
    letters = [item for item in value if item.isalpha()]
    return sum(item.isupper() for item in letters) / max(1, len(letters))

from __future__ import annotations

from typing import Any

from .captions import caption_metrics, chunk_words, occupied_regions_for_plan, remap_transcript_to_plan
from .models import EditPlan, QCCheck, Transcript

QUALIFIERS = {
    "may", "might", "could", "possibly", "possible", "suggest", "suggests", "associated", "uncertain", "unknown",
    "limited", "preclinical", "animal", "animals", "mouse", "mice", "rat", "rats", "anecdote", "anecdotal",
}


def integrity_checks(
    plan: EditPlan,
    *,
    transcript: Transcript | None,
    source_transcript: Transcript | None,
    checks: list[QCCheck],
    metrics: dict[str, Any],
    recommendations: list[str],
) -> None:
    if transcript is not None:
        _captions(plan, transcript, checks, metrics, recommendations)
    if source_transcript is not None:
        _source_integrity(plan, source_transcript, checks, metrics, recommendations)


def _captions(plan: EditPlan, transcript: Transcript, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    mapped = remap_transcript_to_plan(transcript, plan)
    cues = chunk_words(mapped.words, plan.caption_style, width=plan.width, height=plan.height, occupied=occupied_regions_for_plan(plan))
    values = caption_metrics(cues)
    metrics["captions"] = values
    cps_ok = float(values["maximum_cps"]) <= plan.caption_style.maximum_chars_per_second * 1.08
    size_ok = not cues or int(values["minimum_font_size"]) >= plan.caption_style.min_font_size
    lines_ok = int(values["maximum_lines"]) <= plan.caption_style.max_lines
    checks.extend([
        QCCheck("caption_reading_speed", cps_ok, "warning", f"Maximum caption reading speed {values['maximum_cps']:.1f} chars/s", {"target": plan.caption_style.maximum_chars_per_second}),
        QCCheck("caption_responsive_size", size_ok, "error", f"Minimum caption size {values['minimum_font_size']}px", {"minimum": plan.caption_style.min_font_size}),
        QCCheck("caption_line_count", lines_ok, "error", f"Maximum caption lines {values['maximum_lines']}", {"maximum": plan.caption_style.max_lines}),
    ])
    if not cps_ok:
        recs.append("Split fast caption phrases at a grammatical or pause boundary; never shrink them into unreadability.")


def _source_integrity(plan: EditPlan, source: Transcript, checks: list[QCCheck], metrics: dict[str, Any], recs: list[str]) -> None:
    ranges = [(item.source_start, item.source_end) for item in plan.segments if item.source_id == source.asset_id]
    beat_map = sorted(plan.metadata.get("beat_map", []), key=lambda item: float(item.get("start", 0)))
    dropped: list[str] = []
    for index, beat in enumerate(beat_map):
        if not beat.get("qualifier"):
            continue
        start, end = float(beat.get("start", 0)), float(beat.get("end", 0))
        if any(left < end and start < right for left, right in ranges):
            continue
        preceding = beat_map[max(0, index - 2):index]
        risky = any(
            not item.get("qualifier") and float(item.get("end", 0)) <= start and start - float(item.get("end", 0)) <= 3
            and any(left < float(item.get("end", 0)) and float(item.get("start", 0)) < right for left, right in ranges)
            for item in preceding
        )
        if risky:
            dropped.append(str(beat.get("id", f"beat-{index}")))
    selected = [word for segment in plan.segments if segment.source_id == source.asset_id for word in source.words_in(segment.source_start, segment.source_end)]
    positions = [source.words.index(word) for word in selected if word in source.words]
    reordered = any(right < left for left, right in zip(positions, positions[1:], strict=False))
    qualifiers = sorted({word.text.lower().strip(".,!?;:") for word in selected if word.text.lower().strip(".,!?;:") in QUALIFIERS})
    metrics["integrity"] = {"dropped_qualifier_beat_ids": dropped, "source_order_reversed": reordered, "selected_qualifier_terms": qualifiers}
    checks.extend([
        QCCheck("integrity_qualifier_retention", not dropped, "error", "No adjacent scientific/medical qualifier was dropped" if not dropped else f"Dropped qualifier beat(s): {dropped}", {"beat_ids": dropped}),
        QCCheck("integrity_source_order", not reordered, "warning", "Selected source words remain chronological" if not reordered else "Source words were reordered", {"reordered": reordered}),
    ])
    if dropped:
        recs.append("Restore the uncertainty, population, model, or evidence qualifier immediately following the included claim.")

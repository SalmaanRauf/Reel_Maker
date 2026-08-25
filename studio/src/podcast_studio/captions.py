from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .models import CaptionAnimation, CaptionStyle, EditPlan, TextRole, Transcript, Word
from .transcript import to_srt, to_vtt
from .util import clamp


@dataclass(slots=True)
class CaptionCue:
    start: float
    end: float
    words: list[Word]
    text: str
    speaker: str | None = None
    lines: list[list[Word]] = field(default_factory=list)
    font_size: int = 64
    lane_y: float = 0.78
    chars_per_second: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(slots=True, frozen=True)
class OccupiedRegion:
    start: float
    end: float
    top: float
    bottom: float
    priority: int = 50
    label: str = "overlay"

    def overlaps(self, start: float, end: float) -> bool:
        return self.start < end and start < self.end


@dataclass(slots=True, frozen=True)
class WordPlacement:
    word: Word
    x: float
    y: float
    font_size: int
    line_index: int
    active_scale: float
    emphasis: bool


PUNCTUATION_END = re.compile(r"[.!?…][\"'’”)]*$")
PUNCTUATION_ONLY = re.compile(r"^[,.;:!?…]+$")


def chunk_words(
    words: Iterable[Word],
    style: CaptionStyle,
    *,
    width: int = 1080,
    height: int = 1920,
    occupied: Sequence[OccupiedRegion] = (),
) -> list[CaptionCue]:
    ordered = sorted(words, key=lambda item: (item.start, item.end))
    if not ordered:
        return []
    raw: list[list[Word]] = []
    current: list[Word] = []
    for word in ordered:
        if current:
            candidate = _join([*current, word])
            gap = word.start - current[-1].end
            speaker_changed = bool(word.speaker and current[-1].speaker and word.speaker != current[-1].speaker)
            duration = current[-1].end - current[0].start
            cps = len(candidate) / max(0.01, word.end - current[0].start)
            should_break = (
                gap >= style.pause_split
                or len(current) >= style.max_words
                or len(candidate) > style.max_chars
                or speaker_changed
                or duration >= style.maximum_duration
                or cps > style.maximum_chars_per_second * 1.18
                or bool(PUNCTUATION_END.search(current[-1].text))
            )
            if should_break:
                raw.extend(_split_if_needed(current, style))
                current = []
        current.append(word)
    if current:
        raw.extend(_split_if_needed(current, style))

    cues: list[CaptionCue] = []
    for group in raw:
        cue = _cue(group, style)
        cue.font_size = responsive_font_size(cue.text, style, width=width, height=height)
        cue.lines = wrap_words(group, cue.font_size, style, width=width)
        cue.lane_y = choose_caption_lane(cue.start, cue.end, occupied, style)
        cue.chars_per_second = len(cue.text) / max(0.01, cue.duration)
        cues.append(cue)
    return cues


def responsive_font_size(text: str, style: CaptionStyle, *, width: int, height: int) -> int:
    base = int(round(height * style.font_size_ratio)) if style.auto_scale else style.font_size
    base = int(clamp(base, style.min_font_size, style.max_font_size))
    max_width = width * (1 - 2 * style.safe_margin_x_ratio)
    estimated = _measure_text(text, base, style.letter_spacing)
    if estimated > max_width * max(1, style.max_lines):
        scale = max_width * max(1, style.max_lines) / max(1.0, estimated)
        base = int(base * scale)
    longest_word = max((_measure_text(word, base, style.letter_spacing) for word in text.split()), default=0)
    if longest_word > max_width:
        base = int(base * max_width / max(1.0, longest_word))
    return int(clamp(base, style.min_font_size, style.max_font_size))


def wrap_words(words: list[Word], font_size: int, style: CaptionStyle, *, width: int) -> list[list[Word]]:
    if not words:
        return []
    max_width = width * (1 - 2 * style.safe_margin_x_ratio)
    if _measure_words(words, font_size, style.letter_spacing) <= max_width:
        return [words]
    if style.max_lines <= 1:
        return [words]

    best: tuple[float, list[list[Word]]] | None = None
    for split in range(1, len(words)):
        left, right = words[:split], words[split:]
        left_width = _measure_words(left, font_size, style.letter_spacing)
        right_width = _measure_words(right, font_size, style.letter_spacing)
        overflow = max(0.0, left_width - max_width) + max(0.0, right_width - max_width)
        balance = abs(left_width - right_width) * 0.18
        punctuation_penalty = 70.0 if right and PUNCTUATION_ONLY.match(right[0].text) else 0.0
        score = overflow * 10 + balance + punctuation_penalty
        if best is None or score < best[0]:
            best = (score, [left, right])
    lines = best[1] if best else [words]
    return lines[: style.max_lines]


def choose_caption_lane(
    start: float,
    end: float,
    occupied: Sequence[OccupiedRegion],
    style: CaptionStyle,
) -> float:
    candidates = [1.0 - style.safe_bottom_ratio - 0.06, 0.68, style.safe_top_ratio + 0.16]
    if not style.auto_move:
        return candidates[0]
    active = [region for region in occupied if region.overlaps(start, end)]
    if not active:
        return candidates[0]
    best_y = candidates[0]
    best_score = math.inf
    caption_half_height = 0.075
    for lane in candidates:
        top, bottom = lane - caption_half_height, lane + caption_half_height
        score = 0.0
        for region in active:
            overlap = max(0.0, min(bottom, region.bottom) - max(top, region.top))
            score += overlap * (1 + region.priority / 50)
        score += abs(candidates[0] - lane) * 0.02
        if score < best_score:
            best_score, best_y = score, lane
    return clamp(best_y, style.safe_top_ratio + 0.05, 1 - style.safe_bottom_ratio - 0.04)


def occupied_regions_for_plan(plan: EditPlan) -> list[OccupiedRegion]:
    regions: list[OccupiedRegion] = []
    for item in plan.text_overlays:
        if item.role in {TextRole.EYEBROW, TextRole.HEADLINE, TextRole.SUBHEAD, TextRole.STATISTIC, TextRole.EVIDENCE}:
            regions.append(OccupiedRegion(item.start, item.end, 0.06, 0.34, item.priority, f"text:{item.role.value}"))
        else:
            regions.append(OccupiedRegion(item.start, item.end, 0.65, 0.88, item.priority, f"text:{item.role.value}"))
    for item in plan.evidence_cards:
        regions.append(
            OccupiedRegion(item.start, item.end, item.y, min(1.0, item.y + item.height), 90, f"evidence:{item.kind.value}")
        )
    for item in plan.overlays:
        if item.kind.value in {"fullscreen", "proof", "screenshot"}:
            regions.append(OccupiedRegion(item.start, item.end, 0.08, 0.72, 65, f"overlay:{item.kind.value}"))
    return regions


def remap_transcript_to_plan(transcript: Transcript, plan: EditPlan) -> Transcript:
    words: list[Word] = []
    timeline_cursor = 0.0
    for index, segment in enumerate(plan.segments):
        selected = transcript.words_in(segment.source_start, segment.source_end)
        for word in selected:
            source_start = max(word.start, segment.source_start)
            source_end = min(word.end, segment.source_end)
            if source_end <= source_start:
                continue
            mapped_start = timeline_cursor + source_start - segment.source_start
            mapped_end = timeline_cursor + source_end - segment.source_start
            words.append(
                Word(
                    text=word.text,
                    start=max(0.0, mapped_start),
                    end=max(mapped_start + 0.01, mapped_end),
                    speaker=word.speaker,
                    confidence=word.confidence,
                )
            )
        transition = segment.transition_to_next.duration if index < len(plan.segments) - 1 else 0.0
        timeline_cursor += segment.duration - transition
    words.sort(key=lambda item: (item.start, item.end))
    return Transcript(asset_id=f"timeline:{plan.id}", language=transcript.language, words=words, engine="timeline-remap")


def write_caption_files(
    transcript: Transcript,
    output_base: str | Path,
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
    occupied: Sequence[OccupiedRegion] = (),
) -> dict[str, Path]:
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    style = style or CaptionStyle()
    paths = {name: base.with_suffix(f".{name}") for name in ("srt", "vtt", "ass")}
    paths["srt"].write_text(to_srt(transcript), encoding="utf-8")
    paths["vtt"].write_text(to_vtt(transcript), encoding="utf-8")
    paths["ass"].write_text(to_ass(transcript, style=style, width=width, height=height, occupied=occupied), encoding="utf-8")
    return paths


def to_ass_for_plan(transcript: Transcript, plan: EditPlan) -> str:
    remapped = remap_transcript_to_plan(transcript, plan)
    return to_ass(
        remapped,
        style=plan.caption_style,
        width=plan.width,
        height=plan.height,
        occupied=occupied_regions_for_plan(plan),
    )


def to_ass(
    transcript: Transcript,
    *,
    style: CaptionStyle | None = None,
    width: int = 1080,
    height: int = 1920,
    occupied: Sequence[OccupiedRegion] = (),
) -> str:
    style = style or CaptionStyle()
    cues = chunk_words(transcript.words, style, width=width, height=height, occupied=occupied)
    border_style = 3 if style.box else 1
    active_border_style = 3 if style.active_word_box else 1
    bold = -1 if style.bold else 0
    margin_x = round(width * style.safe_margin_x_ratio)
    header = f"""[Script Info]
; Generated by Agentic Podcast Studio
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{_field(style.font_family)},{style.font_size},{style.primary_color},{style.secondary_color},{style.outline_color},{style.back_color},{bold},0,0,0,100,100,{style.letter_spacing},0,{border_style},{style.outline},{style.shadow},5,{margin_x},{margin_x},{style.margin_v},1
Style: Active,{_field(style.font_family)},{style.font_size},{style.active_color},{style.active_color},{style.outline_color},{style.back_color},{bold},0,0,0,100,100,{style.letter_spacing},0,{active_border_style},{style.outline},{style.shadow},5,{margin_x},{margin_x},{style.margin_v},1
Style: Emphasis,{_field(style.font_family)},{style.font_size},{style.emphasis_color},{style.emphasis_color},{style.outline_color},{style.back_color},{bold},0,0,0,100,100,{style.letter_spacing},0,{border_style},{style.outline},{style.shadow},5,{margin_x},{margin_x},{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    emphasis = {normalize_word(item) for item in style.emphasis_words}
    events: list[str] = []
    for cue_index, cue in enumerate(cues):
        placements = place_words(cue, style, width=width, height=height, emphasis=emphasis)
        for placement in placements:
            text = escape_ass(_styled_word(placement.word.text, style))
            event_style = "Emphasis" if placement.emphasis else "Base"
            entrance = _entrance_tags(style.animation, placement.x, placement.y, cue_index)
            karaoke = rf"\kf{max(1, round((placement.word.end - placement.word.start) * 100))}" if style.karaoke else ""
            base_tags = (
                rf"{{\an5\pos({placement.x:.1f},{placement.y:.1f})\fs{placement.font_size}"
                rf"\fscx100\fscy100{karaoke}{entrance}}}"
            )
            events.append(
                f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},{event_style},{_field(cue.speaker or '')},0,0,0,,{base_tags}{text}"
            )
            if style.karaoke and style.animation in {
                CaptionAnimation.WORD_POP,
                CaptionAnimation.ACTIVE_FILL,
                CaptionAnimation.BOUNCE,
            }:
                active_start = max(cue.start, placement.word.start)
                active_end = min(cue.end, placement.word.end)
                if active_end > active_start:
                    active_tags = _active_tags(style, placement)
                    events.append(
                        f"Dialogue: 2,{ass_time(active_start)},{ass_time(active_end)},Active,{_field(cue.speaker or '')},0,0,0,,{active_tags}{text}"
                    )
    return header + "\n".join(events) + ("\n" if events else "")


def place_words(
    cue: CaptionCue,
    style: CaptionStyle,
    *,
    width: int,
    height: int,
    emphasis: set[str] | None = None,
) -> list[WordPlacement]:
    emphasis = emphasis or set()
    lines = cue.lines or [cue.words]
    line_gap = cue.font_size * 1.12 + style.line_spacing
    total_height = max(0.0, (len(lines) - 1) * line_gap)
    center_y = cue.lane_y * height
    first_y = center_y - total_height / 2
    placements: list[WordPlacement] = []
    for line_index, line in enumerate(lines):
        widths = [_measure_text(word.text, cue.font_size, style.letter_spacing) for word in line]
        space = cue.font_size * 0.34
        line_width = sum(widths) + space * max(0, len(line) - 1)
        cursor = (width - line_width) / 2
        y = first_y + line_index * line_gap
        for word, word_width in zip(line, widths, strict=True):
            placements.append(
                WordPlacement(
                    word=word,
                    x=cursor + word_width / 2,
                    y=y,
                    font_size=cue.font_size,
                    line_index=line_index,
                    active_scale=style.active_scale,
                    emphasis=normalize_word(word.text) in emphasis,
                )
            )
            cursor += word_width + space
    return placements


def caption_metrics(cues: Sequence[CaptionCue]) -> dict[str, float | int]:
    if not cues:
        return {
            "cue_count": 0,
            "maximum_cps": 0.0,
            "average_cps": 0.0,
            "maximum_words": 0,
            "minimum_font_size": 0,
            "maximum_lines": 0,
        }
    return {
        "cue_count": len(cues),
        "maximum_cps": max(item.chars_per_second for item in cues),
        "average_cps": sum(item.chars_per_second for item in cues) / len(cues),
        "maximum_words": max(len(item.words) for item in cues),
        "minimum_font_size": min(item.font_size for item in cues),
        "maximum_lines": max(len(item.lines) for item in cues),
    }


def ass_time(seconds: float) -> str:
    cs = round(max(0, seconds) * 100)
    hours, rest = divmod(cs, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, centis = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def normalize_word(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def escape_ass(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _field(value: str) -> str:
    return value.replace(",", " ").replace("\n", " ").strip()


def _cue(words: list[Word], style: CaptionStyle) -> CaptionCue:
    text = _join(words)
    text = text.upper() if style.uppercase else text
    return CaptionCue(words[0].start, words[-1].end, list(words), text, words[0].speaker)


def _split_if_needed(words: list[Word], style: CaptionStyle) -> list[list[Word]]:
    if len(words) <= style.max_words and len(_join(words)) <= style.max_chars:
        return [words]
    if len(words) <= 1:
        return [words]
    gaps = [max(0.0, words[index + 1].start - words[index].end) for index in range(len(words) - 1)]
    split = max(range(1, len(words)), key=lambda index: (gaps[index - 1], -abs(index - len(words) / 2)))
    left, right = words[:split], words[split:]
    return _split_if_needed(left, style) + _split_if_needed(right, style)


def _join(words: list[Word]) -> str:
    text = " ".join(item.text.strip() for item in words)
    return re.sub(r"\s+", " ", re.sub(r"\s+([,.;:!?…])", r"\1", text)).strip()


def _measure_words(words: Sequence[Word], font_size: int, letter_spacing: float) -> float:
    if not words:
        return 0.0
    return sum(_measure_text(item.text, font_size, letter_spacing) for item in words) + (len(words) - 1) * font_size * 0.34


def _measure_text(text: str, font_size: int, letter_spacing: float = 0.0) -> float:
    width_units = 0.0
    for character in text:
        if character.isspace():
            width_units += 0.32
        elif character in "ilI1.,'`|!:;":
            width_units += 0.30
        elif character in "MW@#%&QO0":
            width_units += 0.78
        elif character.isupper():
            width_units += 0.62
        else:
            width_units += 0.53
    return max(1.0, width_units * font_size + max(0, len(text) - 1) * letter_spacing)


def _styled_word(text: str, style: CaptionStyle) -> str:
    return text.upper() if style.uppercase else text


def _entrance_tags(animation: CaptionAnimation, x: float, y: float, cue_index: int) -> str:
    if animation == CaptionAnimation.NONE:
        return ""
    if animation == CaptionAnimation.FADE:
        return r"\fad(90,90)"
    if animation == CaptionAnimation.RISE:
        return rf"\move({x:.1f},{y + 12:.1f},{x:.1f},{y:.1f},0,150)\fad(70,80)"
    if animation in {CaptionAnimation.POP, CaptionAnimation.WORD_POP, CaptionAnimation.ACTIVE_FILL}:
        return r"\fscx94\fscy94\t(0,120,\fscx100\fscy100)\fad(45,70)"
    if animation == CaptionAnimation.BOUNCE:
        return r"\fscx90\fscy90\t(0,80,\fscx108\fscy108)\t(80,160,\fscx100\fscy100)\fad(35,65)"
    return ""


def _active_tags(style: CaptionStyle, placement: WordPlacement) -> str:
    scale = round(placement.active_scale * 100)
    if style.animation == CaptionAnimation.BOUNCE:
        transform = rf"\fscx100\fscy100\t(0,55,\fscx{scale + 4}\fscy{scale + 4})\t(55,{style.animation_ms},\fscx{scale}\fscy{scale})"
    else:
        transform = rf"\fscx100\fscy100\t(0,{style.animation_ms},\fscx{scale}\fscy{scale})"
    return rf"{{\an5\pos({placement.x:.1f},{placement.y:.1f})\fs{placement.font_size}{transform}}}"

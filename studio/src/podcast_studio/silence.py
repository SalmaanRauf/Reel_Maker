from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .exceptions import DependencyError, ValidationError
from .models import Transcript, Word
from .process import run_command

_START = re.compile(r"silence_start:\s*(?P<value>-?\d+(?:\.\d+)?)")
_END = re.compile(r"silence_end:\s*(?P<value>-?\d+(?:\.\d+)?)(?:\s*\|\s*silence_duration:\s*(?P<duration>\d+(?:\.\d+)?))?")
_FILLERS = {
    "um", "umm", "uh", "uhh", "erm", "er", "hmm", "hm", "like", "basically",
    "actually", "literally", "you know", "i mean", "sort of", "kind of",
}
_PROTECTED = {
    "not", "no", "never", "without", "unless", "except", "may", "might", "could",
    "likely", "unlikely", "sometimes", "usually", "approximately", "about", "roughly",
}


@dataclass(slots=True, frozen=True)
class SilenceInterval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True, frozen=True)
class RemovalCandidate:
    start: float
    end: float
    kind: str
    confidence: float
    reason: str
    protected: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def parse_silencedetect(output: str, *, media_duration: float | None = None) -> list[SilenceInterval]:
    intervals: list[SilenceInterval] = []
    open_start: float | None = None
    for line in output.splitlines():
        start_match = _START.search(line)
        if start_match:
            open_start = max(0.0, float(start_match.group("value")))
            continue
        end_match = _END.search(line)
        if end_match:
            end = max(0.0, float(end_match.group("value")))
            if open_start is None and end_match.group("duration"):
                open_start = max(0.0, end - float(end_match.group("duration")))
            if open_start is not None and end > open_start:
                intervals.append(SilenceInterval(open_start, end))
            open_start = None
    if open_start is not None and media_duration and media_duration > open_start:
        intervals.append(SilenceInterval(open_start, media_duration))
    return merge_intervals(intervals)


def detect_silence(
    media_path: str | Path,
    *,
    noise_db: float = -38.0,
    minimum_seconds: float = 0.55,
    ffmpeg: str = "ffmpeg",
    duration: float | None = None,
) -> list[SilenceInterval]:
    source = Path(media_path).expanduser().resolve()
    if not source.exists():
        raise ValidationError(f"Media not found: {source}")
    result = run_command(
        [
            ffmpeg, "-hide_banner", "-nostdin", "-i", str(source),
            "-af", f"silencedetect=noise={noise_db}dB:d={minimum_seconds}",
            "-f", "null", "-",
        ],
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode not in {0, 255} and "silence_" not in combined:
        raise DependencyError(f"FFmpeg silence detection failed: {combined[-1200:]}")
    return parse_silencedetect(combined, media_duration=duration)


def conservative_removals(
    transcript: Transcript,
    silences: Iterable[SilenceInterval],
    *,
    minimum_silence: float = 0.72,
    retained_breath: float = 0.18,
    maximum_single_cut: float = 3.25,
    remove_fillers: bool = True,
) -> list[RemovalCandidate]:
    words = transcript.all_words()
    candidates: list[RemovalCandidate] = []
    for interval in silences:
        if interval.duration < minimum_silence:
            continue
        trim = min(retained_breath, interval.duration / 3.0)
        start, end = interval.start + trim, interval.end - trim
        if end <= start:
            continue
        if end - start > maximum_single_cut:
            end = start + maximum_single_cut
        adjacent = _adjacent_words(words, interval.start, interval.end)
        protected = any(_normalize(word.text) in _PROTECTED for word in adjacent)
        candidates.append(
            RemovalCandidate(
                start=start,
                end=end,
                kind="silence",
                confidence=0.97 if interval.duration >= 1.2 else 0.88,
                reason=f"Long pause reduced while retaining {trim:.2f}s handles",
                protected=protected,
            )
        )
    if remove_fillers:
        candidates.extend(filler_candidates(words))
    return resolve_candidate_conflicts(candidates)


def filler_candidates(words: Iterable[Word]) -> list[RemovalCandidate]:
    ordered = sorted(words, key=lambda word: (word.start, word.end))
    candidates: list[RemovalCandidate] = []
    index = 0
    while index < len(ordered):
        normalized = _normalize(ordered[index].text)
        phrase = normalized
        span = [ordered[index]]
        if index + 1 < len(ordered):
            phrase = f"{normalized} {_normalize(ordered[index + 1].text)}".strip()
            if phrase in _FILLERS:
                span.append(ordered[index + 1])
        if phrase not in _FILLERS and normalized not in _FILLERS:
            index += 1
            continue
        token = phrase if phrase in _FILLERS else normalized
        previous = ordered[index - 1] if index > 0 else None
        following_index = index + len(span)
        following = ordered[following_index] if following_index < len(ordered) else None
        isolated = (previous is None or span[0].start - previous.end >= 0.08) and (
            following is None or following.start - span[-1].end >= 0.08
        )
        protected = any(
            _normalize(word.text) in _PROTECTED
            for word in [item for item in (previous, following) if item is not None]
        )
        candidates.append(
            RemovalCandidate(
                start=max(0.0, span[0].start - (0.025 if isolated else 0.0)),
                end=span[-1].end + (0.025 if isolated else 0.0),
                kind="filler",
                confidence=0.9 if token in {"um", "umm", "uh", "uhh", "erm", "er"} and isolated else 0.58,
                reason=f"Transcript filler: {token}",
                protected=protected or not isolated or token in {"like", "actually", "basically", "literally"},
            )
        )
        index += len(span)
    return candidates


def kept_ranges(duration: float, removals: Iterable[RemovalCandidate], *, minimum_keep: float = 0.12) -> list[tuple[float, float]]:
    if duration <= 0:
        raise ValidationError("Duration must be positive")
    accepted = [item for item in removals if not item.protected and item.confidence >= 0.8]
    cut_intervals = merge_intervals([SilenceInterval(max(0.0, item.start), min(duration, item.end)) for item in accepted])
    ranges: list[tuple[float, float]] = []
    cursor = 0.0
    for interval in cut_intervals:
        if interval.start - cursor >= minimum_keep:
            ranges.append((cursor, interval.start))
        cursor = max(cursor, interval.end)
    if duration - cursor >= minimum_keep:
        ranges.append((cursor, duration))
    return ranges or [(0.0, duration)]


def merge_intervals(intervals: Iterable[SilenceInterval], *, tolerance: float = 0.025) -> list[SilenceInterval]:
    ordered = sorted((item for item in intervals if item.end > item.start), key=lambda item: item.start)
    merged: list[SilenceInterval] = []
    for interval in ordered:
        if merged and interval.start <= merged[-1].end + tolerance:
            merged[-1] = SilenceInterval(merged[-1].start, max(merged[-1].end, interval.end))
        else:
            merged.append(interval)
    return merged


def resolve_candidate_conflicts(candidates: Iterable[RemovalCandidate]) -> list[RemovalCandidate]:
    ordered = sorted(candidates, key=lambda item: (item.start, -item.confidence, item.end))
    accepted: list[RemovalCandidate] = []
    for candidate in ordered:
        if candidate.end <= candidate.start:
            continue
        overlapping = [item for item in accepted if candidate.start < item.end and item.start < candidate.end]
        if not overlapping:
            accepted.append(candidate)
            continue
        strongest = max(overlapping + [candidate], key=lambda item: (not item.protected, item.confidence, item.duration))
        accepted = [item for item in accepted if item not in overlapping]
        accepted.append(strongest)
    return sorted(accepted, key=lambda item: item.start)


def _adjacent_words(words: list[Word], start: float, end: float) -> list[Word]:
    before = [word for word in words if word.end <= start]
    after = [word for word in words if word.start >= end]
    result: list[Word] = []
    if before:
        result.append(before[-1])
    if after:
        result.append(after[0])
    return result


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", text.lower()).strip()

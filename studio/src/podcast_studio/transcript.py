from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .exceptions import ValidationError
from .models import Transcript, TranscriptSegment, Word
from .util import compact_whitespace, dump_json, parse_timestamp, seconds_to_srt, seconds_to_vtt

_TIMESTAMP_LINE = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})"
)
_TAG = re.compile(r"<[^>]+>")


def load_transcript(path: str | Path, *, asset_id: str = "unknown") -> Transcript:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Transcript file not found: {source}")
    suffix = source.suffix.lower()
    if suffix == ".json":
        return transcript_from_json(json.loads(source.read_text(encoding="utf-8")), asset_id=asset_id)
    if suffix in {".srt", ".vtt"}:
        return transcript_from_subtitles(source.read_text(encoding="utf-8-sig"), asset_id=asset_id, engine=suffix[1:])
    if suffix in {".txt", ".md"}:
        raise ValidationError("Plain text has no timings. Import timed JSON, SRT, or VTT instead.")
    raise ValidationError(f"Unsupported transcript format: {source.suffix}")


def save_transcript(transcript: Transcript, path: str | Path) -> Path:
    destination = Path(path)
    suffix = destination.suffix.lower()
    if suffix == ".json":
        return dump_json(transcript.to_dict(), destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".srt":
        destination.write_text(to_srt(transcript), encoding="utf-8")
        return destination
    if suffix == ".vtt":
        destination.write_text(to_vtt(transcript), encoding="utf-8")
        return destination
    raise ValidationError("Transcript output must end in .json, .srt, or .vtt")


def transcript_from_json(payload: Any, *, asset_id: str = "unknown") -> Transcript:
    if isinstance(payload, dict) and isinstance(payload.get("transcript"), dict):
        payload = payload["transcript"]
    if not isinstance(payload, dict):
        raise ValidationError("Transcript JSON must be an object")

    resolved_asset = str(payload.get("asset_id") or asset_id)
    language = str(payload.get("language") or payload.get("detected_language") or "en")
    engine = str(payload.get("engine") or payload.get("model") or "json-import")
    segments: list[TranscriptSegment] = []

    raw_segments = payload.get("segments") or payload.get("transcription") or []
    if isinstance(raw_segments, list):
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict) or raw.get("start") is None or raw.get("end") is None:
                continue
            words = [_word_from_payload(item, raw.get("speaker")) for item in raw.get("words", []) if isinstance(item, dict)]
            text = compact_whitespace(str(raw.get("text") or " ".join(word.text for word in words)))
            if not text:
                continue
            start, end = float(raw["start"]), float(raw["end"])
            if not words:
                words = approximate_words(text, start, end, speaker=raw.get("speaker"))
            segments.append(
                TranscriptSegment(
                    id=str(raw.get("id") or f"segment-{index + 1}"),
                    start=start,
                    end=end,
                    text=text,
                    speaker=raw.get("speaker"),
                    words=words,
                )
            )

    top_words = [_word_from_payload(item, item.get("speaker")) for item in payload.get("words", []) if isinstance(item, dict)]
    if not segments and top_words:
        segments = segments_from_words(top_words)
    if not segments and isinstance(payload.get("text"), str) and payload.get("duration"):
        text = compact_whitespace(payload["text"])
        words = approximate_words(text, 0.0, float(payload["duration"]))
        segments = [TranscriptSegment(0.0, float(payload["duration"]), text, words=words)]
    if not segments and not top_words:
        raise ValidationError("Transcript JSON contains no timed segments or words")
    return Transcript(
        asset_id=resolved_asset,
        language=language,
        segments=segments,
        words=top_words,
        engine=engine,
        metadata={key: value for key, value in payload.items() if key not in {"segments", "transcription", "words", "text"}},
    )


def transcript_from_subtitles(text: str, *, asset_id: str = "unknown", engine: str = "subtitle-import") -> Transcript:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[TranscriptSegment] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line or line.upper() == "WEBVTT" or line.startswith(("NOTE", "STYLE", "REGION")):
            index += 1
            continue
        match = _TIMESTAMP_LINE.search(line)
        if not match and index + 1 < len(lines):
            match = _TIMESTAMP_LINE.search(lines[index + 1])
            if match:
                index += 1
        if not match:
            index += 1
            continue
        start, end = parse_timestamp(match.group("start")), parse_timestamp(match.group("end"))
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            content.append(lines[index].strip())
            index += 1
        clean = compact_whitespace(_TAG.sub("", " ".join(content)).replace("&nbsp;", " "))
        if clean and end > start:
            speaker, clean = _extract_speaker(clean)
            segments.append(
                TranscriptSegment(
                    start=start,
                    end=end,
                    text=clean,
                    speaker=speaker,
                    words=approximate_words(clean, start, end, speaker=speaker),
                )
            )
        index += 1
    if not segments:
        raise ValidationError("No timed subtitle cues were found")
    return Transcript(asset_id=asset_id, segments=segments, engine=engine)


def to_srt(transcript: Transcript) -> str:
    cues = transcript.segments or segments_from_words(transcript.words)
    blocks = []
    for index, segment in enumerate(cues, 1):
        speaker = f"{segment.speaker}: " if segment.speaker else ""
        blocks.append(
            f"{index}\n{seconds_to_srt(segment.start)} --> {seconds_to_srt(segment.end)}\n"
            f"{speaker}{segment.text}\n"
        )
    return "\n".join(blocks)


def to_vtt(transcript: Transcript) -> str:
    cues = transcript.segments or segments_from_words(transcript.words)
    blocks = ["WEBVTT\n"]
    for segment in cues:
        speaker = f"<v {segment.speaker}>" if segment.speaker else ""
        blocks.append(
            f"{seconds_to_vtt(segment.start)} --> {seconds_to_vtt(segment.end)}\n"
            f"{speaker}{segment.text}\n"
        )
    return "\n".join(blocks)


def approximate_words(text: str, start: float, end: float, *, speaker: str | None = None) -> list[Word]:
    tokens = [item for item in re.findall(r"\S+", compact_whitespace(text)) if item]
    if not tokens or end <= start:
        return []
    weights = [max(1.0, len(re.sub(r"\W", "", token)) ** 0.72) for token in tokens]
    total = sum(weights)
    duration = end - start
    cursor = start
    words: list[Word] = []
    for index, (token, weight) in enumerate(zip(tokens, weights, strict=True)):
        word_duration = duration * weight / total
        word_end = end if index == len(tokens) - 1 else min(end, cursor + word_duration)
        words.append(Word(token, cursor, max(cursor + 0.01, word_end), speaker=speaker))
        cursor = word_end
    return words


def segments_from_words(words: Iterable[Word], *, maximum_seconds: float = 4.0, maximum_words: int = 14) -> list[TranscriptSegment]:
    ordered = sorted(words, key=lambda item: (item.start, item.end))
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in ordered:
        if current:
            gap = word.start - current[-1].end
            duration = current[-1].end - current[0].start
            speaker_change = bool(word.speaker and current[-1].speaker and word.speaker != current[-1].speaker)
            if gap >= 0.55 or speaker_change or len(current) >= maximum_words or duration >= maximum_seconds or re.search(r"[.!?…]$", current[-1].text):
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)
    return [
        TranscriptSegment(
            start=group[0].start,
            end=group[-1].end,
            text=compact_whitespace(" ".join(word.text for word in group)),
            speaker=group[0].speaker,
            words=list(group),
        )
        for group in groups
    ]


def _word_from_payload(value: dict[str, Any], fallback_speaker: str | None) -> Word:
    token = str(value.get("text") or value.get("word") or "").strip()
    return Word(
        token,
        float(value["start"]),
        float(value["end"]),
        speaker=value.get("speaker") or fallback_speaker,
        confidence=float(value.get("confidence", value.get("probability"))) if value.get("confidence", value.get("probability")) is not None else None,
    )


def _extract_speaker(text: str) -> tuple[str | None, str]:
    voice = re.match(r"^<v\s+([^>]+)>(.*)$", text, re.I)
    if voice:
        return voice.group(1).strip(), compact_whitespace(voice.group(2))
    label = re.match(r"^([A-Z][A-Za-z0-9 _.-]{0,30}):\s+(.+)$", text)
    if label:
        return label.group(1).strip(), compact_whitespace(label.group(2))
    return None, text

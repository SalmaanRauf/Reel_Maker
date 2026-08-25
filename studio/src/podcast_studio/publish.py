from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .agent import run_subscription_agent
from .exceptions import ValidationError
from .models import Transcript, TranscriptSegment
from .transcript import load_transcript
from .util import compact_whitespace, dump_json, slugify

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by", "for", "from", "had", "has", "have",
    "he", "her", "his", "i", "if", "in", "is", "it", "its", "of", "on", "or", "our", "she", "so", "that", "the",
    "their", "them", "they", "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "will", "with", "you", "your",
}


@dataclass(slots=True)
class Chapter:
    time: float
    title: str

    def to_dict(self) -> dict[str, Any]:
        return {"time": round(self.time, 3), "title": self.title}


@dataclass(slots=True)
class PublishingPackage:
    title: str
    alternate_titles: list[str]
    description: str
    short_caption: str
    chapters: list[Chapter]
    hashtags: list[str]
    thumbnail_concepts: list[dict[str, Any]]
    platform_copy: dict[str, str]
    source_range: dict[str, float]
    integrity_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "alternate_titles": self.alternate_titles,
            "description": self.description,
            "short_caption": self.short_caption,
            "chapters": [item.to_dict() for item in self.chapters],
            "hashtags": self.hashtags,
            "thumbnail_concepts": self.thumbnail_concepts,
            "platform_copy": self.platform_copy,
            "source_range": self.source_range,
            "integrity_notes": self.integrity_notes,
        }


def build_package(
    transcript_path: str | Path,
    *,
    start: float = 0.0,
    end: float | None = None,
    title_hint: str | None = None,
    agent: str | None = None,
    project_root: str | Path | None = None,
    brand_voice: str = "clear, precise, credible, direct",
) -> PublishingPackage:
    transcript = load_transcript(transcript_path)
    resolved_end = end if end is not None else transcript.duration
    if resolved_end <= start:
        raise ValidationError("Publishing range end must be after start")
    segments = [item for item in transcript.segments if item.end > start and item.start < resolved_end]
    if not segments:
        raise ValidationError("No transcript content overlaps the publishing range")
    text = compact_whitespace(" ".join(item.text for item in segments))
    if agent:
        if project_root is None:
            raise ValidationError("project_root is required for subscription-backed publishing copy")
        package = _agent_package(
            transcript,
            segments,
            text,
            start=start,
            end=resolved_end,
            title_hint=title_hint,
            provider=agent,
            project_root=project_root,
            brand_voice=brand_voice,
        )
    else:
        package = _deterministic_package(segments, text, start=start, end=resolved_end, title_hint=title_hint)
    _validate_fidelity(package, text)
    return package


def save_package(package: PublishingPackage, output: str | Path) -> Path:
    return dump_json(package.to_dict(), output)


def _deterministic_package(
    segments: list[TranscriptSegment],
    text: str,
    *,
    start: float,
    end: float,
    title_hint: str | None,
) -> PublishingPackage:
    first_sentence = _sentences(text)[0] if _sentences(text) else text
    title = _clean_title(title_hint or first_sentence, maximum_words=11)
    keywords = _keywords(text, maximum=8)
    alternate_titles = _alternate_titles(title, first_sentence, keywords)
    description = _description(text)
    chapters = _chapters(segments, start=start)
    hashtags = ["#" + _hashtag(item) for item in keywords[:6] if _hashtag(item)]
    thumbnail_concepts = _thumbnail_concepts(segments, title, keywords, start=start)
    short_caption = _short_caption(first_sentence, title)
    platform_copy = {
        "youtube_shorts": f"{short_caption}\n\n{description}\n\n{' '.join(hashtags[:5])}".strip(),
        "instagram_reels": f"{short_caption}\n\n{' '.join(hashtags[:6])}".strip(),
        "tiktok": f"{short_caption} {' '.join(hashtags[:4])}".strip(),
        "linkedin": f"{title}\n\n{description}".strip(),
        "x": _limit(f"{short_caption}\n\n{hashtags[0] if hashtags else ''}".strip(), 280),
    }
    integrity_notes = _integrity_notes(text)
    return PublishingPackage(
        title=title,
        alternate_titles=alternate_titles,
        description=description,
        short_caption=short_caption,
        chapters=chapters,
        hashtags=hashtags,
        thumbnail_concepts=thumbnail_concepts,
        platform_copy=platform_copy,
        source_range={"start": start, "end": end},
        integrity_notes=integrity_notes,
    )


def _agent_package(
    transcript: Transcript,
    segments: list[TranscriptSegment],
    text: str,
    *,
    start: float,
    end: float,
    title_hint: str | None,
    provider: str,
    project_root: str | Path,
    brand_voice: str,
) -> PublishingPackage:
    schema = {
        "type": "object",
        "required": ["title", "alternate_titles", "description", "short_caption", "chapters", "hashtags", "thumbnail_concepts", "platform_copy", "integrity_notes"],
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "alternate_titles": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string"}},
            "description": {"type": "string"},
            "short_caption": {"type": "string"},
            "chapters": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "required": ["time", "title"],
                    "additionalProperties": False,
                    "properties": {"time": {"type": "number", "minimum": 0}, "title": {"type": "string"}},
                },
            },
            "hashtags": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
            "thumbnail_concepts": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "required": ["headline", "visual", "source_time", "reason"],
                    "additionalProperties": False,
                    "properties": {
                        "headline": {"type": "string"},
                        "visual": {"type": "string"},
                        "source_time": {"type": "number", "minimum": 0},
                        "reason": {"type": "string"},
                    },
                },
            },
            "platform_copy": {
                "type": "object",
                "required": ["youtube_shorts", "instagram_reels", "tiktok", "linkedin", "x"],
                "additionalProperties": False,
                "properties": {name: {"type": "string"} for name in ("youtube_shorts", "instagram_reels", "tiktok", "linkedin", "x")},
            },
            "integrity_notes": {"type": "array", "maxItems": 10, "items": {"type": "string"}},
        },
    }
    timestamped = "\n".join(f"[{segment.start - start:.2f}-{segment.end - start:.2f}] {segment.text}" for segment in segments)
    prompt = f"""Create the complete publishing package for this podcast clip.

Voice: {brand_voice}
Title hint: {title_hint or 'none'}

Rules:
- Every title and description must be substantively supported by the transcript.
- Never intensify uncertainty, causality, scope, dosage, numbers, or outcomes.
- Do not use empty clickbait, fake controversy, generic motivation, or fabricated quotes.
- Prefer a crisp concrete thesis, mechanism, contrast, consequence, or question.
- Title: ideally 5-11 words.
- Short caption: one or two concise sentences.
- Hashtags: specific and useful, not spam.
- X copy must stay within 280 characters.
- Chapter times are relative to the beginning of this clip and must fall between 0 and {end - start:.2f}.
- Thumbnail headlines must be 2-7 words and remain faithful.
- Thumbnail source_time must identify a real expressive or explanatory frame inside the clip.
- Integrity notes must identify qualifiers or claims that should not be exaggerated.

Timed transcript:
{timestamped}
"""
    result = run_subscription_agent(provider, prompt, cwd=project_root, schema=schema)
    payload = result.structured
    chapters = [
        Chapter(time=min(end - start, max(0.0, float(item["time"]))), title=_clean_title(str(item["title"]), maximum_words=9))
        for item in payload["chapters"]
    ]
    concepts = []
    for item in payload["thumbnail_concepts"]:
        concepts.append(
            {
                "headline": _clean_title(str(item["headline"]), maximum_words=7),
                "visual": str(item["visual"]).strip(),
                "source_time": min(end - start, max(0.0, float(item["source_time"]))),
                "reason": str(item["reason"]).strip(),
            }
        )
    hashtags = []
    for value in payload["hashtags"]:
        tag = _hashtag(str(value).lstrip("#"))
        if tag and f"#{tag}" not in hashtags:
            hashtags.append(f"#{tag}")
    platform_copy = {key: str(value).strip() for key, value in payload["platform_copy"].items()}
    platform_copy["x"] = _limit(platform_copy["x"], 280)
    return PublishingPackage(
        title=_clean_title(payload["title"], maximum_words=12),
        alternate_titles=[_clean_title(item, maximum_words=12) for item in payload["alternate_titles"]],
        description=str(payload["description"]).strip(),
        short_caption=str(payload["short_caption"]).strip(),
        chapters=chapters,
        hashtags=hashtags,
        thumbnail_concepts=concepts,
        platform_copy=platform_copy,
        source_range={"start": start, "end": end},
        integrity_notes=[str(item).strip() for item in payload["integrity_notes"] if str(item).strip()],
    )


def _chapters(segments: list[TranscriptSegment], *, start: float) -> list[Chapter]:
    if len(segments) <= 2:
        return [Chapter(0.0, _clean_title(segments[0].text, maximum_words=7))]
    desired = min(6, max(2, round((segments[-1].end - segments[0].start) / 28)))
    stride = max(1, len(segments) // desired)
    chapters: list[Chapter] = []
    for index in range(0, len(segments), stride):
        segment = segments[index]
        title = _clean_title(segment.text, maximum_words=7)
        if not chapters or title.casefold() != chapters[-1].title.casefold():
            chapters.append(Chapter(max(0.0, segment.start - start), title))
    return chapters[:8]


def _thumbnail_concepts(segments: list[TranscriptSegment], title: str, keywords: list[str], *, start: float) -> list[dict[str, Any]]:
    candidates = [segments[0], segments[len(segments) // 2], segments[-1]]
    concepts = []
    headlines = [title, f"The {keywords[0]} Problem" if keywords else title, "What Actually Happens"]
    for segment, headline in zip(candidates, headlines, strict=False):
        concepts.append(
            {
                "headline": _clean_title(headline, maximum_words=7),
                "visual": "Use the strongest natural speaker expression; preserve eye line and leave negative space for the headline.",
                "source_time": round(max(0.0, ((segment.start + segment.end) / 2) - start), 3),
                "reason": "Source-derived moment aligned with a major beat in the clip.",
            }
        )
    return concepts


def _description(text: str) -> str:
    sentences = _sentences(text)
    selected = sentences[:3]
    description = compact_whitespace(" ".join(selected))
    return _limit(description, 520)


def _short_caption(first_sentence: str, title: str) -> str:
    sentence = compact_whitespace(first_sentence)
    if len(sentence) <= 180:
        return sentence
    return _limit(title + ". " + sentence, 220)


def _alternate_titles(title: str, first_sentence: str, keywords: list[str]) -> list[str]:
    options = [
        _clean_title(first_sentence, maximum_words=10),
        _clean_title(f"Why {keywords[0]} Is Misunderstood", maximum_words=10) if keywords else title,
        _clean_title(f"What Most People Miss About {keywords[0]}", maximum_words=10) if keywords else title,
        _clean_title(f"The Real {keywords[0]} Tradeoff", maximum_words=10) if keywords else title,
    ]
    unique = []
    for option in options:
        if option and option.casefold() != title.casefold() and option.casefold() not in {item.casefold() for item in unique}:
            unique.append(option)
    return unique[:4] or [title]


def _integrity_notes(text: str) -> list[str]:
    notes = []
    patterns = {
        r"\b(may|might|could)\b": "Preserve uncertainty; do not convert possibility into certainty.",
        r"\b(about|approximately|roughly)\b": "Preserve approximate quantities.",
        r"\b(in my experience|anecdotally|i think)\b": "Keep opinion or anecdote distinct from evidence.",
        r"\b(not|never|without|unless|except)\b": "Protect negation and exceptions in edits and headlines.",
        r"\b(study|trial|research|data)\b": "Verify that supporting visuals match the exact cited evidence.",
    }
    for pattern, note in patterns.items():
        if re.search(pattern, text, re.I):
            notes.append(note)
    return notes


def _validate_fidelity(package: PublishingPackage, source_text: str) -> None:
    if not package.title.strip() or len(package.title) > 160:
        raise ValidationError("Publishing title is missing or unreasonably long")
    if len(package.platform_copy.get("x", "")) > 280:
        raise ValidationError("X copy exceeds 280 characters")
    duration = package.source_range["end"] - package.source_range["start"]
    if any(chapter.time < 0 or chapter.time > duration for chapter in package.chapters):
        raise ValidationError("A chapter time falls outside the source range")
    if any(float(item.get("source_time", -1)) < 0 or float(item.get("source_time", duration + 1)) > duration for item in package.thumbnail_concepts):
        raise ValidationError("A thumbnail source time falls outside the clip")
    source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", source_text))
    published_text = " ".join([package.title, package.description, package.short_caption, *package.platform_copy.values()])
    invented = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", published_text)) - source_numbers
    if invented:
        raise ValidationError(f"Publishing package introduced unsupported numbers: {', '.join(sorted(invented))}")


def _keywords(text: str, *, maximum: int) -> list[str]:
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text):
        normalized = token.casefold().strip("'-")
        if normalized in _STOPWORDS or len(normalized) < 4:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
        display.setdefault(normalized, token.strip("'-"))
    ranked = sorted(counts, key=lambda item: (counts[item], len(item)), reverse=True)
    return [display[item] for item in ranked[:maximum]]


def _sentences(text: str) -> list[str]:
    return [compact_whitespace(item) for item in re.split(r"(?<=[.!?])\s+", compact_whitespace(text)) if compact_whitespace(item)]


def _clean_title(text: str, *, maximum_words: int) -> str:
    cleaned = compact_whitespace(str(text)).strip(" .,:;!?—–-")
    words = cleaned.split()
    cleaned = " ".join(words[:maximum_words])
    if not cleaned:
        return "Podcast Clip"
    return cleaned[0].upper() + cleaned[1:]


def _hashtag(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return ""
    return "".join(word[:1].upper() + word[1:] for word in words)[:48]


def _limit(text: str, maximum: int) -> str:
    text = compact_whitespace(text)
    if len(text) <= maximum:
        return text
    shortened = text[: maximum - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return shortened + "…"

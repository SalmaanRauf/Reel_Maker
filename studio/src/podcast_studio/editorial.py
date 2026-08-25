from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .agent import run_subscription_agent
from .exceptions import ValidationError
from .models import Transcript, TranscriptSegment, Word
from .transcript import load_transcript
from .util import compact_whitespace, dump_json, slugify

_HOOKS = re.compile(
    r"\b(the truth|most people|nobody|everyone|never|always|biggest|worst|best|mistake|"
    r"problem|secret|surprising|actually|here's why|what if|how do|why does|\d+(?:\.\d+)?%?)\b",
    re.I,
)
_CONTRAST = re.compile(r"\b(but|however|instead|rather than|whereas|yet|on the other hand|the opposite)\b", re.I)
_EVIDENCE = re.compile(r"\b(study|trial|data|evidence|research|measured|participants|patients|result|found|showed)\b", re.I)
_MECHANISM = re.compile(r"\b(because|which means|the reason|mechanism|causes|leads to|therefore|so that)\b", re.I)
_PAYOFF = re.compile(r"\b(so|therefore|the takeaway|what you should|the point is|that is why|in practice)\b", re.I)
_QUALIFIER = re.compile(r"\b(may|might|could|usually|sometimes|likely|approximately|about|depends|in my experience|anecdotal)\b", re.I)
_WEAK_OPEN = re.compile(r"^(and|so|but|then|it|this|that|they|he|she|we)\b", re.I)


@dataclass(slots=True)
class ClipCandidate:
    id: str
    start: float
    end: float
    text: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    speaker: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "text": self.text,
            "score": round(self.score, 2),
            "components": {key: round(value, 3) for key, value in self.components.items()},
            "flags": self.flags,
            "speaker": self.speaker,
        }


def discover_candidates(
    transcript: Transcript,
    *,
    minimum_seconds: float = 35.0,
    target_seconds: float = 72.0,
    maximum_seconds: float = 120.0,
    step_segments: int = 2,
    maximum_candidates: int = 80,
) -> list[ClipCandidate]:
    segments = transcript.segments
    if not segments:
        raise ValidationError("Clip discovery requires timed transcript segments")
    candidates: list[ClipCandidate] = []
    for start_index in range(0, len(segments), max(1, step_segments)):
        for end_index in range(start_index, len(segments)):
            start, end = segments[start_index].start, segments[end_index].end
            duration = end - start
            if duration < minimum_seconds:
                continue
            if duration > maximum_seconds:
                break
            window = segments[start_index : end_index + 1]
            candidate = score_candidate(window, target_seconds=target_seconds)
            candidates.append(candidate)
            if duration >= target_seconds and _semantic_close(window[-1].text):
                break
    candidates.sort(key=lambda item: item.score, reverse=True)
    return _deduplicate(candidates, limit=maximum_candidates)


def score_candidate(segments: list[TranscriptSegment], *, target_seconds: float = 72.0) -> ClipCandidate:
    if not segments:
        raise ValidationError("Cannot score an empty clip")
    text = compact_whitespace(" ".join(segment.text for segment in segments))
    start, end = segments[0].start, segments[-1].end
    duration = end - start
    first_text = compact_whitespace(" ".join(segment.text for segment in segments if segment.start <= start + 5.0))
    last_text = compact_whitespace(" ".join(segment.text for segment in segments if segment.end >= end - 8.0))

    hook = min(1.0, (0.55 if _HOOKS.search(first_text) else 0.0) + (0.3 if re.search(r"\?", first_text) else 0.0) + (0.2 if re.search(r"\d", first_text) else 0.0))
    standalone = 1.0 - (0.5 if _WEAK_OPEN.search(first_text) else 0.0) - (0.25 if len(first_text.split()) < 6 else 0.0)
    structure = min(1.0, 0.25 * bool(_CONTRAST.search(text)) + 0.25 * bool(_MECHANISM.search(text)) + 0.25 * bool(_EVIDENCE.search(text)) + 0.25 * bool(_PAYOFF.search(last_text)))
    payoff = min(1.0, 0.65 * bool(_PAYOFF.search(last_text)) + 0.35 * _semantic_close(last_text))
    specificity = min(1.0, 0.35 * bool(re.search(r"\d", text)) + 0.35 * bool(_EVIDENCE.search(text)) + 0.3 * _lexical_specificity(text))
    duration_fit = math.exp(-abs(duration - target_seconds) / max(18.0, target_seconds * 0.42))
    density = min(1.0, len(text.split()) / max(1.0, duration * 2.1))
    qualifier_integrity = 1.0 if _QUALIFIER.search(text) else 0.78
    completion = 1.0 if _semantic_close(last_text) else 0.58

    components = {
        "hook": hook,
        "standalone": max(0.0, standalone),
        "structure": structure,
        "payoff": payoff,
        "specificity": specificity,
        "duration_fit": duration_fit,
        "density": density,
        "qualifier_integrity": qualifier_integrity,
        "completion": completion,
    }
    weights = {
        "hook": 0.18,
        "standalone": 0.13,
        "structure": 0.13,
        "payoff": 0.15,
        "specificity": 0.11,
        "duration_fit": 0.08,
        "density": 0.06,
        "qualifier_integrity": 0.08,
        "completion": 0.08,
    }
    score = 100.0 * sum(components[key] * weights[key] for key in weights)
    flags = []
    if _WEAK_OPEN.search(first_text):
        flags.append("context-dependent opening")
    if not _semantic_close(last_text):
        flags.append("weak ending")
    if not _QUALIFIER.search(text) and _EVIDENCE.search(text):
        flags.append("verify scientific qualification")
    if duration < 45:
        flags.append("short")
    speaker = segments[0].speaker if all(segment.speaker == segments[0].speaker for segment in segments) else None
    return ClipCandidate(
        id=f"clip-{round(start * 1000)}-{round(end * 1000)}",
        start=start,
        end=end,
        text=text,
        score=score,
        components=components,
        flags=flags,
        speaker=speaker,
    )


def select_with_agent(
    transcript_path: str | Path,
    candidates: Iterable[ClipCandidate],
    *,
    provider: str,
    project_root: str | Path,
    count: int = 10,
    brief: str = "",
) -> list[dict[str, Any]]:
    transcript = load_transcript(transcript_path)
    materialized = list(candidates)
    if not materialized:
        raise ValidationError("No clip candidates were supplied")
    candidate_payload = [
        {
            "id": item.id,
            "start": item.start,
            "end": item.end,
            "duration": item.duration,
            "score": item.score,
            "flags": item.flags,
            "text": item.text,
        }
        for item in materialized[:60]
    ]
    schema = {
        "type": "object",
        "required": ["clips"],
        "additionalProperties": False,
        "properties": {
            "clips": {
                "type": "array",
                "minItems": 1,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "required": ["candidate_id", "title", "hook", "editorial_reason", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "title": {"type": "string"},
                        "hook": {"type": "string"},
                        "editorial_reason": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "risk": {"type": "string"},
                    },
                },
            }
        },
    }
    prompt = f"""You are the senior short-form editor for an expert-led podcast.
Select at most {count} candidates that can become exceptional standalone clips.

Editorial bar:
- The first two seconds must create real curiosity without fabricating a hook.
- A clip must contain one coherent idea, enough context, and a satisfying payoff.
- Preserve uncertainty, scientific qualifiers, dissent, and material caveats.
- Prefer specificity, proof, mechanisms, strong disagreement, surprising explanations, or useful stories.
- Reject clips that begin with unresolved pronouns, require missing context, repeat another selection, or merely sound motivational.
- Do not reward density for its own sake. Natural conversation is allowed.
- Visual editing will support the idea; do not select weak ideas because they could be decorated.

Project brief:
{brief or 'No additional brief.'}

Transcript language: {transcript.language}
Candidates:
{json.dumps(candidate_payload, indent=2)}
"""
    result = run_subscription_agent(provider, prompt, cwd=project_root, schema=schema)
    by_id = {item.id: item for item in materialized}
    selected: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for choice in result.structured["clips"]:
        candidate = by_id.get(choice["candidate_id"])
        if candidate is None:
            continue
        if any(_overlap_ratio((candidate.start, candidate.end), interval) > 0.62 for interval in used):
            continue
        start, end = snap_to_words(transcript, candidate.start, candidate.end)
        selected.append(
            {
                "id": slugify(choice["title"]) or candidate.id,
                "candidate_id": candidate.id,
                "title": choice["title"],
                "hook": choice["hook"],
                "editorial_reason": choice["editorial_reason"],
                "confidence": choice["confidence"],
                "risk": choice.get("risk", ""),
                "start": start,
                "end": end,
                "duration": end - start,
                "source_text": candidate.text,
                "deterministic_score": candidate.score,
                "qualifier_terms": sorted(set(match.group(0).lower() for match in _QUALIFIER.finditer(candidate.text))),
            }
        )
        used.append((candidate.start, candidate.end))
    if not selected:
        raise ValidationError("Agent did not return any valid candidate IDs")
    return selected


def discover_and_save(
    transcript_path: str | Path,
    output_path: str | Path,
    *,
    maximum_candidates: int = 80,
) -> list[ClipCandidate]:
    transcript = load_transcript(transcript_path)
    candidates = discover_candidates(transcript, maximum_candidates=maximum_candidates)
    dump_json({"candidates": [item.to_dict() for item in candidates]}, output_path)
    return candidates


def snap_to_words(transcript: Transcript, start: float, end: float) -> tuple[float, float]:
    words = transcript.all_words()
    if not words:
        return start, end
    start_word = min(words, key=lambda word: abs(word.start - start))
    end_word = min(words, key=lambda word: abs(word.end - end))
    resolved_start = start_word.start if abs(start_word.start - start) <= 1.2 else start
    resolved_end = end_word.end if abs(end_word.end - end) <= 1.2 else end
    if resolved_end <= resolved_start:
        return start, end
    return resolved_start, resolved_end


def _semantic_close(text: str) -> bool:
    stripped = text.strip()
    return bool(re.search(r"[.!?][\"')\]]?$", stripped) or _PAYOFF.search(stripped[-180:]))


def _lexical_specificity(text: str) -> float:
    tokens = [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z'-]+", text)]
    if not tokens:
        return 0.0
    common = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "it", "that", "this", "you", "i", "we", "they", "to", "of", "in", "for", "on", "with"}
    informative = [token for token in tokens if token not in common and len(token) >= 4]
    return min(1.0, len(set(informative)) / max(12.0, len(tokens) * 0.38))


def _deduplicate(candidates: list[ClipCandidate], *, limit: int) -> list[ClipCandidate]:
    accepted: list[ClipCandidate] = []
    for candidate in candidates:
        if any(_overlap_ratio((candidate.start, candidate.end), (item.start, item.end)) > 0.72 for item in accepted):
            continue
        accepted.append(candidate)
        if len(accepted) >= limit:
            break
    return accepted


def _overlap_ratio(left: tuple[float, float], right: tuple[float, float]) -> float:
    overlap = max(0.0, min(left[1], right[1]) - max(left[0], right[0]))
    shortest = max(1e-9, min(left[1] - left[0], right[1] - right[0]))
    return overlap / shortest

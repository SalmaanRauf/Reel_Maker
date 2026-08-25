from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import run_subscription_agent
from .exceptions import ValidationError
from .transcript import load_transcript
from .util import compact_whitespace, dump_json


@dataclass(slots=True)
class ScriptBeat:
    label: str
    text: str
    visual_cue: str = ""
    estimated_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "visual_cue": self.visual_cue,
            "estimated_seconds": round(self.estimated_seconds, 2),
        }


@dataclass(slots=True)
class ScriptPackage:
    title: str
    hook: str
    beats: list[ScriptBeat]
    full_script: str
    estimated_seconds: float
    integrity_notes: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "hook": self.hook,
            "beats": [item.to_dict() for item in self.beats],
            "full_script": self.full_script,
            "estimated_seconds": round(self.estimated_seconds, 2),
            "integrity_notes": self.integrity_notes,
            "source_refs": self.source_refs,
        }


def write_script(
    brief: str,
    *,
    provider: str,
    project_root: str | Path,
    target_seconds: float = 60.0,
    voice: str = "natural, direct, credible, conversational",
    source_transcript: str | Path | None = None,
    source_notes: str | Path | None = None,
) -> ScriptPackage:
    if not brief.strip():
        raise ValidationError("A script brief is required")
    if not 10 <= target_seconds <= 1800:
        raise ValidationError("Target script duration must be between 10 and 1800 seconds")
    references = []
    source_text = ""
    if source_transcript:
        transcript = load_transcript(source_transcript)
        source_text = compact_whitespace(" ".join(segment.text for segment in transcript.segments))
        references.append(str(Path(source_transcript).expanduser().resolve()))
    if source_notes:
        notes_path = Path(source_notes).expanduser().resolve()
        if not notes_path.is_file():
            raise ValidationError(f"Source notes not found: {notes_path}")
        notes = notes_path.read_text(encoding="utf-8")
        source_text = compact_whitespace(f"{source_text} {notes}")
        references.append(str(notes_path))

    schema = {
        "type": "object",
        "required": ["title", "hook", "beats", "full_script", "integrity_notes"],
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "hook": {"type": "string"},
            "beats": {
                "type": "array",
                "minItems": 2,
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "required": ["label", "text", "visual_cue"],
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "text": {"type": "string"},
                        "visual_cue": {"type": "string"},
                    },
                },
            },
            "full_script": {"type": "string"},
            "integrity_notes": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
        },
    }
    source_section = source_text[:24000] if source_text else "No source material supplied; do not invent factual specificity beyond the brief."
    prompt = f"""Write a camera-ready spoken script.

Brief:
{brief.strip()}

Target duration: {target_seconds:.0f} seconds
Voice: {voice}

Source material:
{source_section}

Rules:
- Write natural spoken language, not essay prose or generic AI copy.
- Hook immediately with a truthful tension, question, consequence, or counterintuitive point.
- Develop one coherent idea through setup, mechanism/evidence/example, caveat, and payoff where applicable.
- Do not invent studies, numbers, quotes, personal experiences, credentials, outcomes, or certainty.
- When source material includes qualifiers, preserve them.
- Avoid fake outrage, clickbait, repetitive rhetorical questions, and filler transitions.
- `full_script` must be a clean teleprompter-ready version containing the hook and every beat in order.
- Visual cues are production notes, not spoken words.
- Integrity notes identify facts or qualifiers that must be checked or preserved.
"""
    result = run_subscription_agent(provider, prompt, cwd=project_root, schema=schema)
    payload = result.structured
    full_script = compact_whitespace(payload["full_script"])
    word_count = len(full_script.split())
    estimated_seconds = word_count / 2.45
    if estimated_seconds < target_seconds * 0.55 or estimated_seconds > target_seconds * 1.55:
        raise ValidationError(
            f"Generated script length is outside tolerance: estimated {estimated_seconds:.1f}s for a {target_seconds:.1f}s target"
        )
    beats = []
    for item in payload["beats"]:
        text = compact_whitespace(item["text"])
        beats.append(
            ScriptBeat(
                label=compact_whitespace(item["label"]),
                text=text,
                visual_cue=compact_whitespace(item["visual_cue"]),
                estimated_seconds=len(text.split()) / 2.45,
            )
        )
    package = ScriptPackage(
        title=compact_whitespace(payload["title"]),
        hook=compact_whitespace(payload["hook"]),
        beats=beats,
        full_script=full_script,
        estimated_seconds=estimated_seconds,
        integrity_notes=[compact_whitespace(item) for item in payload["integrity_notes"] if compact_whitespace(item)],
        source_refs=references,
    )
    _validate_script(package, source_text)
    return package


def save_script(package: ScriptPackage, output: str | Path) -> Path:
    destination = dump_json(package.to_dict(), output)
    text_path = destination.with_suffix(".txt")
    text_path.write_text(package.full_script + "\n", encoding="utf-8")
    return destination


def _validate_script(package: ScriptPackage, source_text: str) -> None:
    if not package.hook or not package.full_script:
        raise ValidationError("Generated script is missing its hook or full text")
    if package.hook.casefold() not in package.full_script.casefold():
        normalized_hook = re.sub(r"\W+", " ", package.hook.casefold()).strip()
        normalized_script = re.sub(r"\W+", " ", package.full_script.casefold()).strip()
        if normalized_hook not in normalized_script:
            raise ValidationError("The declared hook is not present in the teleprompter script")
    if source_text:
        source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", source_text))
        script_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", package.full_script))
        invented = script_numbers - source_numbers
        if invented:
            raise ValidationError(f"Generated script introduced unsupported numbers: {', '.join(sorted(invented))}")

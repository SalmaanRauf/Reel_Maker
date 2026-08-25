from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from .bridge import load_edit_plan
from .exceptions import DependencyError, ValidationError


@dataclass(slots=True, frozen=True)
class InterchangeClip:
    name: str
    source: str
    source_in: float
    source_out: float
    timeline_in: float
    timeline_out: float

    @property
    def duration(self) -> float:
        return self.timeline_out - self.timeline_in


def extract_clips(plan: Any) -> list[InterchangeClip]:
    payload = _mapping(plan)
    raw_segments = payload.get("segments") or payload.get("clips") or payload.get("timeline") or []
    if isinstance(raw_segments, dict):
        raw_segments = raw_segments.get("segments") or raw_segments.get("clips") or []
    if not isinstance(raw_segments, list):
        raise ValidationError("Edit plan does not contain a segment list")
    clips: list[InterchangeClip] = []
    cursor = 0.0
    for index, raw in enumerate(raw_segments):
        item = _mapping(raw)
        source = str(item.get("source_path") or item.get("source") or item.get("path") or item.get("asset_id") or item.get("source_asset_id") or "")
        source_in = _number(item, "source_in", "in_point", "in", "start", default=0.0)
        source_out = _number(item, "source_out", "out_point", "out", "end", default=None)
        duration = _number(item, "duration", default=None)
        if source_out is None and duration is not None:
            source_out = source_in + duration
        if source_out is None or source_out <= source_in:
            continue
        timeline_in = _number(item, "timeline_in", "timeline_start", "offset", default=cursor)
        timeline_out = _number(item, "timeline_out", "timeline_end", default=timeline_in + (source_out - source_in))
        if timeline_out <= timeline_in:
            timeline_out = timeline_in + (source_out - source_in)
        clips.append(
            InterchangeClip(
                name=str(item.get("name") or item.get("id") or f"clip-{index + 1}"),
                source=source,
                source_in=source_in,
                source_out=source_out,
                timeline_in=timeline_in,
                timeline_out=timeline_out,
            )
        )
        cursor = timeline_out
    if not clips:
        raise ValidationError("No interchangeable source clips were found in the plan")
    return clips


def export_edl(plan_path: str | Path, output: str | Path, *, fps: int = 30, title: str | None = None) -> Path:
    plan = load_edit_plan(plan_path)
    clips = extract_clips(plan)
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"TITLE: {title or Path(plan_path).stem}", "FCM: NON-DROP FRAME", ""]
    for index, clip in enumerate(clips, 1):
        reel = _reel_name(clip.source, index)
        lines.append(
            f"{index:03d}  {reel:<8} V     C        "
            f"{_timecode(clip.source_in, fps)} {_timecode(clip.source_out, fps)} "
            f"{_timecode(clip.timeline_in, fps)} {_timecode(clip.timeline_out, fps)}"
        )
        lines.append(f"* FROM CLIP NAME: {clip.name}")
        lines.append(f"* SOURCE FILE: {clip.source}")
        lines.append("")
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def export_fcpxml(
    plan_path: str | Path,
    output: str | Path,
    *,
    fps: int = 30,
    width: int = 1080,
    height: int = 1920,
    title: str | None = None,
) -> Path:
    plan = load_edit_plan(plan_path)
    clips = extract_clips(plan)
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame_duration = Fraction(1, fps)
    root = ET.Element("fcpxml", version="1.10")
    resources = ET.SubElement(root, "resources")
    ET.SubElement(
        resources,
        "format",
        id="r1",
        name=f"FFVideoFormat{height}p{fps}",
        frameDuration=_rational(frame_duration),
        width=str(width),
        height=str(height),
        colorSpace="1-1-1 (Rec. 709)",
    )
    asset_ids: dict[str, str] = {}
    for index, source in enumerate(dict.fromkeys(clip.source for clip in clips), 2):
        asset_id = f"r{index}"
        asset_ids[source] = asset_id
        asset = ET.SubElement(resources, "asset", id=asset_id, name=Path(source).name or source, start="0s", hasVideo="1", hasAudio="1")
        ET.SubElement(asset, "media-rep", kind="original-media", src=Path(source).resolve().as_uri() if Path(source).exists() else source)
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Podcast Studio")
    project = ET.SubElement(event, "project", name=title or Path(plan_path).stem)
    sequence = ET.SubElement(
        project,
        "sequence",
        format="r1",
        duration=_rational(Fraction(round(clips[-1].timeline_out * fps), fps)),
        tcStart="0s",
        tcFormat="NDF",
        audioLayout="stereo",
        audioRate="48k",
    )
    spine = ET.SubElement(sequence, "spine")
    for clip in clips:
        ET.SubElement(
            spine,
            "asset-clip",
            name=clip.name,
            ref=asset_ids[clip.source],
            offset=_rational(Fraction(round(clip.timeline_in * fps), fps)),
            start=_rational(Fraction(round(clip.source_in * fps), fps)),
            duration=_rational(Fraction(round(clip.duration * fps), fps)),
        )
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def export_otio(plan_path: str | Path, output: str | Path, *, fps: float = 30.0) -> Path:
    try:
        import opentimelineio as otio  # type: ignore
    except ImportError as exc:
        raise DependencyError("OpenTimelineIO export requires podcast-studio[otio]") from exc
    clips = extract_clips(load_edit_plan(plan_path))
    timeline = otio.schema.Timeline(name=Path(plan_path).stem)
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(track)
    cursor = 0.0
    for clip in clips:
        if clip.timeline_in > cursor:
            track.append(otio.schema.Gap(source_range=_otio_range(cursor, clip.timeline_in - cursor, fps, otio)))
        reference = otio.schema.ExternalReference(target_url=Path(clip.source).resolve().as_uri() if Path(clip.source).exists() else clip.source)
        item = otio.schema.Clip(
            name=clip.name,
            media_reference=reference,
            source_range=_otio_range(clip.source_in, clip.source_out - clip.source_in, fps, otio),
        )
        item.metadata["podcast_studio"] = {
            "timeline_in": clip.timeline_in,
            "timeline_out": clip.timeline_out,
            "source": clip.source,
        }
        track.append(item)
        cursor = clip.timeline_out
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(timeline, str(destination))
    return destination


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for name in ("to_dict", "model_dump", "dict"):
        method = getattr(value, name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, dict):
                return payload
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _number(payload: dict[str, Any], *keys: str, default: float | None) -> float | None:
    for key in keys:
        if payload.get(key) is not None:
            return float(payload[key])
    return default


def _timecode(seconds: float, fps: int) -> str:
    frames = max(0, round(seconds * fps))
    hours, frames = divmod(frames, fps * 3600)
    minutes, frames = divmod(frames, fps * 60)
    whole_seconds, frame = divmod(frames, fps)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}:{frame:02d}"


def _reel_name(source: str, index: int) -> str:
    token = "".join(character for character in Path(source).stem.upper() if character.isalnum())[:8]
    return token or f"REEL{index:04d}"[:8]


def _rational(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}s" if value.denominator != 1 else f"{value.numerator}s"


def _otio_range(start: float, duration: float, fps: float, otio: Any) -> Any:
    return otio.opentime.TimeRange(
        start_time=otio.opentime.RationalTime(start * fps, fps),
        duration=otio.opentime.RationalTime(duration * fps, fps),
    )

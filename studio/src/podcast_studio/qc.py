from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .aesthetic_qc import analyze_aesthetics
from .media import create_filmstrip, extract_frame, probe_media
from .models import EditPlan, QCCheck, QCReport, Transcript
from .process import require_binary, run_command
from .project import ProjectWorkspace
from .silence import parse_silencedetect
from .util import dump_json


def quality_control(
    workspace: ProjectWorkspace,
    render_path: str | Path,
    *,
    plan: EditPlan | None = None,
    transcript: Transcript | None = None,
    source_transcript: Transcript | None = None,
    contact_sheet: bool = True,
    inspection_frames: bool = True,
    cut_frames: bool | None = None,
) -> QCReport:
    if cut_frames is not None:
        inspection_frames = cut_frames
    path = Path(render_path).expanduser()
    if not path.is_absolute():
        path = workspace.root / path
    path = path.resolve()
    checks: list[QCCheck] = []
    if not path.is_file() or path.stat().st_size == 0:
        report = QCReport(str(path), [QCCheck("file", False, "error", "Render file is missing or empty")])
        _save(workspace, report, path.stem)
        return report

    probe = probe_media(path)
    checks.extend([
        QCCheck("video_stream", probe.has_video, "error", "Video stream present" if probe.has_video else "No video stream"),
        QCCheck("audio_stream", probe.has_audio, "error", "Audio stream present" if probe.has_audio else "No audio stream"),
    ])
    if plan:
        tolerance = max(.35, plan.duration * .01)
        delta = abs(probe.duration - plan.duration)
        checks.extend([
            QCCheck("duration", delta <= tolerance, "error", f"Rendered {probe.duration:.3f}s; expected {plan.duration:.3f}s", {"delta": delta, "tolerance": tolerance}),
            QCCheck("dimensions", probe.width == plan.width and probe.height == plan.height, "error", f"Rendered {probe.width}x{probe.height}; expected {plan.width}x{plan.height}"),
        ])
    else:
        checks.append(QCCheck("duration", probe.duration > .1, "error", f"Duration {probe.duration:.3f}s"))

    black = detect_black(path)
    black_total = sum(end - start for start, end in black)
    black_ratio = black_total / probe.duration if probe.duration else 0
    freezes = detect_freezes(path)
    max_freeze = max((end - start for start, end in freezes), default=0)
    silences = detect_output_silence(path, probe.duration)
    long_silences = [item for item in silences if item.end - item.start > 2]
    checks.extend([
        QCCheck("black_frames", black_ratio < .02, "warning", f"Black-frame ratio {black_ratio:.2%}", {"ranges": black, "seconds": black_total}),
        QCCheck("freezes", max_freeze < 2, "warning", f"Longest detected freeze {max_freeze:.2f}s", {"ranges": freezes}),
        QCCheck("long_silence", not long_silences, "warning", f"{len(long_silences)} silence interval(s) longer than 2s", {"ranges": [{"start": item.start, "end": item.end} for item in long_silences]}),
    ])

    loudness = measure_loudness(path)
    if loudness:
        target = plan.audio_target_lufs if plan else -16
        actual = _float(loudness.get("input_i"))
        peak = _float(loudness.get("input_tp"))
        peak_limit = plan.audio_true_peak if plan else -1
        checks.extend([
            QCCheck("loudness", actual is not None and abs(actual - target) <= 2, "warning", f"Integrated loudness {actual} LUFS; target {target} LUFS", loudness),
            QCCheck("true_peak", peak is not None and peak <= peak_limit + .5, "warning", f"True peak {peak} dBTP; target <= {peak_limit} dBTP", loudness),
        ])

    aesthetic: dict[str, Any] = {}
    if plan:
        aesthetic_report = analyze_aesthetics(plan, transcript=transcript, source_transcript=source_transcript)
        checks.extend(aesthetic_report.checks)
        aesthetic = aesthetic_report.to_dict()

    sheet_path: str | None = None
    if contact_sheet and probe.has_video:
        sheet = workspace.artifact_path("qc", f"{path.stem}-contact-sheet", ".jpg")
        try:
            create_filmstrip(path, sheet, frames=16, tile_columns=4)
            sheet_path = str(sheet)
        except Exception as exc:
            checks.append(QCCheck("contact_sheet", False, "warning", f"Could not generate contact sheet: {exc}"))

    frame_paths: list[str] = []
    inspection_times = _inspection_times(plan, probe.duration) if plan else _even_times(probe.duration, 10)
    if inspection_frames and probe.has_video:
        for index, at in enumerate(inspection_times):
            target = workspace.artifact_path("qc", f"{path.stem}-inspect-{index:03d}-{at:.3f}", ".jpg")
            try:
                extract_frame(path, target, at=at, width=540)
                frame_paths.append(str(target))
            except Exception:
                continue
        checks.append(QCCheck("inspection_frames", bool(frame_paths), "warning", f"Generated {len(frame_paths)} semantic inspection frame(s)", {"timestamps": inspection_times}))

    report = QCReport(
        str(path),
        checks,
        contact_sheet=sheet_path,
        cut_frames=frame_paths,
        technical={"probe": probe.raw, "loudness": loudness, "inspection_timestamps": inspection_times},
        aesthetic=aesthetic,
    )
    _save(workspace, report, path.stem)
    return report


def _inspection_times(plan: EditPlan | None, duration: float) -> list[float]:
    if not plan:
        return _even_times(duration, 10)
    values = {0.05, max(.05, min(duration - .05, duration * .5)), max(.05, duration - .05)}
    cursor = 0.0
    for index, segment in enumerate(plan.segments):
        values.add(max(.05, min(duration - .05, cursor + .04)))
        for keyframe in segment.motion.keyframes:
            if keyframe.time > .03:
                values.add(max(.05, min(duration - .05, cursor + keyframe.time)))
        if index < len(plan.segments) - 1:
            boundary = cursor + segment.duration - segment.transition_to_next.duration
            values.update({max(.05, boundary - .04), min(duration - .05, boundary + .04)})
        cursor += segment.duration - (segment.transition_to_next.duration if index < len(plan.segments) - 1 else 0)
    for collection in (plan.text_overlays, plan.overlays, plan.evidence_cards, plan.layout_events):
        for item in collection:
            values.update({max(.05, item.start + .04), min(duration - .05, item.end - .04)})
    for beat in plan.metadata.get("beat_map", []):
        if float(beat.get("strength", 0)) < .74:
            continue
        mapped = _source_to_timeline(plan, float(beat.get("start", 0)))
        if mapped is not None:
            values.add(max(.05, min(duration - .05, mapped + .04)))
    return sorted(round(item, 4) for item in values if .0 <= item <= duration)


def _source_to_timeline(plan: EditPlan, source_time: float) -> float | None:
    cursor = 0.0
    for index, segment in enumerate(plan.segments):
        if segment.source_start <= source_time <= segment.source_end:
            return cursor + source_time - segment.source_start
        cursor += segment.duration - (segment.transition_to_next.duration if index < len(plan.segments) - 1 else 0)
    return None


def _even_times(duration: float, count: int) -> list[float]:
    if duration <= .1:
        return [.0]
    return [round(max(.05, min(duration - .05, duration * (index + .5) / count)), 4) for index in range(count)]


def detect_black(path: str | Path, *, threshold: float = .98, min_duration: float = .2) -> list[tuple[float, float]]:
    result = run_command([require_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vf", f"blackdetect=d={min_duration}:pic_th={threshold}", "-an", "-f", "null", "-"], check=False)
    return [(float(start), float(end)) for start, end in re.findall(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", result.stderr)]


def detect_freezes(path: str | Path, *, noise_db: float = -50, min_duration: float = 1) -> list[tuple[float, float]]:
    result = run_command([require_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vf", f"freezedetect=n={noise_db}dB:d={min_duration}", "-an", "-f", "null", "-"], check=False)
    starts = [float(value) for value in re.findall(r"freeze_start:\s*([0-9.]+)", result.stderr)]
    ends = [float(value) for value in re.findall(r"freeze_end:\s*([0-9.]+)", result.stderr)]
    return [(start, ends[index]) for index, start in enumerate(starts) if index < len(ends) and ends[index] > start]


def detect_output_silence(path: str | Path, duration: float):
    result = run_command([require_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "silencedetect=noise=-45dB:d=1", "-f", "null", "-"], check=False)
    return parse_silencedetect(result.stderr, duration=duration)


def measure_loudness(path: str | Path) -> dict[str, Any] | None:
    result = run_command([require_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], check=False)
    matches = re.findall(r"\{\s*\"input_i\".*?\}", result.stderr, flags=re.DOTALL)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def _save(workspace: ProjectWorkspace, report: QCReport, name: str) -> Path:
    return dump_json(report.to_dict(), workspace.artifact_path("qc", f"{name}-report", ".json"))


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

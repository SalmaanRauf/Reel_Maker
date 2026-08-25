from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .captions import remap_transcript_to_plan, to_ass_for_plan
from .exceptions import ValidationError
from .ffmpeg_graph import (
    drawtext_text,
    filter_path,
    motion_filter,
    overlay_motion_filter,
    responsive_text_size,
    safe_expression,
    transition_name,
    validate_custom_filter,
)
from .models import (
    CaptionMode,
    EditPlan,
    EvidenceCard,
    LayoutEvent,
    LayoutKind,
    MediaAsset,
    OverlayKind,
    TextOverlay,
    Transcript,
    TransitionKind,
)
from .process import require_binary, run_command
from .project import ProjectWorkspace
from .transcript import load_transcript, to_srt, to_vtt
from .util import slugify

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


@dataclass(slots=True)
class RenderInput:
    index: int
    path: str
    kind: str
    options: list[str] = field(default_factory=list)
    owner: str | None = None


@dataclass(slots=True)
class RenderJob:
    output: str
    command: list[str]
    filter_graph: str
    filter_script: str
    caption_path: str | None
    expected_duration: float
    plan_id: str
    inputs: list[RenderInput]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RenderResult:
    output: str
    plan_id: str
    duration: float
    command: list[str]
    caption_path: str | None
    receipt: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InputRegistry:
    def __init__(self, args: list[str]):
        self.args = args
        self.inputs: list[RenderInput] = []
        self._by_key: dict[str, int] = {}

    def add(
        self,
        path: str | Path,
        *,
        kind: str,
        owner: str | None = None,
        loop: bool = False,
        stream_loop: bool = False,
        dedupe_key: str | None = None,
    ) -> int:
        resolved = str(Path(path).expanduser().resolve())
        key = dedupe_key or f"{kind}:{resolved}:{loop}:{stream_loop}"
        if key in self._by_key:
            return self._by_key[key]
        options: list[str] = []
        if loop:
            options.extend(["-loop", "1"])
        if stream_loop:
            options.extend(["-stream_loop", "-1"])
        self.args.extend(options)
        self.args.extend(["-i", resolved])
        index = len(self.inputs)
        self.inputs.append(RenderInput(index=index, path=resolved, kind=kind, options=options, owner=owner))
        self._by_key[key] = index
        return index


def render_plan(
    workspace: ProjectWorkspace,
    plan: EditPlan,
    output: str | Path,
    *,
    transcript: Transcript | None = None,
    preview: bool = False,
    overwrite: bool = True,
) -> RenderResult:
    job = compile_render(workspace, plan, output, transcript=transcript, preview=preview, overwrite=overwrite)
    run_command(job.command, cwd=workspace.root, timeout=None)
    destination = Path(job.output)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ValidationError(f"Renderer produced no output: {destination}")
    receipt = workspace.write_receipt(
        "render",
        inputs=[item.path for item in job.inputs],
        outputs=[str(destination)],
        command=job.command,
        metadata={
            "plan_id": plan.id,
            "preview": preview,
            "expected_duration": plan.duration,
            "filter_script": job.filter_script,
            "warnings": job.warnings,
        },
    )
    return RenderResult(
        str(destination), plan.id, plan.duration, job.command, job.caption_path, str(receipt), job.warnings
    )


def compile_render(
    workspace: ProjectWorkspace,
    plan: EditPlan,
    output: str | Path,
    *,
    transcript: Transcript | None = None,
    preview: bool = False,
    overwrite: bool = True,
) -> RenderJob:
    ffmpeg = require_binary("ffmpeg")
    destination = Path(output).expanduser()
    if not destination.is_absolute():
        destination = workspace.root / destination
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [ffmpeg, "-y" if overwrite else "-n", "-hide_banner", "-loglevel", "warning"]
    registry = InputRegistry(args)
    manifest = workspace.manifest()
    warnings: list[str] = []

    source_ids = _source_ids(plan)
    source_assets: dict[str, tuple[MediaAsset, Path]] = {}
    source_indices: dict[str, int] = {}
    for asset_id in source_ids:
        asset, path = workspace.resolve_asset(manifest.asset(asset_id))
        source_assets[asset_id] = asset, path
        source_indices[asset_id] = registry.add(path, kind="source", owner=asset_id, dedupe_key=f"source:{asset_id}")

    _validate_plan_sources(plan, source_assets)

    overlay_inputs: list[int] = []
    for index, overlay in enumerate(plan.overlays):
        path = workspace.resolve_project_path(overlay.path, must_exist=True)
        is_image = path.suffix.lower() in IMAGE_EXTENSIONS
        overlay_inputs.append(
            registry.add(path, kind="overlay", owner=f"overlay:{index}", loop=is_image, dedupe_key=f"overlay:{index}:{path}")
        )

    evidence_inputs: dict[int, int] = {}
    for index, card in enumerate(plan.evidence_cards):
        if not card.path:
            continue
        path = workspace.resolve_project_path(card.path, must_exist=True)
        is_image = path.suffix.lower() in IMAGE_EXTENSIONS
        evidence_inputs[index] = registry.add(
            path, kind="evidence", owner=f"evidence:{index}", loop=is_image, dedupe_key=f"evidence:{index}:{path}"
        )

    music_index: int | None = None
    if plan.music:
        path = workspace.resolve_project_path(plan.music.path, must_exist=True)
        music_index = registry.add(path, kind="music", owner="music", stream_loop=plan.music.loop, dedupe_key=f"music:{path}")

    sfx_inputs: list[int] = []
    for index, event in enumerate(plan.sound_effects):
        path = workspace.resolve_project_path(event.path, must_exist=True)
        sfx_inputs.append(registry.add(path, kind="sfx", owner=f"sfx:{index}", dedupe_key=f"sfx:{index}:{path}"))

    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    for index, segment in enumerate(plan.segments):
        video_label, audio_label = _compile_segment(
            filters,
            index=index,
            plan=plan,
            segment=segment,
            source_indices=source_indices,
            source_assets=source_assets,
        )
        video_labels.append(video_label)
        audio_labels.append(audio_label)

    video_label, audio_label = _join_segments(filters, plan, video_labels, audio_labels)

    if plan.global_color_filter:
        next_label = "v_global_grade"
        filters.append(f"[{video_label}]{validate_custom_filter(plan.global_color_filter)}[{next_label}]")
        video_label = next_label

    video_label = _compile_layout_events(
        filters,
        video_label=video_label,
        plan=plan,
        events=plan.layout_events,
        source_indices=source_indices,
        source_assets=source_assets,
        warnings=warnings,
    )

    video_label = _compile_overlays(
        filters,
        video_label=video_label,
        plan=plan,
        overlays=plan.overlays,
        input_indices=overlay_inputs,
    )

    video_label = _compile_evidence_cards(
        filters,
        video_label=video_label,
        plan=plan,
        cards=plan.evidence_cards,
        input_indices=evidence_inputs,
    )

    video_label = _compile_text_overlays(filters, video_label=video_label, plan=plan, overlays=plan.text_overlays, workspace=workspace)

    caption_path: Path | None = None
    transcript = transcript or (_load_plan_transcript(workspace, plan) if plan.transcript_path else None)
    if transcript and transcript.words:
        caption_path = _write_plan_caption_files(workspace, plan, transcript)
        if plan.caption_mode in {CaptionMode.BURN, CaptionMode.BOTH}:
            next_label = "v_captions"
            filters.append(f"[{video_label}]subtitles=filename='{filter_path(caption_path)}'[{next_label}]")
            video_label = next_label
    elif plan.caption_mode in {CaptionMode.BURN, CaptionMode.BOTH}:
        warnings.append("Caption burn requested but no word-timed transcript was available.")

    audio_label = _compile_censors(filters, audio_label=audio_label, plan=plan)
    audio_label = _compile_music(filters, audio_label=audio_label, plan=plan, music_index=music_index)
    audio_label = _compile_sound_effects(filters, audio_label=audio_label, plan=plan, input_indices=sfx_inputs)

    filters.append(
        f"[{audio_label}]highpass=f=70,lowpass=f=18000,"
        f"loudnorm=I={plan.audio_target_lufs:.2f}:TP={plan.audio_true_peak:.2f}:LRA=11,"
        "alimiter=limit=0.98:attack=5:release=50[a_final]"
    )
    audio_label = "a_final"

    filter_graph = ";\n".join(filters)
    filter_script = workspace.root / ".cache" / f"render-{slugify(plan.id)}.ffmpeg"
    filter_script.parent.mkdir(parents=True, exist_ok=True)
    filter_script.write_text(filter_graph + "\n", encoding="utf-8")

    args.extend(["-filter_complex_script", str(filter_script), "-map", f"[{video_label}]", "-map", f"[{audio_label}]"])
    args.extend(
        [
            "-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "26" if preview else "18",
            "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-b:a", "160k" if preview else "192k", "-ar", "48000", "-movflags", "+faststart",
            "-t", f"{plan.duration:.6f}", str(destination),
        ]
    )
    return RenderJob(
        output=str(destination), command=[str(item) for item in args], filter_graph=filter_graph,
        filter_script=str(filter_script), caption_path=str(caption_path) if caption_path else None,
        expected_duration=plan.duration, plan_id=plan.id, inputs=registry.inputs, warnings=warnings,
    )


def _source_ids(plan: EditPlan) -> list[str]:
    result: list[str] = []
    for segment in plan.segments:
        for asset_id in (segment.source_id, segment.audio_source_id):
            if asset_id and asset_id not in result:
                result.append(asset_id)
    for event in plan.layout_events:
        for asset_id in event.source_ids:
            if asset_id not in result:
                result.append(asset_id)
    return result


def _validate_plan_sources(plan: EditPlan, assets: dict[str, tuple[MediaAsset, Path]]) -> None:
    for segment in plan.segments:
        asset = assets[segment.source_id][0]
        if not asset.has_video:
            raise ValidationError(f"Video rendering requires a video stream: {segment.source_id}")
        if asset.duration and segment.source_end > asset.duration + 0.1:
            raise ValidationError(
                f"Plan segment exceeds source duration: {segment.source_id} {segment.source_end:.3f}s > {asset.duration:.3f}s"
            )
        audio_id = segment.audio_source_id or segment.source_id
        audio_asset = assets[audio_id][0]
        audio_start = segment.audio_source_start if segment.audio_source_start is not None else segment.source_start
        audio_end = segment.audio_source_end if segment.audio_source_end is not None else audio_start + segment.duration
        if audio_asset.duration and audio_end > audio_asset.duration + 0.1:
            raise ValidationError(f"Plan audio segment exceeds source duration: {audio_id}")


def _compile_segment(
    filters: list[str],
    *,
    index: int,
    plan: EditPlan,
    segment: Any,
    source_indices: dict[str, int],
    source_assets: dict[str, tuple[MediaAsset, Path]],
) -> tuple[str, str]:
    duration = segment.duration
    source_index = source_indices[segment.source_id]
    prefix = [f"trim=start={segment.source_start:.6f}:end={segment.source_end:.6f}", "setpts=PTS-STARTPTS", "settb=AVTB"]
    if segment.color_filter:
        prefix.append(validate_custom_filter(segment.color_filter))
    graph = motion_filter(
        segment.motion, segment.transform, width=plan.width, height=plan.height,
        fps=plan.fps, duration=duration, prefix_filters=prefix,
    )
    filters.append(f"[{source_index}:v:0]{graph}[v_seg_{index}]")

    audio_id = segment.audio_source_id or segment.source_id
    audio_index = source_indices[audio_id]
    audio_asset = source_assets[audio_id][0]
    audio_start = segment.audio_source_start if segment.audio_source_start is not None else segment.source_start
    audio_end = segment.audio_source_end if segment.audio_source_end is not None else audio_start + duration
    fade = min(0.012, duration / 5)
    if audio_asset.has_audio:
        audio_filters = [
            f"atrim=start={audio_start:.6f}:end={audio_end:.6f}", "asetpts=PTS-STARTPTS",
            "aresample=48000:async=1:first_pts=0", "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
            f"volume={segment.audio_gain_db:.3f}dB",
        ]
        if fade > 0:
            audio_filters.extend([f"afade=t=in:st=0:d={fade:.6f}", f"afade=t=out:st={max(0, duration - fade):.6f}:d={fade:.6f}"])
        filters.append(f"[{audio_index}:a:0]{','.join(audio_filters)}[a_seg_{index}]")
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[a_seg_{index}]")
    return f"v_seg_{index}", f"a_seg_{index}"


def _join_segments(filters: list[str], plan: EditPlan, video_labels: list[str], audio_labels: list[str]) -> tuple[str, str]:
    video_label = video_labels[0]
    audio_label = audio_labels[0]
    cursor = plan.segments[0].duration
    for index in range(1, len(plan.segments)):
        transition = plan.segments[index - 1].transition_to_next
        next_video = video_labels[index]
        next_audio = audio_labels[index]
        if transition.kind == TransitionKind.CUT or transition.duration <= 0:
            joined_video = f"v_join_{index}"
            joined_audio = f"a_join_{index}"
            filters.append(f"[{video_label}][{next_video}]concat=n=2:v=1:a=0[{joined_video}]")
            filters.append(f"[{audio_label}][{next_audio}]concat=n=2:v=0:a=1[{joined_audio}]")
            video_label, audio_label = joined_video, joined_audio
            cursor += plan.segments[index].duration
        else:
            duration = transition.duration
            offset = max(0.0, cursor - duration)
            joined_video = f"v_xfade_{index}"
            joined_audio = f"a_xfade_{index}"
            filters.append(
                f"[{video_label}][{next_video}]xfade=transition={transition_name(transition.kind)}:"
                f"duration={duration:.6f}:offset={offset:.6f}[{joined_video}]"
            )
            filters.append(f"[{audio_label}][{next_audio}]acrossfade=d={duration:.6f}:c1=tri:c2=tri[{joined_audio}]")
            video_label, audio_label = joined_video, joined_audio
            cursor += plan.segments[index].duration - duration
    return video_label, audio_label


def _compile_layout_events(
    filters: list[str], *, video_label: str, plan: EditPlan, events: Iterable[LayoutEvent],
    source_indices: dict[str, int], source_assets: dict[str, tuple[MediaAsset, Path]], warnings: list[str],
) -> str:
    for event_index, event in enumerate(events):
        duration = min(event.end, plan.duration) - event.start
        if duration <= 0:
            continue
        source_start_default = float(event.metadata.get("source_start", event.start))
        source_starts = event.metadata.get("source_start_by_id", {})
        labels: list[str] = []
        for source_order, asset_id in enumerate(event.source_ids):
            if asset_id not in source_indices:
                warnings.append(f"Layout event references unavailable source {asset_id}.")
                continue
            asset = source_assets[asset_id][0]
            source_start = float(source_starts.get(asset_id, source_start_default + asset.offset))
            source_end = min(asset.duration or source_start + duration, source_start + duration)
            if source_end <= source_start:
                continue
            label = f"layout_{event_index}_{source_order}"
            filters.append(
                f"[{source_indices[asset_id]}:v:0]trim=start={source_start:.6f}:end={source_end:.6f},"
                f"setpts=PTS-STARTPTS,fps={plan.fps:.6f},setsar=1[{label}]"
            )
            labels.append(label)
        if not labels:
            continue
        layout_label = _layout_canvas(filters, event, labels, plan, event_index)
        shifted = f"layout_shift_{event_index}"
        fade = min(0.08, duration / 3)
        filters.append(
            f"[{layout_label}]format=rgba,fade=t=in:st=0:d={fade:.6f}:alpha=1,"
            f"fade=t=out:st={max(0, duration - fade):.6f}:d={fade:.6f}:alpha=1,"
            f"setpts=PTS-STARTPTS+{event.start:.6f}/TB[{shifted}]"
        )
        next_label = f"v_layout_{event_index}"
        filters.append(
            f"[{video_label}][{shifted}]overlay=0:0:eof_action=pass:"
            f"enable='between(t,{event.start:.6f},{event.end:.6f})'[{next_label}]"
        )
        video_label = next_label
    return video_label


def _layout_canvas(filters: list[str], event: LayoutEvent, labels: list[str], plan: EditPlan, event_index: int) -> str:
    if len(labels) == 1:
        output = f"layout_canvas_{event_index}"
        filters.append(
            f"[{labels[0]}]scale={plan.width}:{plan.height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={plan.width}:{plan.height}[{output}]"
        )
        return output

    if event.kind in {LayoutKind.PICTURE_IN_PICTURE, LayoutKind.CONTENT_SHARE}:
        base = f"layout_base_{event_index}"
        inset = f"layout_inset_{event_index}"
        output = f"layout_canvas_{event_index}"
        filters.append(
            f"[{labels[0]}]scale={plan.width}:{plan.height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={plan.width}:{plan.height}[{base}]"
        )
        inset_w = max(2, round(plan.width * 0.34) // 2 * 2)
        inset_h = max(2, round(plan.height * 0.28) // 2 * 2)
        filters.append(
            f"[{labels[1]}]scale={inset_w}:{inset_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={inset_w}:{inset_h},pad={inset_w + 12}:{inset_h + 12}:6:6:color=white@0.92[{inset}]"
        )
        filters.append(f"[{base}][{inset}]overlay=W-w-{event.padding}:H-h-{event.padding}[{output}]")
        return output

    labels = labels[:4]
    if event.kind == LayoutKind.SPLIT_HORIZONTAL:
        columns, rows = 1, len(labels)
    elif event.kind in {LayoutKind.SPLIT_VERTICAL, LayoutKind.GROUP} and len(labels) == 2:
        columns, rows = 2, 1
    else:
        columns, rows = 2, math.ceil(len(labels) / 2)
    gap = max(0, event.gap)
    cell_w = max(2, ((plan.width - gap * (columns - 1)) // columns) // 2 * 2)
    cell_h = max(2, ((plan.height - gap * (rows - 1)) // rows) // 2 * 2)
    cell_labels: list[str] = []
    for index, label in enumerate(labels):
        cell = f"layout_cell_{event_index}_{index}"
        filters.append(
            f"[{label}]scale={cell_w}:{cell_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={cell_w}:{cell_h}[{cell}]"
        )
        cell_labels.append(cell)
    layout_positions: list[str] = []
    for index in range(len(cell_labels)):
        row, column = divmod(index, columns)
        layout_positions.append(f"{column * (cell_w + gap)}_{row * (cell_h + gap)}")
    output = f"layout_canvas_{event_index}"
    inputs = "".join(f"[{item}]" for item in cell_labels)
    filters.append(
        f"{inputs}xstack=inputs={len(cell_labels)}:layout={'|'.join(layout_positions)}:fill={event.background_color},"
        f"pad={plan.width}:{plan.height}:(ow-iw)/2:(oh-ih)/2:color={event.background_color}[{output}]"
    )
    return output


def _compile_overlays(
    filters: list[str], *, video_label: str, plan: EditPlan, overlays: list[Any], input_indices: list[int],
) -> str:
    for index, (overlay, input_index) in enumerate(zip(overlays, input_indices, strict=True)):
        start = max(0.0, overlay.start)
        end = min(plan.duration, overlay.end)
        duration = end - start
        if duration <= 0:
            continue
        if overlay.width:
            width = overlay.width
        elif overlay.kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN}:
            width = plan.width
        else:
            width = round(plan.width * 0.84)
        if overlay.height:
            height = overlay.height
        elif overlay.kind in {OverlayKind.BROLL, OverlayKind.FULLSCREEN}:
            height = plan.height
        else:
            height = round(plan.height * 0.62)
        width = max(2, width // 2 * 2)
        height = max(2, height // 2 * 2)
        source_end = overlay.source_end if overlay.source_end is not None else overlay.source_start + duration
        graph = overlay_motion_filter(
            overlay.motion, width=width, height=height, fps=plan.fps, duration=duration, fit=overlay.fit,
            opacity=overlay.opacity, transition_in=overlay.transition_in.duration, transition_out=overlay.transition_out.duration,
        )
        prepared = f"overlay_prepared_{index}"
        filters.append(
            f"[{input_index}:v:0]trim=start={overlay.source_start:.6f}:end={source_end:.6f},"
            f"setpts=PTS-STARTPTS,{graph},setpts=PTS-STARTPTS+{start:.6f}/TB[{prepared}]"
        )
        next_label = f"v_overlay_{index}"
        x = safe_expression(overlay.x)
        y = safe_expression(overlay.y)
        filters.append(
            f"[{video_label}][{prepared}]overlay=x='{x}':y='{y}':eof_action=pass:"
            f"enable='between(t,{start:.6f},{end:.6f})'[{next_label}]"
        )
        video_label = next_label
    return video_label


def _compile_evidence_cards(
    filters: list[str], *, video_label: str, plan: EditPlan, cards: list[EvidenceCard], input_indices: dict[int, int],
) -> str:
    for index, card in enumerate(cards):
        start, end = max(0.0, card.start), min(plan.duration, card.end)
        if end <= start:
            continue
        x = round(card.x * plan.width)
        y = round(card.y * plan.height)
        width = max(2, round(card.width * plan.width) // 2 * 2)
        height = max(2, round(card.height * plan.height) // 2 * 2)
        fade = min(0.12, (end - start) / 3)
        if index in input_indices:
            prepared = f"evidence_prepared_{index}"
            filters.append(
                f"[{input_indices[index]}:v:0]trim=duration={end - start:.6f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101216F2,format=rgba,"
                f"fade=t=in:st=0:d={fade:.6f}:alpha=1,fade=t=out:st={max(0, end - start - fade):.6f}:d={fade:.6f}:alpha=1,"
                f"setpts=PTS-STARTPTS+{start:.6f}/TB[{prepared}]"
            )
            next_label = f"v_evidence_image_{index}"
            filters.append(
                f"[{video_label}][{prepared}]overlay={x}:{y}:eof_action=pass:enable='between(t,{start:.6f},{end:.6f})'[{next_label}]"
            )
            video_label = next_label
        else:
            next_label = f"v_evidence_box_{index}"
            filters.append(
                f"[{video_label}]drawbox=x={x}:y={y}:w={width}:h={height}:color=0x101216E8:t=fill:"
                f"enable='between(t,{start:.6f},{end:.6f})'[{next_label}]"
            )
            video_label = next_label
        title_size, title = responsive_text_size(
            card.title, requested=max(30, round(plan.height * 0.031)), minimum=max(24, round(plan.height * 0.019)),
            maximum=max(40, round(plan.height * 0.05)), width=width, max_width_ratio=0.88, max_lines=2,
        )
        title_label = f"v_evidence_title_{index}"
        filters.append(
            f"[{video_label}]drawtext=text='{drawtext_text(title)}':fontcolor=white:fontsize={title_size}:"
            f"x={x}+({width}-text_w)/2:y={y}+{round(height * 0.08)}:"
            f"enable='between(t,{start:.6f},{end:.6f})'[{title_label}]"
        )
        video_label = title_label
        source_text = card.citation or card.source_name or ""
        if source_text:
            source_label = f"v_evidence_source_{index}"
            filters.append(
                f"[{video_label}]drawtext=text='{drawtext_text(source_text)}':fontcolor=0xB8BEC9:"
                f"fontsize={max(18, round(plan.height * 0.016))}:x={x}+{round(width * 0.06)}:"
                f"y={y}+{height}-{round(height * 0.08)}-text_h:"
                f"enable='between(t,{start:.6f},{end:.6f})'[{source_label}]"
            )
            video_label = source_label
    return video_label


def _compile_text_overlays(
    filters: list[str], *, video_label: str, plan: EditPlan, overlays: list[TextOverlay], workspace: ProjectWorkspace,
) -> str:
    for index, item in enumerate(sorted(overlays, key=lambda value: (value.start, value.priority))):
        start, end = max(0.0, item.start), min(plan.duration, item.end)
        if end <= start:
            continue
        font_size, text = responsive_text_size(
            item.text, requested=item.font_size, minimum=item.min_font_size, maximum=item.max_font_size,
            width=plan.width, max_width_ratio=item.max_width_ratio, max_lines=2,
        )
        font = ""
        font_path = item.font_file or (plan.brand.headline_font_file if item.role.value in {"headline", "statistic"} else plan.brand.font_file)
        if font_path:
            resolved = workspace.resolve_project_path(font_path, must_exist=True)
            font = f":fontfile='{filter_path(resolved)}'"
        fade = min(item.fade_seconds, (end - start) / 2)
        if fade > 0:
            alpha = (
                f"if(lt(t\\,{start + fade:.6f})\\,{item.opacity:.6f}*(t-{start:.6f})/{fade:.6f}\\,"
                f"if(gt(t\\,{end - fade:.6f})\\,{item.opacity:.6f}*({end:.6f}-t)/{fade:.6f}\\,{item.opacity:.6f}))"
            )
        else:
            alpha = f"{item.opacity:.6f}"
        x = safe_expression(item.x)
        y = safe_expression(item.y)
        if item.animation == "rise":
            y = f"({y})+12*max(0\\,1-(t-{start:.6f})/0.15)"
        box = f":box=1:boxcolor={item.box_color}:boxborderw={item.box_border}" if item.box else ":box=0"
        next_label = f"v_text_{index}"
        filters.append(
            f"[{video_label}]drawtext=text='{drawtext_text(text)}'{font}:fontsize={font_size}:"
            f"fontcolor={item.font_color}:x='{x}':y='{y}'{box}:alpha='{alpha}':"
            f"enable='between(t,{start:.6f},{end:.6f})'[{next_label}]"
        )
        video_label = next_label
    return video_label


def _compile_censors(filters: list[str], *, audio_label: str, plan: EditPlan) -> str:
    for index, event in enumerate(plan.censors):
        next_label = f"a_censor_{index}"
        expression = f"between(t\\,{event.start:.6f}\\,{event.end:.6f})"
        filters.append(f"[{audio_label}]volume=volume=0:enable='{expression}'[{next_label}]")
        audio_label = next_label
    beeps: list[str] = []
    for index, event in enumerate(plan.censors):
        if event.mode != "beep":
            continue
        delay = round(event.start * 1000)
        duration = event.end - event.start
        filters.append(
            f"sine=frequency={event.frequency}:sample_rate=48000:duration={duration:.6f},"
            f"volume=-12dB,afade=t=in:d=0.008,afade=t=out:st={max(0, duration - 0.012):.6f}:d=0.012,"
            f"adelay={delay}:all=1[a_beep_{index}]"
        )
        beeps.append(f"[a_beep_{index}]")
    if beeps:
        next_label = "a_with_beeps"
        filters.append(f"[{audio_label}]{''.join(beeps)}amix=inputs={1 + len(beeps)}:normalize=0:duration=first[{next_label}]")
        audio_label = next_label
    return audio_label


def _compile_music(filters: list[str], *, audio_label: str, plan: EditPlan, music_index: int | None) -> str:
    if not plan.music or music_index is None:
        return audio_label
    end = min(plan.music.end if plan.music.end is not None else plan.duration, plan.duration)
    duration = max(0.0, end - plan.music.start)
    if duration <= 0:
        return audio_label
    fade_out = min(plan.music.fade_out, duration / 2)
    fade_in = min(plan.music.fade_in, duration / 2)
    delay = round(plan.music.start * 1000)
    filters.append(
        f"[{music_index}:a:0]atrim=start=0:duration={duration:.6f},asetpts=PTS-STARTPTS,"
        "aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"volume={plan.music.gain_db:.3f}dB,afade=t=in:st=0:d={fade_in:.6f},"
        f"afade=t=out:st={max(0, duration - fade_out):.6f}:d={fade_out:.6f},adelay={delay}:all=1[a_music_raw]"
    )
    if plan.music.duck:
        filters.append(
            f"[a_music_raw][{audio_label}]sidechaincompress=threshold=0.022:ratio=9:attack=18:release=380:makeup=1[a_music_ducked]"
        )
        music_label = "a_music_ducked"
    else:
        music_label = "a_music_raw"
    filters.append(f"[{audio_label}][{music_label}]amix=inputs=2:normalize=0:duration=first[a_with_music]")
    return "a_with_music"


def _compile_sound_effects(
    filters: list[str], *, audio_label: str, plan: EditPlan, input_indices: list[int],
) -> str:
    labels: list[str] = []
    for index, (event, input_index) in enumerate(zip(plan.sound_effects, input_indices, strict=True)):
        duration = event.duration
        trim = f"atrim=start=0:duration={duration:.6f}," if duration else ""
        delay = round(event.start * 1000)
        filters.append(
            f"[{input_index}:a:0]{trim}asetpts=PTS-STARTPTS,aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={event.gain_db:.3f}dB,afade=t=in:d=0.008,adelay={delay}:all=1[a_sfx_{index}]"
        )
        labels.append(f"[a_sfx_{index}]")
    if not labels:
        return audio_label
    filters.append(f"[{audio_label}]{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first[a_with_sfx]")
    return "a_with_sfx"


def _write_plan_caption_files(workspace: ProjectWorkspace, plan: EditPlan, transcript: Transcript) -> Path:
    base = workspace.artifact_path("captions", plan.id, "")
    base.parent.mkdir(parents=True, exist_ok=True)
    mapped = remap_transcript_to_plan(transcript, plan)
    srt = base.with_suffix(".srt")
    vtt = base.with_suffix(".vtt")
    ass = base.with_suffix(".ass")
    srt.write_text(to_srt(mapped), encoding="utf-8")
    vtt.write_text(to_vtt(mapped), encoding="utf-8")
    ass.write_text(to_ass_for_plan(transcript, plan), encoding="utf-8")
    return ass


def _load_plan_transcript(workspace: ProjectWorkspace, plan: EditPlan) -> Transcript:
    assert plan.transcript_path
    source_ids = {segment.source_id for segment in plan.segments}
    asset_id = next(iter(source_ids)) if len(source_ids) == 1 else "unknown"
    return load_transcript(workspace.resolve_project_path(plan.transcript_path, must_exist=True), asset_id=asset_id)

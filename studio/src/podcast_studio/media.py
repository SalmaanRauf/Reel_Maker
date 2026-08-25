from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import ValidationError
from .models import MediaStream
from .process import CommandResult, require_binary, run_command, which


@dataclass(slots=True)
class MediaProbe:
    path: str
    duration: float
    format_name: str | None
    size: int | None
    bit_rate: int | None
    streams: list[MediaStream]
    raw: dict[str, Any]

    @property
    def width(self) -> int | None:
        stream = next((item for item in self.streams if item.codec_type == "video"), None)
        return stream.width if stream else None

    @property
    def height(self) -> int | None:
        stream = next((item for item in self.streams if item.codec_type == "video"), None)
        return stream.height if stream else None

    @property
    def has_audio(self) -> bool:
        return any(item.codec_type == "audio" for item in self.streams)

    @property
    def has_video(self) -> bool:
        return any(item.codec_type == "video" for item in self.streams)


def parse_rational(value: str | int | float | None) -> float | None:
    if value in (None, "", "0/0", "N/A"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


def probe_media(path: str | Path) -> MediaProbe:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Media file not found: {source}")
    result = run_command([require_binary("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-print_format", "json", source])
    payload = json.loads(result.stdout)
    format_data = payload.get("format", {})
    duration = _number(format_data.get("duration")) or 0.0
    streams: list[MediaStream] = []
    for raw in payload.get("streams", []):
        stream_duration = _number(raw.get("duration"))
        duration = max(duration, stream_duration or 0.0)
        streams.append(MediaStream(
            index=int(raw.get("index", len(streams))), codec_type=str(raw.get("codec_type", "unknown")), codec_name=raw.get("codec_name"),
            width=_integer(raw.get("width")), height=_integer(raw.get("height")), sample_rate=_integer(raw.get("sample_rate")), channels=_integer(raw.get("channels")),
            duration=stream_duration, frame_rate=parse_rational(raw.get("avg_frame_rate") or raw.get("r_frame_rate")),
            metadata={"pix_fmt": raw.get("pix_fmt"), "channel_layout": raw.get("channel_layout"), "tags": raw.get("tags", {}), "disposition": raw.get("disposition", {})}
        ))
    return MediaProbe(str(source), duration, format_data.get("format_name"), _integer(format_data.get("size")), _integer(format_data.get("bit_rate")), streams, payload)


def extract_audio(source: str | Path, output: str | Path, *, sample_rate: int = 16000, channels: int = 1, codec: str = "pcm_s16le") -> CommandResult:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run_command([require_binary("ffmpeg"), "-y", "-v", "error", "-i", source, "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-c:a", codec, destination])


def make_proxy(source: str | Path, output: str | Path, *, width: int = 960, video_bitrate: str = "1800k", audio_bitrate: str = "128k") -> CommandResult:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run_command([require_binary("ffmpeg"), "-y", "-v", "warning", "-i", source, "-vf", f"scale='min({width},iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-b:v", video_bitrate, "-c:a", "aac", "-b:a", audio_bitrate, "-movflags", "+faststart", destination])


def extract_frame(source: str | Path, output: str | Path, *, at: float, width: int | None = None) -> CommandResult:
    if at < 0:
        raise ValidationError("Frame timestamp cannot be negative")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    args: list[str | Path] = [require_binary("ffmpeg"), "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", source]
    if width:
        args.extend(["-vf", f"scale={width}:-2"])
    args.extend(["-frames:v", "1", destination])
    return run_command(args)


def create_filmstrip(source: str | Path, output: str | Path, *, start: float = 0, end: float | None = None, frames: int = 12, tile_columns: int = 4, thumb_width: int = 320) -> CommandResult:
    probe = probe_media(source)
    clip_end = min(end if end is not None else probe.duration, probe.duration)
    if clip_end <= start:
        raise ValidationError("Filmstrip end must be after start")
    duration = clip_end - start
    interval = max(duration / frames, 0.04)
    rows = math.ceil(frames / tile_columns)
    graph = f"fps=1/{interval:.6f},scale={thumb_width}:-2:flags=lanczos,tile={tile_columns}x{rows}:nb_frames={frames}:padding=4:margin=4"
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run_command([require_binary("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source, "-vf", graph, "-frames:v", "1", destination])


def create_waveform(source: str | Path, output: str | Path, *, width: int = 1600, height: int = 240) -> CommandResult:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return run_command([require_binary("ffmpeg"), "-y", "-v", "error", "-i", source, "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:split_channels=0", "-frames:v", "1", destination])


def denoise_audio(source: str | Path, output: str | Path, *, target_lufs: float = -16, true_peak: float = -1.5, strength: float = 12) -> CommandResult:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    filters = f"highpass=f=70,lowpass=f=18000,afftdn=nr={strength}:nf=-45:tn=1,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=100:makeup=1.5dB,loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
    return run_command([require_binary("ffmpeg"), "-y", "-v", "warning", "-i", source, "-vn", "-af", filters, destination])


def doctor() -> dict[str, Any]:
    binaries = {name: which(name) for name in ["ffmpeg", "ffprobe", "codex", "claude", "piper"]}
    binaries["whisper_cpp"] = which("whisper-cli") or which("whisper.cpp") or which("main")
    filters: set[str] = set()
    encoders: set[str] = set()
    if binaries["ffmpeg"]:
        result = run_command([binaries["ffmpeg"], "-hide_banner", "-filters"], check=False)
        filters = set(re.findall(r"^\s*[TSC\.]{3}\s+([\w]+)\s", result.stdout, flags=re.MULTILINE))
        result = run_command([binaries["ffmpeg"], "-hide_banner", "-encoders"], check=False)
        encoders = set(re.findall(r"^\s*[A-Z\.]{6}\s+([\w_-]+)\s", result.stdout, flags=re.MULTILINE))
    return {
        "binaries": binaries,
        "ffmpeg_filters": {name: name in filters for name in ["subtitles", "loudnorm", "afftdn", "sidechaincompress", "blackdetect", "freezedetect"]},
        "encoders": {name: name in encoders for name in ["libx264", "h264_videotoolbox", "h264_nvenc", "hevc_videotoolbox"]},
        "ready_for_core_editing": bool(binaries["ffmpeg"] and binaries["ffprobe"]),
        "ready_for_subscription_reasoning": bool(binaries["codex"] or binaries["claude"]),
    }


def _number(value: Any) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None

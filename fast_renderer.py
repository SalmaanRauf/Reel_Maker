"""
Fast Renderer - Direct FFmpeg rendering for maximum speed
Replaces MoviePy with native FFmpeg for 10x faster output.
"""
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class RenderConfig:
    """Rendering configuration"""
    output_width: int = 1080
    output_height: int = 1920
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "fast"  # ultrafast, fast, medium, slow
    crf: int = 23         # Quality (lower = better, 18-28 typical)
    audio_bitrate: str = "192k"


def extract_clip(
    video_path: Path,
    output_path: Path,
    start_time: float,
    end_time: float,
    config: RenderConfig = None
) -> Path:
    """
    Extract a clip from video with precise timestamps.
    Uses FFmpeg's seeking for fast extraction.
    """
    config = config or RenderConfig()
    duration = end_time - start_time
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-t", str(duration),
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg extract failed: {result.stderr}")
    
    return output_path


def apply_crop(
    video_path: Path,
    output_path: Path,
    crop_x: int,
    crop_y: int,
    crop_width: int,
    crop_height: int,
    config: RenderConfig = None
) -> Path:
    """
    Apply crop to video.
    """
    config = config or RenderConfig()
    
    crop_filter = f"crop={crop_width}:{crop_height}:{crop_x}:{crop_y}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", crop_filter,
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg crop failed: {result.stderr}")
    
    return output_path


def burn_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    config: RenderConfig = None
) -> Path:
    """
    Burn ASS/SRT subtitles into video.
    """
    config = config or RenderConfig()
    
    # Escape path for FFmpeg filter (handle colons and backslashes)
    sub_escaped = str(subtitle_path).replace("\\", "/").replace(":", r"\:")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{sub_escaped}'",
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle burn failed: {result.stderr}")
    
    return output_path


def overlay_video(
    base_video: Path,
    overlay_video: Path,
    output_path: Path,
    start_time: float,
    duration: float,
    position: str = "center",  # center, top, bottom
    opacity: float = 1.0,
    config: RenderConfig = None
) -> Path:
    """
    Overlay one video on another (for B-roll insertion).
    """
    config = config or RenderConfig()
    
    # Calculate position
    if position == "top":
        y_pos = "0"
    elif position == "bottom":
        y_pos = "H-h"
    else:  # center
        y_pos = "(H-h)/2"
    
    # Build filter
    filter_complex = (
        f"[1:v]setpts=PTS-STARTPTS,scale={config.output_width}:-1[ovr];"
        f"[0:v][ovr]overlay=(W-w)/2:{y_pos}:enable='between(t,{start_time},{start_time+duration})'"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(base_video),
        "-i", str(overlay_video),
        "-filter_complex", filter_complex,
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg overlay failed: {result.stderr}")
    
    return output_path


def merge_audio_tracks(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    audio_volume: float = 0.3,  # Background music volume
    config: RenderConfig = None
) -> Path:
    """
    Merge additional audio track (background music) with video.
    """
    config = config or RenderConfig()
    
    filter_complex = (
        f"[1:a]volume={audio_volume}[bg];"
        f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio merge failed: {result.stderr}")
    
    return output_path


def render_full_clip(
    source_video: Path,
    output_path: Path,
    start_time: float,
    end_time: float,
    crop_box: Optional[Tuple[int, int, int, int]] = None,  # (x, y, w, h)
    subtitle_path: Optional[Path] = None,
    config: RenderConfig = None
) -> Path:
    """
    Full clip render pipeline in a single FFmpeg call.
    Combines: extract, crop, subtitle burn.
    
    Args:
        source_video: Input video path
        output_path: Output video path
        start_time: Clip start time (seconds)
        end_time: Clip end time (seconds)
        crop_box: Optional crop coordinates (x, y, width, height)
        subtitle_path: Optional ASS subtitle file
        config: Render configuration
        
    Returns:
        Path to rendered clip
    """
    config = config or RenderConfig()
    duration = end_time - start_time
    
    # Build filter chain
    filters = []
    
    # Crop filter
    if crop_box:
        x, y, w, h = crop_box
        filters.append(f"crop={w}:{h}:{x}:{y}")
    
    # Scale to output size
    filters.append(f"scale={config.output_width}:{config.output_height}")
    
    # Subtitle burn (must be last in video filter chain)
    if subtitle_path and subtitle_path.exists():
        sub_escaped = str(subtitle_path).replace("\\", "/").replace(":", r"\:")
        filters.append(f"subtitles='{sub_escaped}'")
    
    # Combine video filters
    video_filter = ",".join(filters) if filters else None
    
    # Build command
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(source_video),
        "-t", str(duration),
    ]
    
    if video_filter:
        cmd.extend(["-vf", video_filter])
    
    cmd.extend([
        "-c:v", config.video_codec,
        "-preset", config.preset,
        "-crf", str(config.crf),
        "-c:a", config.audio_codec,
        "-b:a", config.audio_bitrate,
        str(output_path)
    ])
    
    console.print(f"[cyan]Rendering clip ({duration:.1f}s)...[/cyan]")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]Render failed: {result.stderr}[/red]")
        raise RuntimeError(f"FFmpeg render failed: {result.stderr}")
    
    console.print(f"[green]✓ Rendered: {output_path.name}[/green]")
    return output_path


def get_video_info(video_path: Path) -> dict:
    """Get video metadata using ffprobe"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    
    import json
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    # Test
    print("Fast Renderer - FFmpeg-based video processing")
    print(f"Default config: {RenderConfig()}")

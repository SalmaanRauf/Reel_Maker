#!/usr/bin/env python3
"""
BPC-157 Viral Clip Builder - High Quality Version
Carefully processes clips with proper face detection, caption positioning, and verification.
"""
import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
from rich.console import Console
from rich.panel import Panel

# Import our new modules
from transcriber import Word, Transcript
from cropper import PersonDetector, SpeakerTracker, generate_crop_trajectory
from caption_animator import generate_ass_subtitles, STYLES
from config import DEFAULT_CLIP_CONFIG

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
ASSET_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/assets")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# Output dimensions
OUT_W, OUT_H = 1080, 1920


@dataclass
class ClipSpec:
    """Specification for a viral clip"""
    clip_num: int
    title: str
    start_time: float  # in seconds
    end_time: float
    transcript_text: str
    hook_text: str
    captions: List[Tuple[str, float, float]]  # (text, start_offset, end_offset)
    vfx_notes: str = ""


def time_to_seconds(time_str: str) -> float:
    """Convert MM:SS or MM:SS.ms to seconds"""
    parts = time_str.replace(":", ".").split(".")
    if len(parts) >= 2:
        minutes = int(parts[0])
        seconds = int(parts[1])
        return minutes * 60 + seconds
    return float(time_str)


def extract_clip_segment(video_path: Path, start: float, end: float, output_path: Path) -> Path:
    """Extract a segment from the source video"""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]Extract failed: {result.stderr}[/red]")
        raise RuntimeError(result.stderr)
    return output_path


def analyze_faces_in_clip(video_path: Path, sample_rate: int = 10) -> Dict:
    """
    Analyze face positions throughout the clip.
    Returns info about where faces are and optimal crop region.
    """
    console.print("  [dim]→ Analyzing face positions...[/dim]")
    
    detector = PersonDetector(model_name="yolov8n.pt")
    
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    face_positions = []
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % sample_rate == 0:
            # Detect people
            detections = detector.detect(frame)
            if detections:
                # Get the largest/most central person
                best = max(detections, key=lambda d: (d.x2 - d.x1) * (d.y2 - d.y1))
                center_x = (best.x1 + best.x2) / 2
                center_y = (best.y1 + best.y2) / 2
                face_positions.append({
                    'frame': frame_idx,
                    'time': frame_idx / fps,
                    'center_x': center_x,
                    'center_y': center_y,
                    'box': (best.x1, best.y1, best.x2, best.y2)
                })
        
        frame_idx += 1
    
    cap.release()
    
    if not face_positions:
        console.print("  [yellow]⚠ No faces detected, using center crop[/yellow]")
        return {
            'avg_x': width / 2,
            'avg_y': height / 2,
            'width': width,
            'height': height,
            'positions': []
        }
    
    # Calculate average position
    avg_x = sum(p['center_x'] for p in face_positions) / len(face_positions)
    avg_y = sum(p['center_y'] for p in face_positions) / len(face_positions)
    
    console.print(f"  [green]✓ Found faces in {len(face_positions)} frames[/green]")
    console.print(f"  [dim]  Average position: ({avg_x:.0f}, {avg_y:.0f})[/dim]")
    
    return {
        'avg_x': avg_x,
        'avg_y': avg_y,
        'width': width,
        'height': height,
        'positions': face_positions
    }


def calculate_safe_crop(face_info: Dict, target_w: int = OUT_W, target_h: int = OUT_H) -> Tuple[int, int]:
    """
    Calculate crop position that keeps faces visible.
    Returns (crop_x, crop_y) for the top-left corner.
    """
    src_w = face_info['width']
    src_h = face_info['height']
    face_x = face_info['avg_x']
    face_y = face_info['avg_y']
    
    # Calculate crop dimensions to maintain 9:16 ratio
    # For 4K (3840x2160), to get 9:16 we need to crop width
    target_ratio = target_w / target_h  # 9/16 = 0.5625
    src_ratio = src_w / src_h
    
    if src_ratio > target_ratio:
        # Source is wider - crop from sides
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        # Source is taller - crop from top/bottom
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
    
    # Center crop on face position, but keep within bounds
    crop_x = int(face_x - crop_w / 2)
    crop_y = int(face_y - crop_h / 2)
    
    # Adjust to keep faces in frame with padding at top for captions
    # Move crop up slightly to give room for captions at bottom
    crop_y = int(face_y - crop_h * 0.4)  # Face in upper 40% of frame
    
    # Clamp to valid range
    crop_x = max(0, min(crop_x, src_w - crop_w))
    crop_y = max(0, min(crop_y, src_h - crop_h))
    
    console.print(f"  [dim]  Crop region: {crop_w}x{crop_h} at ({crop_x}, {crop_y})[/dim]")
    
    return crop_x, crop_y, crop_w, crop_h


def apply_smart_crop_ffmpeg(
    input_path: Path,
    output_path: Path,
    crop_x: int, crop_y: int,
    crop_w: int, crop_h: int,
    target_w: int = OUT_W, target_h: int = OUT_H
) -> Path:
    """Apply crop and scale using FFmpeg"""
    console.print("  [dim]→ Applying smart crop...[/dim]")
    
    filter_chain = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Crop failed: {result.stderr}")
    
    return output_path


def create_word_list_from_captions(captions: List[Tuple[str, float, float]]) -> List[Word]:
    """Convert caption tuples to Word objects for the ASS generator"""
    words = []
    for text, start, end in captions:
        # Split text into individual words
        text_words = text.split()
        if not text_words:
            continue
        
        word_duration = (end - start) / len(text_words)
        for i, w in enumerate(text_words):
            words.append(Word(
                text=w,
                start=start + i * word_duration,
                end=start + (i + 1) * word_duration,
                confidence=1.0
            ))
    return words


def generate_captions_ass(
    captions: List[Tuple[str, float, float]],
    output_path: Path,
    style: str = "hormozi"
) -> Path:
    """Generate animated ASS subtitles from caption list"""
    console.print("  [dim]→ Generating animated captions...[/dim]")
    
    # ASS header with proper styling - positioned in bottom third
    header = f"""[Script Info]
Title: BPC-157 Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Arial Rounded MT Bold,80,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,100,1
Style: Yellow,Arial Rounded MT Bold,80,&H00D7FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,100,1
Style: Hook,Arial Rounded MT Bold,70,&H00D7FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,4,2,50,50,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    for text, start, end in captions:
        # Determine style based on content
        if "🟣" in text or "⬆" in text or any(emoji in text for emoji in ["🔥", "💪", "⚡"]):
            style_name = "Yellow"
        elif start == captions[-1][1]:  # Last caption is the hook
            style_name = "Hook"
        else:
            style_name = "Main"
        
        # Format times
        def fmt_time(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = s % 60
            return f"{h}:{m:02d}:{sec:05.2f}"
        
        # Pop animation
        anim = r"{\fscx20\fscy20\t(0,50,\fscx110\fscy110)\t(50,100,\fscx100\fscy100)}"
        
        # Uppercase the text
        display_text = text.upper()
        
        events.append(f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},{style_name},,0,0,0,,{anim}{display_text}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write("\n".join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} caption lines[/green]")
    return output_path


def burn_captions_ffmpeg(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn ASS subtitles into video"""
    console.print("  [dim]→ Burning captions into video...[/dim]")
    
    # Escape the path for FFmpeg
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]Caption burn failed: {result.stderr}[/red]")
        raise RuntimeError(result.stderr)
    
    return output_path


def verify_clip(video_path: Path) -> Dict:
    """Verify the output clip meets quality standards"""
    console.print("  [dim]→ Verifying output...[/dim]")
    
    # Get video info
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    
    video_stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    
    width = int(video_stream['width'])
    height = int(video_stream['height'])
    duration = float(info['format']['duration'])
    
    # Check dimensions
    correct_dims = (width == OUT_W and height == OUT_H)
    
    # Check for black frames at start/end (basic check)
    cap = cv2.VideoCapture(str(video_path))
    cap.read()  # First frame
    ret, first_frame = cap.read()
    
    # Go to end
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 2)
    ret, last_frame = cap.read()
    cap.release()
    
    # Check if frames have content (not all black)
    first_ok = first_frame is not None and np.mean(first_frame) > 10
    last_ok = last_frame is not None and np.mean(last_frame) > 10
    
    verification = {
        'dimensions': f"{width}x{height}",
        'correct_dims': correct_dims,
        'duration': f"{duration:.1f}s",
        'has_content': first_ok and last_ok,
        'file_size': f"{video_path.stat().st_size / 1024 / 1024:.1f}MB"
    }
    
    if correct_dims and first_ok and last_ok:
        console.print("  [green]✓ Verification passed![/green]")
    else:
        console.print("  [yellow]⚠ Verification issues detected[/yellow]")
    
    return verification


def build_clip_1_purple_tricep() -> Path:
    """
    Build Clip 1: The Purple Tricep (ft. Larry Wheels)
    
    Timecode: 39:44 -> Start at 39*60+44 = 2384 seconds
    Duration: ~30 seconds based on transcript
    """
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep[/bold cyan]\n"
        "Featuring: Larry Wheels\n"
        "Hook: Celebrity Insider Story + Shocking Recovery",
        title="🎬 Building"
    ))
    
    # Correct timecodes from transcript search:
    # [3938.6s] I haven't seen that then I had a four weeks ago exactly I was lifting me my friend Adam Lair wheels were lifting.
    # ...
    # [3983.9s] And if this thing I can just you know, so we're going to talk about basically how to use this for the normal person now.
    START_TIME = 3938.0  # ~65:38
    END_TIME = 3984.0    # ~66:24 (~46 second clip)
    
    clip_name = "clip_1_purple_tricep"
    
    # Step 1: Extract raw segment
    console.print("\n[bold]Step 1: Extract segment[/bold]")
    raw_segment = TEMP_DIR / f"{clip_name}_raw.mp4"
    extract_clip_segment(VIDEO_PATH, START_TIME, END_TIME, raw_segment)
    console.print(f"  [green]✓ Extracted {END_TIME - START_TIME}s segment[/green]")
    
    # Step 2: Analyze faces
    console.print("\n[bold]Step 2: Analyze faces for smart crop[/bold]")
    face_info = analyze_faces_in_clip(raw_segment, sample_rate=15)
    
    # Step 3: Calculate safe crop region
    console.print("\n[bold]Step 3: Calculate safe crop[/bold]")
    crop_x, crop_y, crop_w, crop_h = calculate_safe_crop(face_info)
    
    # Step 4: Apply crop
    console.print("\n[bold]Step 4: Apply smart crop[/bold]")
    cropped_video = TEMP_DIR / f"{clip_name}_cropped.mp4"
    apply_smart_crop_ffmpeg(raw_segment, cropped_video, crop_x, crop_y, crop_w, crop_h)
    console.print("  [green]✓ Cropped to 9:16 vertical format[/green]")
    
    # Step 5: Generate captions
    console.print("\n[bold]Step 5: Generate animated captions[/bold]")
    
    # Captions based on ACTUAL transcript content:
    # [3938.6s] "I was lifting me my friend Adam, Larry Wheels were lifting"
    # [3945.5s] "I was doing too much weight trying to come with them"
    # [3947.9s] "And I hear in my tricep my friend picks up the bar and it's purple from here to here"
    # [3952.9s] "Yeah, I'm like, man, my surgery sucks"
    # [3955.3s] "I run home. I have a vial of BPC left. I put the BPC right into the tendon"
    # [3973.8s] "So like it almost doesn't make sense"
    # [3975.1s] "My my PTs like how is this possible?"
    # [3977.6s] "It's just purple from here to here"
    # [3979.5s] "And that's why so many athletes are running for this"
    captions = [
        ("I was lifting with Larry Wheels", 0.0, 4.0),
        ("I was doing too much weight trying to keep up", 4.0, 8.0),
        ("And I hear in my tricep...", 8.0, 10.0),
        ("It's PURPLE from here to here 🟣", 10.0, 14.0),
        ("Man, my surgery SUCKS", 14.0, 17.0),
        ("I run home, grab my vial of BPC", 17.0, 21.0),
        ("Put the BPC RIGHT into the tendon", 21.0, 25.0),
        ("Four weeks later...", 34.0, 37.0),
        ("My PT is like 'How is this POSSIBLE?'", 37.0, 41.0),
        ("That's why athletes are using this 💪", 41.0, 45.0),
        ("PURPLE 🟣 → Healed in 4 Weeks", 45.0, 46.0),
    ]
    
    ass_path = TEMP_DIR / f"{clip_name}_captions.ass"
    generate_captions_ass(captions, ass_path)
    
    # Step 6: Burn captions
    console.print("\n[bold]Step 6: Burn captions into video[/bold]")
    final_path = OUTPUT_DIR / f"{clip_name}.mp4"
    burn_captions_ffmpeg(cropped_video, ass_path, final_path)
    
    # Step 7: Verify
    console.print("\n[bold]Step 7: Verification[/bold]")
    verification = verify_clip(final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Clip 1 Complete![/bold green]\n\n"
        f"Output: [cyan]{final_path}[/cyan]\n"
        f"Dimensions: {verification['dimensions']}\n"
        f"Duration: {verification['duration']}\n"
        f"Size: {verification['file_size']}",
        title="Success"
    ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 BPC-157 Viral Clip Builder[/bold magenta]")
    console.print(f"Source: {VIDEO_PATH}")
    console.print(f"Output: {OUTPUT_DIR}\n")
    
    # Build Clip 1
    clip_path = build_clip_1_purple_tricep()
    
    console.print(f"\n[bold green]Done! Review the clip at:[/bold green]")
    console.print(f"  {clip_path}")

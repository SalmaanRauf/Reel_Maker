#!/usr/bin/env python3
"""
Clip Builder v3 - Clean captions, wider crop, better quality
"""
import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Dict
from dataclasses import dataclass
import numpy as np
import cv2
from rich.console import Console
from rich.panel import Panel

from cropper import PersonDetector

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TRANSCRIPT_PATH = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920


# Manual corrections for Whisper transcription errors
TRANSCRIPT_FIXES = {
    "Lair wheels": "Larry Wheels",
    "Lair Wheels": "Larry Wheels",
    "Adam Lair": "Adam, Larry",
    "viral BPC": "vial of BPC",
    "great to injury": "grade two injury",
    "the sucks": "this sucks",
    "my my my my PTs": "my PT's",
    "come with them": "keep up with them",
}


def fix_transcription(text: str) -> str:
    """Apply corrections to common Whisper errors"""
    result = text
    for wrong, correct in TRANSCRIPT_FIXES.items():
        result = result.replace(wrong, correct)
    return result


def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)


def get_segments_in_range(transcript: Dict, start: float, end: float) -> List[Dict]:
    """Get transcript segments with timing, applying fixes"""
    segments = []
    for seg in transcript['segments']:
        if seg['start'] >= start and seg['end'] <= end:
            text = fix_transcription(seg['text'].strip())
            segments.append({
                'text': text,
                'start': seg['start'] - start,
                'end': seg['end'] - start,
            })
    return segments


def generate_clean_ass(segments: List[Dict], output_path: Path) -> Path:
    """Generate ASS with cleaned segment-level captions"""
    console.print(f"  [dim]→ Generating {len(segments)} clean captions...[/dim]")
    
    header = f"""[Script Info]
Title: BPC-157 Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,68,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    events = []
    for seg in segments:
        text = seg['text']
        # Skip very short filler responses
        if text.lower().strip() in ['yeah.', 'yeah,', 'yep.', 'yeah']:
            continue
        
        # Pop animation
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        display_text = text.upper()
        events.append(f"Dialogue: 0,{fmt_time(seg['start'])},{fmt_time(seg['end'])},Default,,0,0,0,,{anim}{display_text}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} captions (filtered filler)[/green]")
    return output_path


def extract_segment(start: float, end: float, output: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(end - start),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output


def analyze_faces(video_path: Path, sample_rate: int = 15) -> Dict:
    """Analyze face positions"""
    console.print("  [dim]→ Analyzing faces...[/dim]")
    detector = PersonDetector(model_name="yolov8n.pt")
    
    cap = cv2.VideoCapture(str(video_path))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    positions = []
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % sample_rate == 0:
            detections = detector.detect(frame)
            if detections:
                # Track all people, not just the largest
                for d in detections:
                    positions.append({
                        'frame': frame_idx,
                        'x': (d.x1 + d.x2) / 2,
                        'y': (d.y1 + d.y2) / 2,
                        'w': d.x2 - d.x1,
                    })
        
        frame_idx += 1
    
    cap.release()
    
    if not positions:
        return {'center_x': width / 2, 'width': width, 'height': height}
    
    # Get range of all detected people
    min_x = min(p['x'] - p['w']/2 for p in positions)
    max_x = max(p['x'] + p['w']/2 for p in positions)
    center_x = (min_x + max_x) / 2
    
    console.print(f"  [green]✓ Detected people range: {min_x:.0f} - {max_x:.0f}[/green]")
    
    return {'center_x': center_x, 'min_x': min_x, 'max_x': max_x, 'width': width, 'height': height}


def smart_crop_wider(input_path: Path, output_path: Path, face_info: Dict) -> Path:
    """Crop video to 9:16 with WIDER view to keep faces in frame"""
    console.print("  [dim]→ Applying wider smart crop...[/dim]")
    
    src_w, src_h = face_info['width'], face_info['height']
    
    # Standard 9:16 crop width from height
    standard_crop_w = int(src_h * (9/16))  # 1215 for 4K
    
    # Add 15% extra width to avoid cutting faces
    wider_crop_w = int(standard_crop_w * 1.15)  # ~1397 pixels
    
    # Make sure we don't exceed source width
    crop_w = min(wider_crop_w, src_w)
    crop_h = src_h
    
    # Center on detected people
    center_x = face_info.get('center_x', src_w / 2)
    crop_x = int(center_x - crop_w / 2)
    crop_x = max(0, min(crop_x, src_w - crop_w))
    
    console.print(f"  [dim]  Crop: {crop_w}x{crop_h} at x={crop_x} (15% wider than standard)[/dim]")
    
    # Crop then scale to exact 9:16
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    console.print("  [green]✓ Applied wider crop[/green]")
    return output_path


def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn ASS captions into video"""
    console.print("  [dim]→ Burning captions...[/dim]")
    
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def build_clip_1():
    """Build Clip 1 with clean captions and wider crop"""
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep[/bold cyan]\n"
        "• Clean captions (fixed transcription errors)\n"
        "• Wider crop (15% more width)\n"
        "• Filtered filler words",
        title="🎬 Building v3"
    ))
    
    START = 3938.0
    END = 3984.0
    
    # Step 1: Load and clean transcript
    console.print("\n[bold]Step 1: Load & clean transcript[/bold]")
    transcript = load_transcript()
    segments = get_segments_in_range(transcript, START, END)
    console.print(f"  [green]✓ Loaded {len(segments)} segments with fixes applied[/green]")
    
    # Show cleaned segments
    console.print("  [dim]Preview (cleaned):[/dim]")
    for seg in segments[:5]:
        console.print(f"    [{seg['start']:5.1f}s] {seg['text'][:50]}...")
    
    # Step 2: Extract video
    console.print("\n[bold]Step 2: Extract video segment[/bold]")
    raw_path = TEMP_DIR / "clip1_raw.mp4"
    extract_segment(START, END, raw_path)
    console.print(f"  [green]✓ Extracted {END - START}s[/green]")
    
    # Step 3: Analyze faces
    console.print("\n[bold]Step 3: Analyze faces[/bold]")
    face_info = analyze_faces(raw_path)
    
    # Step 4: Wider crop
    console.print("\n[bold]Step 4: Smart crop (wider)[/bold]")
    cropped_path = TEMP_DIR / "clip1_cropped.mp4"
    smart_crop_wider(raw_path, cropped_path, face_info)
    
    # Step 5: Generate clean captions
    console.print("\n[bold]Step 5: Generate clean captions[/bold]")
    ass_path = TEMP_DIR / "clip1_clean.ass"
    generate_clean_ass(segments, ass_path)
    
    # Step 6: Burn captions
    console.print("\n[bold]Step 6: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep.mp4"
    burn_captions(cropped_path, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Done![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 Clip Builder v3 - Clean & Wide[/bold magenta]\n")
    build_clip_1()

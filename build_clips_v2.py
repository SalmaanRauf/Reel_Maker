#!/usr/bin/env python3
"""
Clip Builder v2 - Uses actual Whisper word timestamps for captions
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


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float = 1.0


def load_transcript() -> Dict:
    """Load the Whisper transcript JSON"""
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)


def get_words_in_range(transcript: Dict, start_time: float, end_time: float) -> List[Word]:
    """Extract all words within a time range from the transcript"""
    words = []
    for segment in transcript['segments']:
        if 'words' not in segment:
            continue
        for w in segment['words']:
            if start_time <= w['start'] <= end_time:
                words.append(Word(
                    text=w['text'],
                    start=w['start'] - start_time,  # Relative to clip start
                    end=w['end'] - start_time,
                    confidence=w.get('confidence', 1.0)
                ))
    return words


def group_words_into_phrases(words: List[Word], max_words: int = 5, max_duration: float = 3.0) -> List[Tuple[str, float, float]]:
    """
    Group words into readable phrases for captions.
    Returns list of (text, start_time, end_time)
    """
    if not words:
        return []
    
    phrases = []
    current_words = []
    phrase_start = None
    
    for word in words:
        if phrase_start is None:
            phrase_start = word.start
        
        current_words.append(word.text.strip())
        
        # End phrase if: too many words, too long duration, or punctuation
        should_break = (
            len(current_words) >= max_words or
            (word.end - phrase_start) >= max_duration or
            word.text.strip().endswith(('.', '?', '!', ','))
        )
        
        if should_break and current_words:
            text = ' '.join(current_words)
            phrases.append((text, phrase_start, word.end))
            current_words = []
            phrase_start = None
    
    # Don't forget remaining words
    if current_words:
        text = ' '.join(current_words)
        phrases.append((text, phrase_start, words[-1].end))
    
    return phrases


def generate_synced_ass(phrases: List[Tuple[str, float, float]], output_path: Path) -> Path:
    """Generate ASS subtitles with proper timing from Whisper data"""
    console.print(f"  [dim]→ Generating {len(phrases)} synced captions...[/dim]")
    
    header = f"""[Script Info]
Title: BPC-157 Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    events = []
    for text, start, end in phrases:
        # Pop animation effect
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        display_text = text.upper()
        events.append(f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Default,,0,0,0,,{anim}{display_text}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(events))
    
    return output_path


def extract_segment(start: float, end: float, output: Path) -> Path:
    """Extract video segment"""
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
    """Analyze face positions for smart cropping"""
    console.print("  [dim]→ Analyzing faces...[/dim]")
    detector = PersonDetector(model_name="yolov8n.pt")
    
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
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
                best = max(detections, key=lambda d: (d.x2 - d.x1) * (d.y2 - d.y1))
                positions.append(((best.x1 + best.x2) / 2, (best.y1 + best.y2) / 2))
        
        frame_idx += 1
    
    cap.release()
    
    if not positions:
        return {'x': width / 2, 'y': height / 2, 'w': width, 'h': height}
    
    avg_x = sum(p[0] for p in positions) / len(positions)
    avg_y = sum(p[1] for p in positions) / len(positions)
    console.print(f"  [green]✓ Found {len(positions)} face positions[/green]")
    
    return {'x': avg_x, 'y': avg_y, 'w': width, 'h': height}


def smart_crop(input_path: Path, output_path: Path, face_info: Dict) -> Path:
    """Crop video to 9:16 centered on face"""
    console.print("  [dim]→ Applying smart crop...[/dim]")
    
    src_w, src_h = face_info['w'], face_info['h']
    target_ratio = OUT_W / OUT_H
    
    crop_h = src_h
    crop_w = int(src_h * target_ratio)
    
    crop_x = int(face_info['x'] - crop_w / 2)
    crop_y = 0  # Keep full height
    
    crop_x = max(0, min(crop_x, src_w - crop_w))
    
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={OUT_W}:{OUT_H}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
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
    """Build Clip 1: Purple Tricep with REAL caption timing"""
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep[/bold cyan]\n"
        "Using ACTUAL Whisper timestamps for captions",
        title="🎬 Building"
    ))
    
    # Correct timestamps from transcript
    START = 3938.0
    END = 3984.0
    
    # Step 1: Load transcript and extract words
    console.print("\n[bold]Step 1: Load transcript[/bold]")
    transcript = load_transcript()
    words = get_words_in_range(transcript, START, END)
    console.print(f"  [green]✓ Loaded {len(words)} words from Whisper transcript[/green]")
    
    # Step 2: Group into phrases
    console.print("\n[bold]Step 2: Group words into phrases[/bold]")
    phrases = group_words_into_phrases(words, max_words=5, max_duration=2.5)
    console.print(f"  [green]✓ Created {len(phrases)} caption phrases[/green]")
    
    # Show first few for verification
    console.print("  [dim]Preview:[/dim]")
    for text, start, end in phrases[:5]:
        console.print(f"    [{start:5.2f}s - {end:5.2f}s] {text}")
    
    # Step 3: Extract video segment
    console.print("\n[bold]Step 3: Extract video segment[/bold]")
    raw_path = TEMP_DIR / "clip1_raw.mp4"
    extract_segment(START, END, raw_path)
    console.print(f"  [green]✓ Extracted {END - START}s segment[/green]")
    
    # Step 4: Analyze faces
    console.print("\n[bold]Step 4: Analyze faces[/bold]")
    face_info = analyze_faces(raw_path)
    
    # Step 5: Smart crop
    console.print("\n[bold]Step 5: Smart crop to 9:16[/bold]")
    cropped_path = TEMP_DIR / "clip1_cropped.mp4"
    smart_crop(raw_path, cropped_path, face_info)
    console.print("  [green]✓ Cropped to vertical format[/green]")
    
    # Step 6: Generate captions with real timing
    console.print("\n[bold]Step 6: Generate synced captions[/bold]")
    ass_path = TEMP_DIR / "clip1_captions.ass"
    generate_synced_ass(phrases, ass_path)
    console.print("  [green]✓ Generated ASS with Whisper timing[/green]")
    
    # Step 7: Burn captions
    console.print("\n[bold]Step 7: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep.mp4"
    burn_captions(cropped_path, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Done![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 Clip Builder v2 - Whisper Synced Captions[/bold magenta]\n")
    build_clip_1()

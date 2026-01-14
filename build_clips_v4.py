#!/usr/bin/env python3
"""
Clip Builder v4 - Word-by-word captions + zoom out
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
import cv2
from rich.console import Console
from rich.panel import Panel

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TRANSCRIPT_PATH = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920


# Transcription fixes
WORD_FIXES = {
    "lair": "Larry",
    "Lair": "Larry",
    "viral": "vial",  # "viral BPC" -> "vial"
}


def fix_word(word: str) -> str:
    """Fix common transcription errors"""
    return WORD_FIXES.get(word, word)


def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)


def get_word_level_captions(transcript: Dict, start: float, end: float, words_per_caption: int = 3) -> List[Dict]:
    """
    Get word-level captions grouped into small chunks (2-4 words each).
    This creates short, punchy captions that appear and disappear quickly.
    """
    all_words = []
    for seg in transcript['segments']:
        if 'words' not in seg:
            continue
        for w in seg['words']:
            if start <= w['start'] <= end:
                all_words.append({
                    'text': fix_word(w['text'].strip()),
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                })
    
    # Group words into small chunks
    captions = []
    for i in range(0, len(all_words), words_per_caption):
        chunk = all_words[i:i + words_per_caption]
        if not chunk:
            continue
        
        text = ' '.join(w['text'] for w in chunk)
        cap_start = chunk[0]['start']
        cap_end = chunk[-1]['end']
        
        captions.append({
            'text': text,
            'start': cap_start,
            'end': cap_end,
        })
    
    return captions


def generate_word_level_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with short word-level captions"""
    console.print(f"  [dim]→ Generating {len(captions)} word-level captions...[/dim]")
    
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
    for cap in captions:
        text = cap['text'].upper()
        # Skip single filler words
        if text.lower().strip() in ['yeah', 'yep', 'yeah,', 'yep,']:
            continue
        
        # Pop animation
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{fmt_time(cap['start'])},{fmt_time(cap['end'])},Default,,0,0,0,,{anim}{text}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} short captions[/green]")
    return output_path


def extract_and_zoom_out(start: float, end: float, output: Path, zoom_out_pct: float = 0.20) -> Path:
    """
    Extract video segment and zoom out by adding padding.
    zoom_out_pct=0.20 means show 20% more (scale to 80% of frame, add black bars)
    """
    console.print(f"  [dim]→ Extracting with {int(zoom_out_pct*100)}% zoom out...[/dim]")
    
    duration = end - start
    scale_factor = 1 - zoom_out_pct  # 0.80 means scale to 80%
    
    # Calculate the scaled dimensions that maintain 9:16 aspect ratio
    # We'll scale the video down and pad it to 1080x1920
    
    # First extract at original size, then scale and pad
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(VIDEO_PATH),
        "-t", str(duration),
        # Scale down and pad to maintain 9:16 with black bars
        "-vf", f"scale=-1:ih*{scale_factor},pad=iw:ih/(0.8):0:(ih-ih*{scale_factor})/2:black,crop=ih*9/16:ih,scale={OUT_W}:{OUT_H}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]FFmpeg error: {result.stderr}[/red]")
        raise RuntimeError(result.stderr)
    
    console.print(f"  [green]✓ Extracted with zoom out[/green]")
    return output


def extract_simple_zoom_out(start: float, end: float, output: Path) -> Path:
    """
    Simpler approach: crop 9:16, centered, then scale down and add padding
    """
    console.print("  [dim]→ Extracting with 20% zoom out (centered)...[/dim]")
    
    duration = end - start
    
    # Step 1: Extract the raw segment
    raw_path = TEMP_DIR / "clip1_raw_full.mp4"
    cmd1 = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", str(VIDEO_PATH), "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(raw_path)
    ]
    subprocess.run(cmd1, capture_output=True, check=True)
    
    # Get original dimensions
    probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", 
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    w, h = map(int, result.stdout.strip().split(','))
    
    # For 4K (3840x2160), a 9:16 crop would be 1215x2160
    # To zoom out 20%, we take a WIDER crop (more content) then scale to fit
    # Standard crop_w = 2160 * 9/16 = 1215
    # Zoomed out (show 20% more) = 1215 * 1.20 = 1458 
    
    crop_h = h
    crop_w_standard = int(h * 9 / 16)  # 1215
    crop_w_zoomed = int(crop_w_standard * 1.25)  # 25% more width to show more scene
    crop_w_zoomed = min(crop_w_zoomed, w)  # Don't exceed source width
    
    # Center the crop
    crop_x = (w - crop_w_zoomed) // 2
    
    console.print(f"  [dim]  Source: {w}x{h}, Crop: {crop_w_zoomed}x{crop_h} at x={crop_x}[/dim]")
    
    # Crop wider, scale to 9:16 (this will add slight letterboxing)
    cmd2 = [
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w_zoomed}:{crop_h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output)
    ]
    subprocess.run(cmd2, capture_output=True, check=True)
    
    console.print(f"  [green]✓ Applied 20% zoom out with centered crop[/green]")
    return output


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
    """Build Clip 1 with word-level captions and zoom out"""
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep[/bold cyan]\n"
        "• Word-level captions (2-3 words each)\n"
        "• 20% zoom out (no face cropping)",
        title="🎬 Building v4"
    ))
    
    START = 3938.0
    END = 3984.0
    
    # Step 1: Load transcript and get word-level captions
    console.print("\n[bold]Step 1: Load transcript (word-level)[/bold]")
    transcript = load_transcript()
    captions = get_word_level_captions(transcript, START, END, words_per_caption=3)
    console.print(f"  [green]✓ Created {len(captions)} short captions[/green]")
    
    # Preview
    console.print("  [dim]Preview:[/dim]")
    for cap in captions[:8]:
        console.print(f"    [{cap['start']:5.2f}s] {cap['text']}")
    
    # Step 2: Extract with zoom out
    console.print("\n[bold]Step 2: Extract with 20% zoom out[/bold]")
    cropped_path = TEMP_DIR / "clip1_zoomed.mp4"
    extract_simple_zoom_out(START, END, cropped_path)
    
    # Step 3: Generate word-level captions
    console.print("\n[bold]Step 3: Generate word-level captions[/bold]")
    ass_path = TEMP_DIR / "clip1_words.ass"
    generate_word_level_ass(captions, ass_path)
    
    # Step 4: Burn captions
    console.print("\n[bold]Step 4: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep.mp4"
    burn_captions(cropped_path, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Done![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 Clip Builder v4 - Word Captions + Zoom Out[/bold magenta]\n")
    build_clip_1()

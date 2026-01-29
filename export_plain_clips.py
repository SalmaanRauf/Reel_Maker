#!/usr/bin/env python3
"""
Plain Clip Exporter
Exports all 11 clips without any captions or titles - just the raw cropped video.
"""
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips/plain_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

OUT_W, OUT_H = 1080, 1920

CLIPS = [
    {"id": 1, "name": "clip_01_purple_tricep", "start": 3938.0, "end": 3984.0},
    {"id": 2, "name": "clip_02_rat_acl", "start": 2305.0, "end": 2334.0},
    {"id": 3, "name": "clip_03_blocks_amphetamines", "start": 2318.0, "end": 2348.0},
    {"id": 4, "name": "clip_04_bolus_protocol", "start": 4175.0, "end": 4210.0},
    {"id": 5, "name": "clip_05_oral_works", "start": 4012.0, "end": 4042.0},
    {"id": 6, "name": "clip_06_fda_loophole", "start": 4031.0, "end": 4061.0},
    {"id": 7, "name": "clip_07_where_inject", "start": 4146.0, "end": 4184.0},
    {"id": 8, "name": "clip_08_cancer_truth", "start": 5073.0, "end": 5110.0},
    {"id": 9, "name": "clip_09_gateway_drug", "start": 80.0, "end": 110.0},
    {"id": 10, "name": "clip_10_not_magic", "start": 3918.0, "end": 3945.0},
    {"id": 11, "name": "clip_11_hgh_stack", "start": 4264.0, "end": 4303.0},
]

def extract_plain_clip(clip: dict) -> Path:
    """Extract and crop video without any overlays"""
    name = clip['name']
    start = clip['start']
    end = clip['end']
    duration = end - start
    
    console.print(f"  Extracting {name} ({duration:.0f}s)...")
    
    # Extract raw segment
    raw_path = TEMP_DIR / "temp_plain.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", str(raw_path)
    ], capture_output=True, check=True)
    
    # Get dimensions for cropping
    res = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)
    ], capture_output=True, text=True)
    w, h = map(int, res.stdout.strip().split(','))
    
    # Center crop for 9:16
    crop_w = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    # Final output with crop and scale
    output_path = OUTPUT_DIR / f"{name}_plain.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ], capture_output=True, check=True)
    
    console.print(f"    ✓ {output_path.name}")
    return output_path

def main():
    console.print(Panel.fit(
        "[bold cyan]Plain Clip Exporter[/bold cyan]\n"
        "• No captions, no titles\n"
        "• Just cropped 9:16 video",
        title="Export"
    ))
    
    for clip in CLIPS:
        extract_plain_clip(clip)
    
    console.print(Panel.fit(
        f"[bold green]✅ All {len(CLIPS)} plain clips exported![/bold green]\n"
        f"Output: {OUTPUT_DIR}",
        title="Complete"
    ))

if __name__ == "__main__":
    main()

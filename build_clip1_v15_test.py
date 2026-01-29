#!/usr/bin/env python3
"""
Clip Builder v15 - Video-Based PIP (10-second test)
Uses short reference video loops for PIP instead of static images.
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Tuple
from rich.console import Console
from rich.panel import Panel

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920
PIP_SIZE = 280
PIP_PADDING = 25
PIP_Y = 60

# Crop coordinates (verified on static frames)
# Source is 3840x2160
# For main view (9:16): crop=1350:2160:1245:0 (center)
# For PIP face: crop=1000:1000:1200:300 (left speaker)
#               crop=1000:1000:1400:300 (right speaker)

MAIN_CROP = "1350:2160:1245:0"  # Center crop for 9:16
LEFT_FACE_CROP = "1000:1000:1200:300"
RIGHT_FACE_CROP = "1000:1000:1400:300"

def build_test_clip():
    """Build 10-second test with video-based PIP"""
    console.print(Panel.fit(
        "[bold cyan]🔬 v15 Test Build (10 seconds)[/bold cyan]\n"
        "• Video-based PIP (not static image)\n"
        "• Rectangular PIP in corner\n"
        "• Using verified crop coordinates",
        title="Test Run"
    ))
    
    # For this 10-second test:
    # Use 3940-3950 (left speaker mainly)
    # PIP shows host (extracted from 3981-3985)
    
    START, END = 3940.0, 3950.0  # 10 seconds
    HOST_REF_START = 3981.0  # Where host face is visible
    
    # Step 1: Extract main video (left speaker)
    console.print("\n[bold]Step 1: Extract main video (10s)[/bold]")
    main_raw = TEMP_DIR / "v15_main_raw.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(START), "-i", str(VIDEO_PATH),
        "-t", "10", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "aac", str(main_raw)
    ], capture_output=True, check=True)
    console.print("  [green]✓ Main extracted[/green]")
    
    # Step 2: Extract host reference (5s loop for PIP)
    console.print("\n[bold]Step 2: Extract host PIP reference (5s)[/bold]")
    pip_ref = TEMP_DIR / "v15_pip_ref.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(HOST_REF_START), "-i", str(VIDEO_PATH),
        "-t", "5",
        "-vf", f"crop={RIGHT_FACE_CROP},scale={PIP_SIZE}:{PIP_SIZE}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-an", str(pip_ref)
    ], capture_output=True, check=True)
    console.print("  [green]✓ PIP reference extracted[/green]")
    
    # Step 3: Compose with filter_complex
    console.print("\n[bold]Step 3: Compose PIP overlay[/bold]")
    composed = TEMP_DIR / "v15_composed.mp4"
    
    # Loop the PIP reference and overlay on main
    # PIP position: top-right since left speaker is main
    pip_x = OUT_W - PIP_SIZE - PIP_PADDING  # 775
    
    filter_complex = (
        # Crop and scale main video
        f"[0:v]crop={MAIN_CROP},scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black,setpts=PTS-STARTPTS[main];"
        
        # Loop and sync PIP
        f"[1:v]loop=loop=-1:size=150:start=0,setpts=PTS-STARTPTS[pip];"
        
        # Overlay
        f"[main][pip]overlay=x={pip_x}:y={PIP_Y}[out]"
    )
    
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(main_raw),
        "-i", str(pip_ref),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "copy",
        "-t", "10",
        str(composed)
    ], capture_output=True)
    
    if result.returncode != 0:
        console.print(f"[red]Error: {result.stderr.decode()[:1000]}[/red]")
        return
    
    console.print("  [green]✓ Composed with PIP[/green]")
    
    # Step 4: Copy to output
    final = OUTPUT_DIR / "clip_1_v15_test_10s.mp4"
    subprocess.run(["cp", str(composed), str(final)])
    
    console.print(Panel.fit(
        f"[bold green]✅ Test Complete![/bold green]\n"
        f"Output: [cyan]{final}[/cyan]",
        title="v15 Test"
    ))
    
    # Extract verification frames
    console.print("\n[bold]Extracting verification frames...[/bold]")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(final),
        "-vf", "fps=2,scale=540:960",
        f"{TEMP_DIR}/v15_test_%03d.jpg"
    ], capture_output=True)
    
    console.print("  [green]✓ Frames extracted[/green]")

if __name__ == "__main__":
    build_test_clip()

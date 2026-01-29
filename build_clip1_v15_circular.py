#!/usr/bin/env python3
"""
Clip Builder v15 - Video-Based PIP with Circular Mask
Fixed:
1. Circular mask with face centered
2. Better face crop to ensure centered
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
PIP_SIZE = 220  # Slightly smaller for cleaner look
PIP_PADDING = 30
PIP_Y = 80

# Crop coordinates (verified)
MAIN_CROP = "1350:2160:1245:0"

# Face-centered crops (adjusted to center face in frame)
# LEFT speaker (Dr. Abud): face is around x=1400, y=400 in source
# RIGHT speaker (Host): face is around x=1600, y=400 in source
LEFT_FACE_CROP = "800:800:1100:200"   # Adjusted for face center
RIGHT_FACE_CROP = "800:800:1300:200"  # Adjusted for face center

def build_circular_test():
    """Build 10-second test with circular PIP"""
    console.print(Panel.fit(
        "[bold cyan]🔬 v15 Circular PIP Test (10s)[/bold cyan]\n"
        "• Circular mask (geq filter)\n"
        "• Face-centered crop\n"
        "• Cleaner bubble look",
        title="Circular Test"
    ))
    
    START, END = 3940.0, 3950.0
    HOST_REF_START = 3981.0
    
    # Step 1: Extract main video
    console.print("\n[bold]Step 1: Extract main video[/bold]")
    main_raw = TEMP_DIR / "v15c_main.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(START), "-i", str(VIDEO_PATH),
        "-t", "10", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-c:a", "aac", str(main_raw)
    ], capture_output=True, check=True)
    console.print("  [green]✓ Main extracted[/green]")
    
    # Step 2: Extract host reference with face-centered crop
    console.print("\n[bold]Step 2: Extract host PIP (face-centered)[/bold]")
    pip_ref = TEMP_DIR / "v15c_pip.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(HOST_REF_START), "-i", str(VIDEO_PATH),
        "-t", "5",
        "-vf", f"crop={RIGHT_FACE_CROP},scale={PIP_SIZE}:{PIP_SIZE}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-an", str(pip_ref)
    ], capture_output=True, check=True)
    console.print("  [green]✓ PIP extracted (face-centered)[/green]")
    
    # Step 3: Compose with CIRCULAR mask
    console.print("\n[bold]Step 3: Compose with circular mask[/bold]")
    composed = TEMP_DIR / "v15c_composed.mp4"
    
    pip_x = OUT_W - PIP_SIZE - PIP_PADDING
    
    # Circular mask using geq filter
    # The geq formula creates a circle by checking if pixel is within radius from center
    # r = PIP_SIZE/2 = 110, center = (110, 110)
    # if distance from center > radius, alpha = 0 (transparent)
    r = PIP_SIZE // 2
    
    filter_complex = (
        # Crop and scale main video
        f"[0:v]crop={MAIN_CROP},scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black,setpts=PTS-STARTPTS[main];"
        
        # Loop PIP and apply circular mask
        f"[1:v]loop=loop=-1:size=150:start=0,setpts=PTS-STARTPTS,"
        f"format=yuva444p,"
        f"geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':"
        f"a='if(gt(sqrt(pow(X-{r},2)+pow(Y-{r},2)),{r}),0,255)'[pip];"
        
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
    
    console.print("  [green]✓ Circular PIP composed[/green]")
    
    # Copy to output
    final = OUTPUT_DIR / "clip_1_v15_circular_test.mp4"
    subprocess.run(["cp", str(composed), str(final)])
    
    console.print(Panel.fit(
        f"[bold green]✅ Circular Test Complete![/bold green]\n"
        f"Output: [cyan]{final}[/cyan]",
        title="Success"
    ))
    
    # Extract verification frames
    console.print("\n[bold]Extracting verification frames...[/bold]")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(final),
        "-vf", "fps=2,scale=540:960",
        f"{TEMP_DIR}/v15c_test_%03d.jpg"
    ], capture_output=True)
    console.print("  [green]✓ Frames extracted[/green]")

if __name__ == "__main__":
    build_circular_test()

#!/usr/bin/env python3
"""
DEBUG v16 - Minimal Highlight Test
Renders just 5 seconds with 1 line of highlights to verify drawtext works.
"""
import subprocess
from pathlib import Path

VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# Debug Timing (matches clip start)
START_TIME = 3938.0
DURATION = 5.0

# Mock Word Data (Matches transcript roughly)
# "I haven't seen that"
# Start times relative to 0.0 (3938.0)
WORDS = [
    {'text': 'I', 'start': 0.58, 'end': 0.82, 'x': 100, 'y': 1580},
    {'text': "HAVEN'T", 'start': 0.82, 'end': 0.98, 'x': 200, 'y': 1580},
    {'text': 'SEEN', 'start': 0.98, 'end': 1.08, 'x': 500, 'y': 1580},
    {'text': 'THAT', 'start': 1.08, 'end': 1.24, 'x': 700, 'y': 1580},
]

def debug_render():
    print("Extracting base 5s clip...")
    base = TEMP_DIR / "debug_base.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(START_TIME), "-i", str(VIDEO_PATH),
        "-t", str(DURATION), "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "copy", str(base)
    ], check=True)

    print("Generating filters...")
    filters = []
    
    # Simple Drawtext Test
    # 1. Static white text
    # 2. Dynamic red box
    
    for w in WORDS:
        # White Text
        filters.append(
            f"drawtext=text='{w['text']}':"
            f"fontfile='{FONT_PATH}':fontsize=68:fontcolor=white:"
            f"borderw=3:bordercolor=black:"
            f"x={w['x']}:y={w['y']}"
        )
        
        # Red Box Highlight
        filters.append(
            f"drawtext=text='{w['text']}':"
            f"fontfile='{FONT_PATH}':fontsize=68:fontcolor=white:"
            f"borderw=3:bordercolor=black:"
            f"box=1:boxcolor=0xE31C3D@0.9:boxborderw=10:"
            f"x={w['x']}:y={w['y']}:"
            f"enable='between(t,{w['start']},{w['end']})'"
        )
    
    filter_str = ",".join(filters)
    
    print("Rendering...")
    out = OUTPUT_DIR / "debug_v16_test.mp4"
    res = subprocess.run([
        "ffmpeg", "-y", "-i", str(base),
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "copy", str(out)
    ], capture_output=True)
    
    if res.returncode != 0:
        print("FFmpeg Error:")
        print(res.stderr.decode())
    else:
        print(f"Success! Output: {out}")
        # Extract frame at 0.7s (should show I with red box)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(out),
            "-ss", "00:00:00.700", "-vframes", "1",
            str(TEMP_DIR / "debug_frame.jpg")
        ])

if __name__ == "__main__":
    debug_render()

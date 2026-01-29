#!/usr/bin/env python3
import subprocess
from pathlib import Path

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

def test_syntax(name, enable_expr):
    print(f"Testing syntax: {name}")
    print(f"Expression: {enable_expr}")
    
    # Simple drawtext
    vf = (
        f"drawtext=text='TEST':fontfile='{FONT_PATH}':fontsize=100:fontcolor=white:"
        f"x=100:y=100:{enable_expr}"
    )
    
    out = TEMP_DIR / f"test_{name}.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=5",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "ultrafast", str(out)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Success")
    else:
        print(f"❌ Failed: {res.stderr.splitlines()[-2:]}")

if __name__ == "__main__":
    # Test 1: Quotes + commas (Failed in short_build)
    test_syntax("quotes_commas", "enable='between(t,1,4)'")
    
    # Test 2: Quotes + escaped commas (Used in v16 fix)
    test_syntax("quotes_escaped", "enable='between(t\,1\,4)'")
    
    # Test 3: No quotes + escaped commas (Proposed fix)
    test_syntax("noquotes_escaped", "enable=between(t\,1\,4)")

#!/usr/bin/env python3
"""
Test FFmpeg Filter Script Syntax
Checks how to escape commas/quotes in a filter script file.
"""
import subprocess
from pathlib import Path

TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

def test_script_syntax(name, filter_content):
    print(f"Testing syntax: {name}")
    print(f"Content: {filter_content}")
    
    script_path = TEMP_DIR / f"test_filter_{name}.txt"
    with open(script_path, "w") as f:
        f.write(filter_content)
    
    out = TEMP_DIR / f"test_script_{name}.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=5",
        "-filter_script:v", str(script_path),
        "-c:v", "libx264", "-preset", "ultrafast", str(out)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Success")
    else:
        print(f"❌ Failed: {res.stderr.splitlines()[-2:]}")

if __name__ == "__main__":
    # Case 1: Quotes + commas (Standard)
    filter1 = f"drawtext=text='CASE1':fontfile='{FONT_PATH}':fontsize=100:fontcolor=white:x=100:y=100:enable='between(t,1,4)'"
    test_script_syntax("quotes_commas", filter1)
    
    # Case 2: Quotes + escaped commas (CLI style)
    filter2 = f"drawtext=text='CASE2':fontfile='{FONT_PATH}':fontsize=100:fontcolor=white:x=100:y=300:enable='between(t\,1\,4)'"
    test_script_syntax("quotes_escaped", filter2)
    
    # Case 3: No quotes + escaped commas
    # Note: colons in fontfile path need escaping too? Usually quotes handle that.
    filter3 = f"drawtext=text='CASE3':fontfile='{FONT_PATH}':fontsize=100:fontcolor=white:x=100:y=500:enable=between(t\,1\,4)"
    test_script_syntax("noquotes_escaped", filter3)

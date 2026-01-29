#!/usr/bin/env python3
"""
v16 SHORT Debug Build
Renders only 10s of the full clip to test if text appears.
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Tuple
from rich.console import Console
from rich.panel import Panel

console = Console()

# Paths (Same as v16)
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TRANSCRIPT_PATH = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

OUT_W, OUT_H = 1080, 1920

# Style
FONT_SIZE = 68
CAPTION_Y_LINE1 = 1580
CAPTION_Y_LINE2 = 1665
HIGHLIGHT_COLOR = "0xE31C3D"
TEXT_COLOR = "white"
OUTLINE_COLOR = "black"
BOX_PADDING = 12
WORDS_PER_LINE = 4

WORD_FIXES = {"lair": "Larry", "Lair": "Larry", "viral": "vial"}

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_words(transcript: Dict, start: float, end: float) -> List[Dict]:
    words = []
    for seg in transcript['segments']:
        if 'words' not in seg: continue
        for w in seg['words']:
            # Relaxed timing check for partial overlaps
            if w['end'] > start and w['start'] < end:
                text = fix_word(w['text'].strip())
                if not text: continue
                words.append({
                    'text': text.upper(),
                    'start': max(0, w['start'] - start),
                    'end': w['end'] - start,
                })
    return words

def group_words_into_lines(words: List[Dict], words_per_line: int = 4) -> List[List[Dict]]:
    lines = []
    for i in range(0, len(words), words_per_line):
        lines.append(words[i:i + words_per_line])
    return lines

def calculate_line_positions(line: List[Dict], y: int, font_size: int = 68) -> List[Dict]:
    char_width = font_size * 0.55
    spacing = font_size * 0.4
    total_width = sum(len(w['text']) * char_width for w in line)
    total_width += spacing * (len(line) - 1)
    start_x = (OUT_W - total_width) / 2
    
    positioned = []
    x = start_x
    for word in line:
        word_width = len(word['text']) * char_width
        positioned.append({
            **word,
            'x': int(x),
            'y': y,
        })
        x += word_width + spacing
    return positioned

def escape_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return text

def generate_highlight_filters(lines: List[List[Dict]]) -> str:
    filters = []
    for line_idx, line in enumerate(lines):
        line_start = line[0]['start']
        line_end = line[-1]['end']
        y = CAPTION_Y_LINE1 if line_idx % 2 == 0 else CAPTION_Y_LINE2
        
        positioned = calculate_line_positions(line, y)
        
        for word in positioned:
            text = escape_text(word['text'])
            # 1. Base White
            filters.append(
                f"drawtext=text='{text}':fontfile='{FONT_PATH}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:"
                f"borderw=3:bordercolor={OUTLINE_COLOR}:x={word['x']}:y={word['y']}:"
                f"enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )
            # 2. Highlight Red
            filters.append(
                f"drawtext=text='{text}':fontfile='{FONT_PATH}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:"
                f"borderw=3:bordercolor={OUTLINE_COLOR}:"
                f"box=1:boxcolor={HIGHLIGHT_COLOR}@0.9:boxborderw={BOX_PADDING}:"
                f"x={word['x']}:y={word['y']}:"
                f"enable='between(t,{word['start']:.3f},{word['end']:.3f})'"
            )
    return ",".join(filters)

def build_test():
    START = 3938.0
    END = 3948.0  # 10s only
    
    console.print(f"[bold]Short Build Test ({START}-{END})[/bold]")
    
    # Extract Base
    base_clip = TEMP_DIR / "clip1_v16_short_base.mp4"
    if not base_clip.exists(): # Reuse if exists to save time? No, overwrite to be safe
        console.print("Extracting base...")
        # Use simple ffmpeg command
        # crop logic from v16:
        # crop_w = min(int((h * 9 / 16) * 1.25), w) -> 2160 * 9/16 * 1.25 = 1518
        # crop=1518:2160:1161:0 scale=1080:1920
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(START), "-i", str(VIDEO_PATH),
            "-t", "10",
            "-vf", "crop=1518:2160:1161:0,scale=1080:1920,pad=1080:1920:0:0:black",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", str(base_clip)
        ], check=True)
    
    # Transcript
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    lines = group_words_into_lines(words)
    f_str = generate_highlight_filters(lines)
    
    console.print(f"Generated {len(f_str.split(','))} filters")
    
    final_path = OUTPUT_DIR / "clip_1_v16_short.mp4"
    console.print("Rendering...")
    res = subprocess.run([
        "ffmpeg", "-y", "-i", str(base_clip),
        "-vf", f_str,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "copy", str(final_path)
    ], capture_output=True)
    
    if res.returncode != 0:
        console.print("[red]Render failed![/red]")
        console.print(res.stderr.decode()[-2000:])
    else:
        console.print("Success!")
        # Verify frame at 2s
        subprocess.run([
            "ffmpeg", "-y", "-i", str(final_path), 
            "-ss", "2", "-vframes", "1", 
            str(TEMP_DIR / "v16_short_verify.jpg")
        ])

if __name__ == "__main__":
    build_test()

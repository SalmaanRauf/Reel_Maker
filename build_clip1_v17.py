#!/usr/bin/env python3
"""
Clip Builder v17 - Red Box Highlight via Thick Border
Uses ASS 3c (border color) override with very thick border to create
a red box effect around the highlighted word.

Strategy:
- Base layer: white text with black outline
- Highlight layer: white text with RED thick border (creates box effect)
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict
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

# Style
FONT_SIZE = 72
WORDS_PER_LINE = 4

WORD_FIXES = {"lair": "Larry", "Lair": "Larry", "viral": "vial", "larry": "Larry"}

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_words(transcript: Dict, start: float, end: float) -> List[Dict]:
    words = []
    duration = end - start
    for seg in transcript['segments']:
        if 'words' not in seg:
            continue
        for w in seg['words']:
            if w['end'] > start and w['start'] < end:
                text = fix_word(w['text'].strip())
                if not text:
                    continue
                rel_start = max(0.0, round(w['start'] - start, 3))
                rel_end = min(duration, round(w['end'] - start, 3))
                if rel_end > rel_start:
                    words.append({
                        'text': text.upper(),
                        'start': rel_start,
                        'end': rel_end,
                    })
    return words

def group_words_into_lines(words: List[Dict], words_per_line: int = 4) -> List[List[Dict]]:
    lines = []
    for i in range(0, len(words), words_per_line):
        lines.append(words[i:i + words_per_line])
    return lines

def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_ass_subtitles(lines: List[List[Dict]], output_path: Path, duration: float):
    """
    Generate ASS with inline styling for word-by-word highlight.
    Uses \\3c (border color) + \\bord (thick border) to create box effect.
    Also adds persistent top title for the whole video.
    """
    
    # Colors (ASS &HAABBGGRR)
    white = "&H00FFFFFF"
    black = "&H00000000"
    red = "&H003D1CE3"  # Red in BGR
    
    # Top title text - hooking and interesting (mentions both hosts)
    title_line1 = "Santa Cruz & Dr. Bakri Explain"
    title_line2 = "How BPC-157 Heals Torn Tendons"
    
    ass_content = f"""[Script Info]
Title: Karaoke Box Highlight with Title
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,{FONT_SIZE},{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,6,6,2,10,10,340,1
Style: TopTitle,Arial,42,{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,4,2,8,20,20,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    
    # Add top title (persists for entire video)
    end_time = format_ass_time(duration)
    events.append(f"Dialogue: 0,0:00:00.00,{end_time},TopTitle,,0,0,0,,{title_line1}\\N{title_line2}")
    
    for line in lines:
        if not line:
            continue
        
        line_start = line[0]['start']
        line_end = line[-1]['end']
        
        # Create one dialogue event per line with inline styling for each word
        # Words get \\3c&H003D1CE3& (red border) + \\bord20 during their highlight time
        
        for word_idx, current_word in enumerate(line):
            word_start = format_ass_time(current_word['start'])
            word_end = format_ass_time(current_word['end'])
            
            # Build line text with current word highlighted
            text_parts = []
            for i, w in enumerate(line):
                if i == word_idx:
                    # Highlighted word: red thick border with black shadow for outline
                    text_parts.append(f"{{\\3c{red}\\bord14\\shad6}}{w['text']}{{\\3c{black}\\bord6\\shad6}}")
                else:
                    # Normal word
                    text_parts.append(w['text'])
            
            line_text = " ".join(text_parts)
            events.append(f"Dialogue: 0,{word_start},{word_end},Default,,0,0,0,,{line_text}")
    
    ass_content += "\n".join(events)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

def extract_base_video(start: float, end: float, output: Path) -> Path:
    console.print("  → Extracting base video...")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v17_raw.mp4"
    
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", str(raw_path)
    ], capture_output=True, check=True)
    
    res = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)
    ], capture_output=True, text=True)
    w, h = map(int, res.stdout.strip().split(','))
    
    crop_w = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output)
    ], capture_output=True, check=True)
    
    console.print("  ✓ Extracted")
    return output

def burn_subtitles(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    console.print("  → Burning karaoke captions...")
    
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    
    if result.returncode != 0:
        console.print(f"[red]Error: {result.stderr.decode()[:500]}[/red]")
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print("  ✓ Captions burned")
    
    return output_path

def build_clip1_v17():
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v17 (Border Box)[/bold magenta]\n"
        "• Thick red border creates box effect\n"
        "• Inline ASS styling per word\n"
        "• Precise Whisper timing",
        title="Karaoke Captions v17"
    ))
    
    START, END = 3938.0, 3984.0
    
    console.print("\n[bold]Step 1: Load transcript[/bold]")
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    console.print(f"  ✓ Found {len(words)} words")
    
    console.print("\n[bold]Step 2: Group into lines[/bold]")
    lines = group_words_into_lines(words, WORDS_PER_LINE)
    console.print(f"  ✓ Created {len(lines)} lines")
    
    console.print("\n[bold]Step 3: Generate ASS subtitles[/bold]")
    ass_path = TEMP_DIR / "clip1_v17_borderbox.ass"
    duration = END - START
    generate_ass_subtitles(lines, ass_path, duration)
    console.print(f"  ✓ Generated {ass_path}")
    
    console.print("\n[bold]Step 4: Extract base video[/bold]")
    base_clip = TEMP_DIR / "clip1_v17_base.mp4"
    extract_base_video(START, END, base_clip)
    
    console.print("\n[bold]Step 5: Burn subtitles[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v17.mp4"
    burn_subtitles(base_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))
    
    return final_path

if __name__ == "__main__":
    build_clip1_v17()

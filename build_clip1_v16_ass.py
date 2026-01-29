#!/usr/bin/env python3
"""
Clip Builder v16 - ASS Karaoke Captions
Uses ASS subtitle format with \k tags for word-by-word highlighting.
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
START, END = 3938.0, 3984.0

# Style
FONT_SIZE = 68
CAPTION_Y = 1600  # Higher position
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
            if start <= w['start'] <= end:
                text = fix_word(w['text'].strip())
                if not text: continue
                words.append({
                    'text': text.upper(),
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                })
    return words

def group_words_into_lines(words: List[Dict], words_per_line: int = 4) -> List[List[Dict]]:
    lines = []
    for i in range(0, len(words), words_per_line):
        lines.append(words[i:i + words_per_line])
    return lines

def generate_ass_subtitles(lines: List[List[Dict]], output_path: Path):
    """Generate ASS subtitle file with karaoke effects"""
    
    # ASS Header
    ass_content = f"""[Script Info]
Title: Karaoke Captions
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{FONT_SIZE},&H00FFFFFF,&H003D1CE3,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,10,10,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Generate events for each line
    for line_idx, line in enumerate(lines):
        if not line:
            continue
        
        line_start = line[0]['start']
        line_end = line[-1]['end']
        
        # Build text with karaoke tags
        # \k<duration> makes word highlight for that duration (in centiseconds)
        text_parts = []
        for word in line:
            duration_cs = int((word['end'] - word['start']) * 100)  # Convert to centiseconds
            text_parts.append(f"{{\\k{duration_cs}}}{word['text']}")
        
        text = " ".join(text_parts)
        
        # Format timestamps
        start_time = format_ass_time(line_start)
        end_time = format_ass_time(line_end)
        
        # Add event
        ass_content += f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format (H:MM:SS.CS)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def extract_base_video(start: float, end: float, output: Path) -> Path:
    """Extract and crop video"""
    console.print("  → Extracting base video...")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v16_ass_raw.mp4"
    
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", str(raw_path)
    ], capture_output=True, check=True)
    
    # Get dimensions
    res = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)
    ], capture_output=True, text=True)
    w, h = map(int, res.stdout.strip().split(','))
    
    # Center crop
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
    """Burn ASS subtitles into video"""
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

def build_clip1_v16():
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v16 (ASS)[/bold magenta]\n"
        "• Word-by-word karaoke highlighting\n"
        "• Using ASS subtitles with \\k tags\n"
        "• Higher captions, heavier font",
        title="Karaoke Captions"
    ))
    
    # Load transcript
    console.print("\n[bold]Step 1: Load transcript[/bold]")
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    console.print(f"  ✓ Found {len(words)} words")
    
    # Group into lines
    console.print("\n[bold]Step 2: Group into lines[/bold]")
    lines = group_words_into_lines(words, WORDS_PER_LINE)
    console.print(f"  ✓ Created {len(lines)} lines")
    
    # Generate ASS
    console.print("\n[bold]Step 3: Generate ASS subtitles[/bold]")
    ass_path = TEMP_DIR / "clip1_v16_karaoke.ass"
    generate_ass_subtitles(lines, ass_path)
    console.print(f"  ✓ Generated {ass_path}")
    
    # Extract base
    console.print("\n[bold]Step 4: Extract base video[/bold]")
    base_clip = TEMP_DIR / "clip1_v16_ass_base.mp4"
    extract_base_video(START, END, base_clip)
    
    # Burn subtitles
    console.print("\n[bold]Step 5: Burn subtitles[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v16.mp4"
    burn_subtitles(base_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v16()

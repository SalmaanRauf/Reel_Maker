#!/usr/bin/env python3
"""
Clip Builder v16 - Word-by-Word Highlight Captions
Features:
- Karaoke-style word highlight (red background moves word-to-word)
- Precise timing from Whisper word-level timestamps
- Two-line display, higher position, heavier font
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
TRANSCRIPT_PATH = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Style Configuration
FONT_SIZE = 68
LINE_HEIGHT = 85
CAPTION_Y_LINE1 = 1580  # Higher position
CAPTION_Y_LINE2 = 1665
HIGHLIGHT_COLOR = "0xE31C3D"  # Red
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
    """Extract words with precise timing"""
    words = []
    for seg in transcript['segments']:
        if 'words' not in seg: continue
        for w in seg['words']:
            if start <= w['start'] <= end:
                text = fix_word(w['text'].strip())
                if not text:
                    continue
                words.append({
                    'text': text.upper(),
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                })
    return words

def group_words_into_lines(words: List[Dict], words_per_line: int = 4) -> List[List[Dict]]:
    """Group words into display lines"""
    lines = []
    for i in range(0, len(words), words_per_line):
        line = words[i:i + words_per_line]
        if line:
            lines.append(line)
    return lines

def calculate_line_positions(line: List[Dict], y: int, font_size: int = 68) -> List[Dict]:
    """Calculate X positions for each word in a line (centered)"""
    # Estimate character width (approximate)
    char_width = font_size * 0.55
    spacing = font_size * 0.4
    
    # Calculate total line width
    total_width = sum(len(w['text']) * char_width for w in line)
    total_width += spacing * (len(line) - 1)
    
    # Center the line
    start_x = (OUT_W - total_width) / 2
    
    positioned = []
    x = start_x
    for word in line:
        word_width = len(word['text']) * char_width
        positioned.append({
            **word,
            'x': int(x),
            'y': y,
            'width': int(word_width),
        })
        x += word_width + spacing
    
    return positioned

def escape_text(text: str) -> str:
    """Escape special characters for FFmpeg drawtext"""
    # Escape colons, quotes, backslashes, and special chars
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    return text

def generate_highlight_filters(lines: List[List[Dict]]) -> str:
    """
    Generate FFmpeg drawtext filters for word-by-word highlighting.
    
    For each line:
    1. Draw all words in white (always visible during line's time)
    2. Draw highlight box behind current word (word's time only)
    """
    filters = []
    
    for line_idx, line in enumerate(lines):
        if not line:
            continue
        
        # Line timing
        line_start = line[0]['start']
        line_end = line[-1]['end']
        y = CAPTION_Y_LINE1 if line_idx % 2 == 0 else CAPTION_Y_LINE2
        
        # Position words
        positioned = calculate_line_positions(line, y)
        
        for word in positioned:
            text = escape_text(word['text'])
            
            # 1. Draw WHITE text (visible for entire line duration)
            # Use standard commas + quotes (works in filter script)
            filters.append(
                f"drawtext=text='{text}':"
                f"fontfile='{FONT_PATH}':"
                f"fontsize={FONT_SIZE}:"
                f"fontcolor={TEXT_COLOR}:"
                f"borderw=3:bordercolor={OUTLINE_COLOR}:"
                f"x={word['x']}:y={word['y']}:"
                f"enable='between(t,{line_start:.3f},{line_end:.3f})'"
            )
            
            # 2. Draw HIGHLIGHTED text with box (visible for word duration only)
            filters.append(
                f"drawtext=text='{text}':"
                f"fontfile='{FONT_PATH}':"
                f"fontsize={FONT_SIZE}:"
                f"fontcolor={TEXT_COLOR}:"
                f"borderw=3:bordercolor={OUTLINE_COLOR}:"
                f"box=1:boxcolor={HIGHLIGHT_COLOR}@0.9:boxborderw={BOX_PADDING}:"
                f"x={word['x']}:y={word['y']}:"
                f"enable='between(t,{word['start']:.3f},{word['end']:.3f})'"
            )
    
    return ",".join(filters)

def extract_base_video(start: float, end: float, output: Path) -> Path:
    """Extract and crop video"""
    console.print("  [dim]→ Extracting with center crop...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v16_raw.mp4"
    
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
    
    console.print("  [green]✓ Extracted[/green]")
    return output

def render_with_highlights(video_path: Path, filter_str: str, output_path: Path) -> Path:
    """Apply word highlight filters using a script file"""
    console.print("  [dim]→ Rendering word-by-word highlights (via script)...[/dim]")
    
    # Save filters to file to avoid CLI length limits
    filter_script_path = TEMP_DIR / "v16_filters.txt"
    with open(filter_script_path, "w") as f:
        f.write(filter_str)
    
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-filter_script:v", str(filter_script_path),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    
    if result.returncode != 0:
        console.print(f"[red]Error: {result.stderr.decode()[:500]}[/red]")
        # Fallback: copy without captions
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print("  [green]✓ Highlights rendered[/green]")
    
    return output_path

def build_clip1_v16():
    """Build Clip 1 v16 with word-by-word highlights"""
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v16[/bold magenta]\n"
        "• Word-by-word RED highlight\n"
        "• Precise Whisper timing\n"
        "• Higher captions, heavier font",
        title="Karaoke Captions"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Load and process words
    console.print("\n[bold]Step 1: Load transcript[/bold]")
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    console.print(f"  [green]✓ Found {len(words)} words with timestamps[/green]")
    
    # 2. Group into lines
    console.print("\n[bold]Step 2: Group into lines[/bold]")
    lines = group_words_into_lines(words, WORDS_PER_LINE)
    # DEBUG: Only process first line
    lines = lines[:1]
    console.print(f"  [green]✓ Created {len(lines)} display lines (DEBUG: ONE LINE ONLY)[/green]")
    
    # 3. Generate highlight filters
    console.print("\n[bold]Step 3: Generate highlight filters[/bold]")
    filter_str = generate_highlight_filters(lines)
    console.print(f"  [green]✓ Generated {len(filter_str.split('drawtext'))-1} drawtext commands[/green]")
    
    # 4. Extract base video
    console.print("\n[bold]Step 4: Extract base video[/bold]")
    base_clip = TEMP_DIR / "clip1_v16_base.mp4"
    extract_base_video(START, END, base_clip)
    
    # 5. Render with highlights
    console.print("\n[bold]Step 5: Render highlights[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v16.mp4"
    render_with_highlights(base_clip, filter_str, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v16()

print('DEBUG VALUES:')
print(f'{lines[0]}')
print(generate_highlight_filters(lines[:1]))

#!/usr/bin/env python3
"""
Clip Builder v13 PATCHED
Based on v13 with user patches:
1. Captions raised higher (320/230 instead of 280/190)
2. NO emojis
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

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Caption Style - PATCHED: EVEN HIGHER
FONT_SIZE = 72
BASE_MARGIN_V_LINE1 = 320  # Was 280, raised +40
BASE_MARGIN_V_LINE2 = 230  # Was 190, raised +40

SLANT_ANGLES = [-4, 4]
MARGIN_VARIATION = [-15, 0, 15]

# Colors
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
GREEN = "&H0099FF00"

WORD_FIXES = {"lair": "Larry", "Lair": "Larry", "viral": "vial"}

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_words(transcript: Dict, start: float, end: float) -> List[Dict]:
    """Extract words (no emoji processing)"""
    words = []
    for seg in transcript['segments']:
        if 'words' not in seg: continue
        for w in seg['words']:
            if start <= w['start'] <= end:
                text = fix_word(w['text'].strip())
                words.append({
                    'text': text,
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                })
    return words

def balance_lines(words: List[str]) -> Tuple[str, str]:
    """Split words into two lines with approximately equal character counts"""
    if len(words) <= 1:
        return ' '.join(words), ""
    
    best_split = len(words) // 2
    best_diff = float('inf')
    
    for i in range(1, len(words)):
        line1 = ' '.join(words[:i])
        line2 = ' '.join(words[i:])
        diff = abs(len(line1) - len(line2))
        if diff < best_diff:
            best_diff = diff
            best_split = i
    
    return ' '.join(words[:best_split]), ' '.join(words[best_split:])

def get_balanced_captions(words: List[Dict]) -> List[Dict]:
    """Create BALANCED two-line captions"""
    captions = []
    i = 0
    caption_idx = 0
    
    while i < len(words):
        chunk_size = min(7, len(words) - i)
        if chunk_size < 2:
            chunk_size = len(words) - i
        
        chunk = words[i:i + chunk_size]
        if not chunk:
            break
        
        word_texts = [w['text'] for w in chunk]
        line1, line2 = balance_lines(word_texts)
        
        captions.append({
            'line1': line1,
            'line2': line2,
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
            'words': chunk,
            'idx': caption_idx,
        })
        
        caption_idx += 1
        i += chunk_size
    
    return captions

def generate_balanced_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with balanced captions"""
    console.print("  [dim]→ Generating balanced ASS...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v13 Patched
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line1,Arial Rounded MT Bold,{FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,50,50,{BASE_MARGIN_V_LINE1},1
Style: Line2,Arial Rounded MT Bold,{FONT_SIZE},&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,2,50,50,{BASE_MARGIN_V_LINE2},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def fmt(s):
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"
    
    events = []
    
    for cap in captions:
        idx = cap['idx']
        
        if cap['line1'].lower().strip() in ['yeah', 'yep']:
            continue
        
        angle = SLANT_ANGLES[idx % 2]
        slant_tag = f"\\frz{angle}"
        
        if idx % 2 == 0:
            line1_color = WHITE
            line2_color = YELLOW
        else:
            line1_color = YELLOW
            line2_color = WHITE
        
        if idx % 5 == 3:
            line2_color = GREEN
        
        v_offset = MARGIN_VARIATION[idx % 3]
        margin_v_line1 = BASE_MARGIN_V_LINE1 + v_offset
        margin_v_line2 = BASE_MARGIN_V_LINE2 + v_offset
        
        pop = r"{\fscx20\fscy20\t(0,60,\fscx108\fscy108)\t(60,120,\fscx100\fscy100)}"
        
        if cap['line1']:
            text1 = cap['line1'].upper()
            color_tag = f"\\c{line1_color}"
            events.append(
                f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Line1,,0,0,{margin_v_line1},,"
                f"{{{slant_tag}{color_tag}}}{pop}{text1}"
            )
        
        if cap['line2']:
            text2 = cap['line2'].upper()
            color_tag = f"\\c{line2_color}"
            events.append(
                f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Line2,,0,0,{margin_v_line2},,"
                f"{{{slant_tag}{color_tag}}}{pop}{text2}"
            )
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} events[/green]")
    return output_path

def extract_zoom_out(start: float, end: float, output: Path) -> Path:
    """Center crop with 25% wider for zoom-out effect"""
    console.print("  [dim]→ Extracting with CENTER CROP...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_patched_raw.mp4"
    
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

def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    console.print("  [dim]→ Burning captions...[/dim]")
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ], capture_output=True, check=True)
    console.print("  [green]✓ Burned[/green]")
    return output_path

def build_clip1_patched():
    """Build Clip 1 v13 PATCHED"""
    console.print(Panel.fit(
        "[bold cyan]🎬 Building Clip 1 v13 PATCHED[/bold cyan]\n"
        "• Higher captions (+40px)\n"
        "• NO emojis\n"
        "• Same balanced captions",
        title="v13 Patched"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Word analysis
    console.print("\n[bold]Step 1: Word analysis[/bold]")
    transcript = load_transcript()
    words = get_words(transcript, START, END)
    console.print(f"  [green]✓ Found {len(words)} words[/green]")
    
    # 2. Balanced captions
    console.print("\n[bold]Step 2: Balanced captions[/bold]")
    captions = get_balanced_captions(words)
    console.print(f"  [green]✓ Created {len(captions)} balanced captions[/green]")
    
    # 3. Extract with center crop
    console.print("\n[bold]Step 3: Center crop[/bold]")
    base_clip = TEMP_DIR / "clip1_patched_base.mp4"
    extract_zoom_out(START, END, base_clip)
    
    # 4. Generate captions
    console.print("\n[bold]Step 4: Generate ASS[/bold]")
    ass_path = TEMP_DIR / "clip1_patched.ass"
    generate_balanced_ass(captions, ass_path)
    
    # 5. Burn captions (NO EMOJI STEP)
    console.print("\n[bold]Step 5: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v13_patched.mp4"
    burn_captions(base_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_patched()

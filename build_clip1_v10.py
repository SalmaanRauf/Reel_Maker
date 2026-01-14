#!/usr/bin/env python3
"""
Clip Builder v10 - Premium Reference-Matched Style
Based on deep frame analysis of Captionsref.MP4:
- Alternating slant (-5° / +5° rotation)
- Color rotation (WHITE/YELLOW/GREEN)
- Emojis appear ABOVE captions
- Vertical position variation
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
EMOJI_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/assets/emojis")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Style Configuration
SLANT_ANGLES = [-4, 4]  # Alternate rotation
BASE_MARGIN_V = 140
MARGIN_VARIATION = [-25, 0, 25]  # Vertical variation

# Colors (ASS BGR format)
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"  # Yellow in BGR
GREEN = "&H0099FF00"   # Light green in BGR

# Contextual Emoji Triggers (appear ABOVE captions)
EMOJI_TRIGGERS = {
    "purple": {"file": "purple.png", "size": 180},
    "surgery": {"file": "surgery.png", "size": 160},
    "four weeks": {"file": "weeks.png", "size": 220},
    "healed": {"file": "healed.png", "size": 200},
    "friend": {"file": "friend.png", "size": 160},
    "larry": {"file": "larry.png", "size": 180},
    "tendon": {"file": "tendon.png", "size": 160},
    "injection": {"file": "surgery.png", "size": 160},
}

WORD_FIXES = {
    "lair": "Larry",
    "Lair": "Larry",
    "viral": "vial",
}

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_semantic_captions(transcript: Dict, start: float, end: float) -> List[Dict]:
    """Create semantic two-line captions"""
    all_words = []
    for seg in transcript['segments']:
        if 'words' not in seg: continue
        for w in seg['words']:
            if start <= w['start'] <= end:
                all_words.append({
                    'text': fix_word(w['text'].strip()),
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                })
    
    captions = []
    i = 0
    caption_idx = 0
    
    while i < len(all_words):
        chunk_size = min(6, len(all_words) - i)
        if chunk_size < 2:
            chunk_size = len(all_words) - i
        
        chunk = all_words[i:i + chunk_size]
        if not chunk:
            break
            
        # Split into two lines
        split_point = max(2, len(chunk) // 2 + 1)
        line1_words = chunk[:split_point]
        line2_words = chunk[split_point:]
        
        line1 = ' '.join(w['text'] for w in line1_words)
        line2 = ' '.join(w['text'] for w in line2_words) if line2_words else ""
        
        # Check for emoji triggers
        full_text = (line1 + " " + line2).lower()
        emoji = None
        for trigger, config in EMOJI_TRIGGERS.items():
            if trigger in full_text:
                emoji = config
                break
        
        captions.append({
            'line1': line1,
            'line2': line2,
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
            'emoji': emoji,
            'idx': caption_idx,
        })
        
        caption_idx += 1
        i += chunk_size
    
    return captions

def generate_premium_ass(captions: List[Dict], output_path: Path) -> Path:
    """
    Generate ASS with premium styling:
    - Alternating slant
    - Color rotation
    - Vertical variation
    """
    console.print("  [dim]→ Generating premium ASS with slant/color rotation...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v10 Premium
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line1,Arial Rounded MT Bold,60,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,170,1
Style: Line2,Arial Rounded MT Bold,60,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,100,1
Style: Final,Arial Rounded MT Bold,70,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,5,50,50,50,1

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
        
        # Skip filler
        if cap['line1'].lower().strip() in ['yeah', 'yep']:
            continue
        
        # 1. SLANT: Alternate rotation
        angle = SLANT_ANGLES[idx % 2]
        slant_tag = f"\\frz{angle}"
        
        # 2. COLOR: Alternate which line gets highlight
        if idx % 2 == 0:
            line1_color = WHITE
            line2_color = YELLOW
        else:
            line1_color = YELLOW
            line2_color = WHITE
        
        # Occasionally use green for variety
        if idx % 5 == 3:
            line2_color = GREEN
        
        # 3. VERTICAL VARIATION
        v_offset = MARGIN_VARIATION[idx % 3]
        margin_v_line1 = 170 + v_offset
        margin_v_line2 = 100 + v_offset
        
        # Pop animation
        pop = r"{\fscx20\fscy20\t(0,60,\fscx108\fscy108)\t(60,120,\fscx100\fscy100)}"
        
        # Line 1
        if cap['line1']:
            text1 = cap['line1'].upper()
            color_tag = f"\\c{line1_color}"
            events.append(
                f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Line1,,0,0,{margin_v_line1},,"
                f"{{{slant_tag}{color_tag}}}{pop}{text1}"
            )
        
        # Line 2
        if cap['line2']:
            text2 = cap['line2'].upper()
            color_tag = f"\\c{line2_color}"
            events.append(
                f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Line2,,0,0,{margin_v_line2},,"
                f"{{{slant_tag}{color_tag}}}{pop}{text2}"
            )
    
    # Final overlay
    final_t = 44.0
    events.append(f"Dialogue: 1,{fmt(final_t)},{fmt(final_t+2.5)},Final,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2-50})}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 1,{fmt(final_t)},{fmt(final_t+2.5)},Final,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2+80})\\c&H00FFFF&}}4 WEEKS • NO SURGERY")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} styled caption events[/green]")
    return output_path

def render_emojis_above_captions(video_path: Path, captions: List[Dict], output_path: Path):
    """
    Place emojis ABOVE the caption block (centered horizontally)
    This matches the reference where emojis float between face and captions
    """
    console.print("[dim]→ Placing emojis above captions...[/dim]")
    
    overlays = []
    for cap in captions:
        if cap['emoji']:
            emoji_cfg = cap['emoji']
            img_path = EMOJI_DIR / emoji_cfg['file']
            if img_path.exists():
                # Position: Center X, above caption zone
                # Caption zone is roughly y=1650-1800
                # Emoji should be at y=1350-1500 (above captions)
                emoji_y = 1380 + (cap['idx'] % 3) * 40  # Slight variation
                emoji_x = (OUT_W - emoji_cfg['size']) // 2  # Center
                
                overlays.append({
                    'path': img_path,
                    'x': emoji_x,
                    'y': emoji_y,
                    'size': emoji_cfg['size'],
                    'start': cap['start'],
                    'end': cap['end'] + 0.3,
                })
    
    if not overlays:
        console.print("  [yellow]No emoji triggers, copying video...[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
    console.print(f"  [dim]Adding {len(overlays)} emojis above captions...[/dim]")
    
    inputs = ["-i", str(video_path)]
    filter_parts = []
    last_out = "[0:v]"
    
    for i, ov in enumerate(overlays):
        idx = i + 1
        inputs.extend(["-i", str(ov['path'])])
        
        # Scale emoji
        filter_parts.append(f"[{idx}:v]scale={ov['size']}:{ov['size']}[ov{idx}]")
        
        # Overlay above captions
        filter_parts.append(
            f"{last_out}[ov{idx}]overlay=x={ov['x']}:y={ov['y']}:"
            f"enable='between(t,{ov['start']},{ov['end']})'[v{idx}]"
        )
        last_out = f"[v{idx}]"
    
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", last_out,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        console.print(f"[red]FFmpeg error, falling back to copy[/red]")
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print(f"  [green]✓ Applied {len(overlays)} emojis[/green]")

def extract_zoom_out(start: float, end: float, output: Path) -> Path:
    """v4 zoom-out logic"""
    console.print("  [dim]→ Extracting with 20% zoom out...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v10_raw.mp4"
    
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
    console.print("  [dim]→ Burning premium captions...[/dim]")
    
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ], capture_output=True, check=True)
    
    console.print("  [green]✓ Burned[/green]")
    return output_path

def build_clip1_v10():
    """Build Clip 1 with premium reference-matched style"""
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v10[/bold magenta]\n"
        "• Alternating slant (-5°/+5°)\n"
        "• Color rotation (WHITE/YELLOW/GREEN)\n"
        "• Emojis ABOVE captions\n"
        "• Vertical variation",
        title="Premium Reference-Matched"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Captions
    console.print("\n[bold]Step 1: Semantic captions[/bold]")
    transcript = load_transcript()
    captions = get_semantic_captions(transcript, START, END)
    console.print(f"  [green]✓ Created {len(captions)} captions[/green]")
    
    # 2. Extract
    console.print("\n[bold]Step 2: Extract video[/bold]")
    base_clip = TEMP_DIR / "clip1_v10_base.mp4"
    extract_zoom_out(START, END, base_clip)
    
    # 3. Emojis above captions
    console.print("\n[bold]Step 3: Emojis above captions[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v10_emoji.mp4"
    render_emojis_above_captions(base_clip, captions, emoji_clip)
    
    # 4. Premium ASS
    console.print("\n[bold]Step 4: Premium captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v10.ass"
    generate_premium_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v10.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    # 5. Verify
    console.print("\n[bold]Step 5: Verify[/bold]")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=duration",
        "-of", "csv=p=0:s=x", str(final_path)
    ], capture_output=True, text=True)
    console.print(f"  Duration: {result.stdout.strip()}")
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v10()

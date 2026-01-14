#!/usr/bin/env python3
"""
Clip Builder v11 - Refined Premium Style
Based on user feedback:
- Shift captions UP more
- Make captions BIGGER
- Consistent emoji-caption padding
- WORD-LEVEL emoji timing (not caption-level)
- Better semantic emoji mapping
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
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

# Style Configuration - BIGGER and HIGHER
FONT_SIZE = 68  # Increased from 60
BASE_MARGIN_V_LINE1 = 220  # Higher up
BASE_MARGIN_V_LINE2 = 145  # Higher up
EMOJI_PADDING = 80  # Consistent padding above captions

SLANT_ANGLES = [-4, 4]
MARGIN_VARIATION = [-20, 0, 20]

# Colors
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
GREEN = "&H0099FF00"

# REFINED EMOJI MAPPING - Semantic and sensible
# The user specifically noted: tendon ≠ bone, vial = glass container, etc.
WORD_EMOJI_MAP = {
    # Medical / Treatment
    "purple": {"emoji": "🟣", "file": "purple.png"},      # Purple color
    "tendon": {"emoji": "💪", "file": "arm.png"},         # Muscle/tendon = arm
    "tricep": {"emoji": "💪", "file": "arm.png"},         # Tricep = arm
    "surgery": {"emoji": "👨‍⚕️", "file": "doctor.png"},     # Surgery = doctor
    "injection": {"emoji": "💉", "file": "surgery.png"},  # Injection = needle
    "needle": {"emoji": "💉", "file": "surgery.png"},     # Needle = syringe
    "vial": {"emoji": "🧪", "file": "surgery.png"},       # Vial = container (using surgery for now)
    
    # People
    "larry": {"emoji": "🦁", "file": "larry.png"},        # Larry Wheels = lion (strength)
    "friend": {"emoji": "🤝", "file": "friend.png"},      # Friend = handshake
    
    # Time / Progress
    "weeks": {"emoji": "📅", "file": "weeks.png"},        # Weeks = calendar
    "four": {"emoji": "4️⃣", "file": "weeks.png"},         # Four = number (use calendar)
    
    # Results
    "healed": {"emoji": "✨", "file": "healed.png"},      # Healed = sparkles
    "gone": {"emoji": "✨", "file": "healed.png"},        # Gone = sparkles
    "fixed": {"emoji": "✅", "file": "healed.png"},       # Fixed = check
    
    # Actions
    "lift": {"emoji": "🏋️", "file": "weight.png"},        # Lift = weightlifting
    "lifting": {"emoji": "🏋️", "file": "weight.png"},     # Lifting = weightlifting
    "weight": {"emoji": "🏋️", "file": "weight.png"},      # Weight = weightlifting
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

def get_words_with_emojis(transcript: Dict, start: float, end: float) -> List[Dict]:
    """
    Extract all words and identify which ones should trigger emojis.
    This gives us WORD-LEVEL timing for emojis!
    """
    words = []
    for seg in transcript['segments']:
        if 'words' not in seg: continue
        for w in seg['words']:
            if start <= w['start'] <= end:
                text = fix_word(w['text'].strip())
                clean = text.lower().strip('.,!?')
                
                emoji_data = None
                for trigger, data in WORD_EMOJI_MAP.items():
                    if trigger in clean:
                        emoji_data = data
                        break
                
                words.append({
                    'text': text,
                    'start': w['start'] - start,
                    'end': w['end'] - start,
                    'emoji': emoji_data,
                })
    
    return words

def get_semantic_captions(words: List[Dict]) -> List[Dict]:
    """Create semantic two-line captions from words"""
    captions = []
    i = 0
    caption_idx = 0
    
    while i < len(words):
        chunk_size = min(6, len(words) - i)
        if chunk_size < 2:
            chunk_size = len(words) - i
        
        chunk = words[i:i + chunk_size]
        if not chunk:
            break
        
        split_point = max(2, len(chunk) // 2 + 1)
        line1_words = chunk[:split_point]
        line2_words = chunk[split_point:]
        
        line1 = ' '.join(w['text'] for w in line1_words)
        line2 = ' '.join(w['text'] for w in line2_words) if line2_words else ""
        
        captions.append({
            'line1': line1,
            'line2': line2,
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
            'words': chunk,  # Keep words for word-level emoji timing
            'idx': caption_idx,
        })
        
        caption_idx += 1
        i += chunk_size
    
    return captions

def generate_premium_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with bigger font and higher position"""
    console.print("  [dim]→ Generating premium ASS (bigger, higher)...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v11 Premium
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line1,Arial Rounded MT Bold,{FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,{BASE_MARGIN_V_LINE1},1
Style: Line2,Arial Rounded MT Bold,{FONT_SIZE},&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,{BASE_MARGIN_V_LINE2},1
Style: Final,Arial Rounded MT Bold,75,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,5,50,50,50,1

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
    
    # End overlay removed per user request
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} events[/green]")
    return output_path

def render_word_level_emojis(video_path: Path, words: List[Dict], output_path: Path):
    """
    Place emojis at WORD-LEVEL timing with consistent padding above captions
    """
    console.print("[dim]→ Placing emojis with WORD-LEVEL timing...[/dim]")
    
    overlays = []
    seen_triggers = set()  # Avoid duplicate emojis for same trigger
    
    for word in words:
        if word['emoji']:
            trigger = word['text'].lower()
            # Skip if we already showed this emoji recently
            if trigger in seen_triggers:
                continue
            seen_triggers.add(trigger)
            
            img_path = EMOJI_DIR / word['emoji']['file']
            if img_path.exists():
                # Position: Center X, consistent padding above captions
                # Caption top is at roughly y = 1920 - 220 = 1700
                # Emoji should be at: 1700 - padding - emoji_size
                emoji_size = 180
                emoji_y = OUT_H - BASE_MARGIN_V_LINE1 - EMOJI_PADDING - emoji_size
                emoji_x = (OUT_W - emoji_size) // 2
                
                overlays.append({
                    'path': img_path,
                    'x': emoji_x,
                    'y': emoji_y,
                    'size': emoji_size,
                    'start': word['start'],  # WORD-LEVEL timing!
                    'end': word['end'] + 1.0,  # Linger for 1 second after word
                })
        
        # Clear seen triggers after 5 seconds to allow re-use
        # (This is a simple approach; could be more sophisticated)
    
    if not overlays:
        console.print("  [yellow]No emoji triggers, copying video...[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
    console.print(f"  [dim]Adding {len(overlays)} word-timed emojis...[/dim]")
    
    inputs = ["-i", str(video_path)]
    filter_parts = []
    last_out = "[0:v]"
    
    for i, ov in enumerate(overlays):
        idx = i + 1
        inputs.extend(["-i", str(ov['path'])])
        
        filter_parts.append(f"[{idx}:v]scale={ov['size']}:{ov['size']}[ov{idx}]")
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
        console.print(f"[red]FFmpeg error, falling back[/red]")
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print(f"  [green]✓ Applied {len(overlays)} emojis[/green]")

def extract_zoom_out(start: float, end: float, output: Path) -> Path:
    console.print("  [dim]→ Extracting with zoom out...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v11_raw.mp4"
    
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

def build_clip1_v11():
    """Build Clip 1 v11 with refined premium style"""
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v11[/bold magenta]\n"
        "• Bigger font (68pt)\n"
        "• Higher position\n"
        "• Consistent emoji padding\n"
        "• WORD-LEVEL emoji timing\n"
        "• Better semantic emojis",
        title="Refined Premium Style"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Get words with emoji triggers
    console.print("\n[bold]Step 1: Word-level analysis[/bold]")
    transcript = load_transcript()
    words = get_words_with_emojis(transcript, START, END)
    emoji_words = [w for w in words if w['emoji']]
    console.print(f"  [green]✓ Found {len(words)} words, {len(emoji_words)} with emoji triggers[/green]")
    
    # Preview emoji triggers
    console.print("  [dim]Emoji triggers:[/dim]")
    for w in emoji_words[:5]:
        console.print(f"    [{w['start']:5.2f}s] {w['text']} → {w['emoji']['emoji']}")
    
    # 2. Create captions
    console.print("\n[bold]Step 2: Semantic captions[/bold]")
    captions = get_semantic_captions(words)
    console.print(f"  [green]✓ Created {len(captions)} captions[/green]")
    
    # 3. Extract
    console.print("\n[bold]Step 3: Extract video[/bold]")
    base_clip = TEMP_DIR / "clip1_v11_base.mp4"
    extract_zoom_out(START, END, base_clip)
    
    # 4. Word-level emojis
    console.print("\n[bold]Step 4: Word-level emojis[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v11_emoji.mp4"
    render_word_level_emojis(base_clip, words, emoji_clip)
    
    # 5. Premium ASS
    console.print("\n[bold]Step 5: Premium captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v11.ass"
    generate_premium_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v11.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v11()

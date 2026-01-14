#!/usr/bin/env python3
"""
Clip Builder v12 - Dual-Face Layout + Refined Emoji System
New features:
- Dual-face: Main speaker + Host (viral influencer) in PIP
- Higher captions with balanced line lengths
- Bigger font
- No emoji overlap (0.3s gap)
- Cooldown for repeated triggers
- Strict centering
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
EMOJI_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/assets/emojis")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Caption Style - HIGHER and BIGGER with BALANCED lines
FONT_SIZE = 72  # Bigger
BASE_MARGIN_V_LINE1 = 280  # Even higher
BASE_MARGIN_V_LINE2 = 190  # Tighter spacing
EMOJI_SIZE = 220
EMOJI_Y = 1340  # Fixed Y for consistency
EMOJI_DURATION = 1.5
EMOJI_GAP = 0.3  # Gap between emojis
EMOJI_COOLDOWN = 10.0  # Seconds before same trigger can repeat

SLANT_ANGLES = [-4, 4]
MARGIN_VARIATION = [-15, 0, 15]

# Colors
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
GREEN = "&H0099FF00"

# Refined Emoji Mapping
WORD_EMOJI_MAP = {
    "purple": {"emoji": "🟣", "file": "purple.png"},
    "tendon": {"emoji": "💪", "file": "arm.png"},
    "tricep": {"emoji": "💪", "file": "arm.png"},
    "surgery": {"emoji": "🏥", "file": "doctor.png"},
    "injection": {"emoji": "💉", "file": "surgery.png"},
    "needle": {"emoji": "💉", "file": "surgery.png"},
    "vial": {"emoji": "🧪", "file": "surgery.png"},
    "larry": {"emoji": "💪", "file": "arm.png"},  # Changed from lion
    "friend": {"emoji": "🤝", "file": "friend.png"},
    "weeks": {"emoji": "📅", "file": "weeks.png"},
    "four": {"emoji": "📅", "file": "weeks.png"},
    "healed": {"emoji": "✨", "file": "healed.png"},
    "gone": {"emoji": "✨", "file": "healed.png"},
    "lift": {"emoji": "🏋️", "file": "weight.png"},
    "lifting": {"emoji": "🏋️", "file": "weight.png"},
}

WORD_FIXES = {"lair": "Larry", "Lair": "Larry", "viral": "vial"}

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_words_with_emojis(transcript: Dict, start: float, end: float) -> List[Dict]:
    """Extract words with emoji triggers"""
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

def balance_lines(words: List[str]) -> Tuple[str, str]:
    """
    Split words into two lines with approximately equal character counts
    """
    full_text = ' '.join(words)
    mid_char = len(full_text) // 2
    
    # Find split point near middle
    best_split = len(words) // 2
    best_diff = float('inf')
    
    for i in range(1, len(words)):
        line1 = ' '.join(words[:i])
        line2 = ' '.join(words[i:])
        diff = abs(len(line1) - len(line2))
        if diff < best_diff:
            best_diff = diff
            best_split = i
    
    line1 = ' '.join(words[:best_split])
    line2 = ' '.join(words[best_split:])
    return line1, line2

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

def schedule_emojis(words: List[Dict], captions: List[Dict]) -> List[Dict]:
    """
    Schedule emojis with:
    - No overlap (0.3s gap)
    - Only when caption is visible
    - Cooldown for repeats
    """
    console.print("  [dim]→ Scheduling emojis with overlap prevention...[/dim]")
    
    last_trigger_time = {}
    last_emoji_end = 0.0
    scheduled = []
    
    # Create caption time lookup
    caption_times = {}
    for cap in captions:
        for w in cap['words']:
            caption_times[id(w)] = (cap['start'], cap['end'])
    
    for word in words:
        if not word['emoji']:
            continue
        
        trigger = word['text'].lower().strip('.,!?')
        
        # Check cooldown
        if trigger in last_trigger_time:
            if word['start'] - last_trigger_time[trigger] < EMOJI_COOLDOWN:
                continue
        
        # Find caption timing for this word
        caption_start, caption_end = caption_times.get(id(word), (word['start'], word['end']))
        
        # Calculate emoji timing with gap
        emoji_start = max(word['start'], last_emoji_end + EMOJI_GAP)
        emoji_end = min(emoji_start + EMOJI_DURATION, caption_end)  # Don't extend past caption
        
        # Only add if there's enough time to show
        if emoji_end - emoji_start < 0.5:
            continue
        
        scheduled.append({
            'file': word['emoji']['file'],
            'start': emoji_start,
            'end': emoji_end,
            'trigger': trigger,
        })
        
        last_trigger_time[trigger] = word['start']
        last_emoji_end = emoji_end
    
    console.print(f"  [green]✓ Scheduled {len(scheduled)} emojis (no overlap)[/green]")
    return scheduled

def generate_balanced_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with bigger font and higher position"""
    console.print("  [dim]→ Generating balanced ASS captions...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v12 Premium
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
    
    console.print(f"  [green]✓ Generated {len(events)} balanced events[/green]")
    return output_path

def extract_dual_face(start: float, end: float, output: Path) -> Path:
    """
    Extract video with DUAL-FACE layout:
    - Main speaker (left person) fills most of frame
    - Host/interviewer (right person) in PIP corner
    
    Layout: 
    ┌─────────────────┐
    │                 │
    │  MAIN SPEAKER   │
    │  (Left person)  │ ┌────────┐
    │                 │ │  HOST  │
    │                 │ │ (PIP)  │
    └─────────────────┘ └────────┘
    """
    console.print("  [dim]→ Extracting with DUAL-FACE layout...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v12_raw.mp4"
    
    # First extract the segment
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", str(raw_path)
    ], capture_output=True, check=True)
    
    # Get source dimensions
    res = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)
    ], capture_output=True, text=True)
    src_w, src_h = map(int, res.stdout.strip().split(','))
    
    # Calculate crop regions
    # Main speaker (left half, with some padding)
    main_w = int(src_h * 9 / 16 * 1.15)  # Wider for main
    main_x = int(src_w * 0.15)  # Offset from left edge to center on left person
    
    # PIP host (right person) - smaller crop
    pip_size = 300  # Size of PIP window
    pip_crop_w = int(src_h * 0.4)  # Crop area for host
    pip_crop_x = int(src_w * 0.65)  # Right side of frame
    
    # Complex filter for dual-face
    filter_complex = (
        # Main speaker crop and scale to 9:16
        f"[0:v]crop={main_w}:{src_h}:{main_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black[main];"
        
        # PIP crop and scale with rounded corners
        f"[0:v]crop={pip_crop_w}:{pip_crop_w}:{pip_crop_x}:{int(src_h*0.1)},scale={pip_size}:{pip_size},"
        f"format=rgba,geq=lum='p(X,Y)':a='if(gt(abs(W/2-X),W/2-10)*gt(abs(H/2-Y),H/2-10),0,255)'[pip];"
        
        # Overlay PIP on main (top-right corner)
        f"[main][pip]overlay=x={OUT_W - pip_size - 30}:y=80[out]"
    )
    
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", str(output)
        ], capture_output=True, check=True)
        console.print("  [green]✓ Dual-face layout created[/green]")
    except subprocess.CalledProcessError as e:
        console.print("[yellow]Dual-face failed, falling back to single crop...[/yellow]")
        # Fallback to single crop
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_path),
            "-vf", f"crop={main_w}:{src_h}:{main_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", str(output)
        ], capture_output=True, check=True)
    
    return output

def render_scheduled_emojis(video_path: Path, scheduled: List[Dict], output_path: Path):
    """Apply scheduled emojis (strictly centered, no overlap)"""
    console.print("[dim]→ Applying centered emojis...[/dim]")
    
    if not scheduled:
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
    emoji_x = (OUT_W - EMOJI_SIZE) // 2  # Strictly centered
    
    inputs = ["-i", str(video_path)]
    filter_parts = []
    last_out = "[0:v]"
    
    for i, ov in enumerate(scheduled):
        img_path = EMOJI_DIR / ov['file']
        if not img_path.exists():
            continue
            
        idx = i + 1
        inputs.extend(["-i", str(img_path)])
        
        filter_parts.append(f"[{idx}:v]scale={EMOJI_SIZE}:{EMOJI_SIZE}[ov{idx}]")
        filter_parts.append(
            f"{last_out}[ov{idx}]overlay=x={emoji_x}:y={EMOJI_Y}:"
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
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print(f"  [green]✓ Applied {len(scheduled)} emojis[/green]")

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

def build_clip1_v12():
    """Build Clip 1 v12 with dual-face and all improvements"""
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v12[/bold magenta]\n"
        "• Dual-face layout (speaker + host PIP)\n"
        "• Balanced line lengths\n"
        "• Bigger font (72pt), higher position\n"
        "• No emoji overlap\n"
        "• Cooldown for repeats",
        title="Premium Dual-Face"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Word analysis
    console.print("\n[bold]Step 1: Word analysis[/bold]")
    transcript = load_transcript()
    words = get_words_with_emojis(transcript, START, END)
    console.print(f"  [green]✓ Found {len(words)} words[/green]")
    
    # 2. Balanced captions
    console.print("\n[bold]Step 2: Balanced captions[/bold]")
    captions = get_balanced_captions(words)
    console.print(f"  [green]✓ Created {len(captions)} balanced captions[/green]")
    
    # Preview
    for cap in captions[:3]:
        console.print(f"    L1: '{cap['line1']}' ({len(cap['line1'])} chars)")
        console.print(f"    L2: '{cap['line2']}' ({len(cap['line2'])} chars)")
    
    # 3. Schedule emojis
    console.print("\n[bold]Step 3: Schedule emojis[/bold]")
    scheduled = schedule_emojis(words, captions)
    
    # 4. Dual-face extract
    console.print("\n[bold]Step 4: Dual-face layout[/bold]")
    base_clip = TEMP_DIR / "clip1_v12_base.mp4"
    extract_dual_face(START, END, base_clip)
    
    # 5. Apply emojis
    console.print("\n[bold]Step 5: Apply emojis[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v12_emoji.mp4"
    render_scheduled_emojis(base_clip, scheduled, emoji_clip)
    
    # 6. Burn captions
    console.print("\n[bold]Step 6: Burn captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v12.ass"
    generate_balanced_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v12.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v12()

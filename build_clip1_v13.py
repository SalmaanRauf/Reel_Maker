#!/usr/bin/env python3
"""
Clip Builder v13 - Fixed Crop + Caption Improvements
REVERTED from v12's broken dual-face to v11's working crop method.
KEPT from v12: balanced captions, no-overlap emoji scheduling.
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

# Caption Style - HIGHER and BIGGER with BALANCED lines (from v12)
FONT_SIZE = 72
BASE_MARGIN_V_LINE1 = 280
BASE_MARGIN_V_LINE2 = 190
EMOJI_SIZE = 200
EMOJI_Y = 1340
EMOJI_DURATION = 1.5
EMOJI_GAP = 0.3
EMOJI_COOLDOWN = 10.0

SLANT_ANGLES = [-4, 4]
MARGIN_VARIATION = [-15, 0, 15]

# Colors
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
GREEN = "&H0099FF00"

# Refined Emoji Mapping (from v12)
WORD_EMOJI_MAP = {
    "purple": {"emoji": "🟣", "file": "purple.png"},
    "tendon": {"emoji": "💪", "file": "arm.png"},
    "tricep": {"emoji": "💪", "file": "arm.png"},
    "surgery": {"emoji": "🏥", "file": "doctor.png"},
    "injection": {"emoji": "💉", "file": "surgery.png"},
    "larry": {"emoji": "💪", "file": "arm.png"},
    "friend": {"emoji": "🤝", "file": "friend.png"},
    "weeks": {"emoji": "📅", "file": "weeks.png"},
    "four": {"emoji": "📅", "file": "weeks.png"},
    "healed": {"emoji": "✨", "file": "healed.png"},
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

def schedule_emojis(words: List[Dict], captions: List[Dict]) -> List[Dict]:
    """Schedule emojis with no overlap and cooldown"""
    console.print("  [dim]→ Scheduling emojis (no overlap)...[/dim]")
    
    last_trigger_time = {}
    last_emoji_end = 0.0
    scheduled = []
    
    caption_times = {}
    for cap in captions:
        for w in cap['words']:
            caption_times[id(w)] = (cap['start'], cap['end'])
    
    for word in words:
        if not word['emoji']:
            continue
        
        trigger = word['text'].lower().strip('.,!?')
        
        if trigger in last_trigger_time:
            if word['start'] - last_trigger_time[trigger] < EMOJI_COOLDOWN:
                continue
        
        caption_start, caption_end = caption_times.get(id(word), (word['start'], word['end']))
        
        emoji_start = max(word['start'], last_emoji_end + EMOJI_GAP)
        emoji_end = min(emoji_start + EMOJI_DURATION, caption_end)
        
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
    
    console.print(f"  [green]✓ Scheduled {len(scheduled)} emojis[/green]")
    return scheduled

def generate_balanced_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with balanced captions"""
    console.print("  [dim]→ Generating balanced ASS...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v13
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
    """
    REVERTED to v11's working crop method:
    - Center crop with 25% wider for zoom-out effect
    - NO dual-face, NO PIP
    """
    console.print("  [dim]→ Extracting with CENTER CROP (v11 method)...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v13_raw.mp4"
    
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
    
    # v11 method: 25% wider crop centered
    crop_w = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w) // 2  # CENTER
    
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output)
    ], capture_output=True, check=True)
    
    console.print("  [green]✓ Extracted (center crop)[/green]")
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

def build_clip1_v13():
    """Build Clip 1 v13 - Fixed crop with caption improvements"""
    console.print(Panel.fit(
        "[bold cyan]🎬 Building Clip 1 v13[/bold cyan]\n"
        "• REVERTED to v11 center crop (working)\n"
        "• KEPT balanced captions from v12\n"
        "• KEPT no-overlap emoji scheduling\n"
        "• 72pt font, higher position",
        title="Fixed + Improved"
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
    
    # 3. Schedule emojis
    console.print("\n[bold]Step 3: Schedule emojis[/bold]")
    scheduled = schedule_emojis(words, captions)
    
    # 4. Extract with CENTER CROP (v11 method)
    console.print("\n[bold]Step 4: Center crop (v11)[/bold]")
    base_clip = TEMP_DIR / "clip1_v13_base.mp4"
    extract_zoom_out(START, END, base_clip)
    
    # 5. Apply emojis
    console.print("\n[bold]Step 5: Apply emojis[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v13_emoji.mp4"
    render_scheduled_emojis(base_clip, scheduled, emoji_clip)
    
    # 6. Burn captions
    console.print("\n[bold]Step 6: Burn captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v13.ass"
    generate_balanced_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v13.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v13()

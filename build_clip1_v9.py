#!/usr/bin/env python3
"""
Clip Builder v9 - Reference-Matched Captions
Based on deep analysis of Captionsref.MP4:
- Two-line captions: WHITE (line 1) + YELLOW (line 2)
- Contextual emoji triggers (only emphasis keywords)
- Safe zone positioning (shoulders/corners, never center)
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

# Safe Zone Positions (Never center/face)
POSITIONS = {
    "top_left": (80, 280),
    "top_right": (780, 280),
    "top_center": (440, 180),
    "shoulder_left": (80, 950),
    "shoulder_right": (780, 950),
    "bottom_left": (80, 1400),
    "bottom_right": (780, 1400),
}

# Contextual Emoji Triggers - ONLY emphasis keywords
# Based on Clip 1 content: "Larry Wheels purple tricep" story
EMOJI_TRIGGERS = {
    "purple": {"file": "purple.png", "pos": "shoulder_right", "size": 220},
    "surgery": {"file": "surgery.png", "pos": "shoulder_left", "size": 200},
    "four weeks": {"file": "weeks.png", "pos": "top_right", "size": 280},
    "healed": {"file": "healed.png", "pos": "top_center", "size": 260},
    "friend": {"file": "friend.png", "pos": "top_left", "size": 200},
    "larry": {"file": "larry.png", "pos": "top_left", "size": 220},
    "tendon": {"file": "tendon.png", "pos": "shoulder_right", "size": 200},
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
    """
    Create TWO-LINE semantic captions:
    - Line 1: WHITE (setup phrase)
    - Line 2: YELLOW (emphasis phrase)
    
    Groups words into natural speech phrases (~4-7 words total, split into 2 lines)
    """
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
    
    # Group into semantic phrases (5-7 words per group)
    captions = []
    i = 0
    while i < len(all_words):
        # Take 5-7 words for one caption group
        chunk_size = min(6, len(all_words) - i)
        if chunk_size < 3:
            chunk_size = len(all_words) - i
        
        chunk = all_words[i:i + chunk_size]
        if not chunk:
            break
            
        # Split into two lines (roughly 60/40 split)
        split_point = max(2, len(chunk) // 2 + 1)
        line1_words = chunk[:split_point]
        line2_words = chunk[split_point:]
        
        line1 = ' '.join(w['text'] for w in line1_words)
        line2 = ' '.join(w['text'] for w in line2_words) if line2_words else ""
        
        # Check for emphasis keywords in line2
        has_emphasis = False
        emphasis_emoji = None
        full_text = (line1 + " " + line2).lower()
        
        for trigger, config in EMOJI_TRIGGERS.items():
            if trigger in full_text:
                has_emphasis = True
                emphasis_emoji = config
                break
        
        captions.append({
            'line1': line1,
            'line2': line2,
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
            'has_emphasis': has_emphasis,
            'emoji': emphasis_emoji,
        })
        
        i += chunk_size
    
    return captions

def generate_two_line_ass(captions: List[Dict], output_path: Path) -> Path:
    """
    Generate ASS with TWO-LINE format:
    - Line 1: WHITE text
    - Line 2: YELLOW text (emphasis)
    """
    console.print("  [dim]→ Generating two-line ASS captions...[/dim]")
    
    # ASS Header with styles
    header = f"""[Script Info]
Title: Viral Clip v9
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: White,Arial Rounded MT Bold,62,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,180,1
Style: Yellow,Arial Rounded MT Bold,62,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,130,1
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
        # Skip filler
        if cap['line1'].lower().strip() in ['yeah', 'yep']:
            continue
            
        # Pop animation
        pop = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        
        # Line 1 (WHITE) - positioned higher
        if cap['line1']:
            text1 = cap['line1'].upper()
            events.append(f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},White,,0,0,0,,{pop}{text1}")
        
        # Line 2 (YELLOW) - positioned lower
        if cap['line2']:
            text2 = cap['line2'].upper()
            events.append(f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Yellow,,0,0,0,,{pop}{text2}")
    
    # Final overlay
    final_t = 44.0
    events.append(f"Dialogue: 1,{fmt(final_t)},{fmt(final_t+2.5)},Final,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2-50})}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 1,{fmt(final_t)},{fmt(final_t+2.5)},Final,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2+80})\\c&H00FFFF&}}4 WEEKS • NO SURGERY")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    
    console.print(f"  [green]✓ Generated {len(events)} caption events[/green]")
    return output_path

def render_contextual_emojis(video_path: Path, captions: List[Dict], output_path: Path):
    """
    Apply CONTEXTUAL emoji overlays:
    - Only on emphasis keywords
    - Positioned in safe zones (shoulders/corners)
    """
    console.print("[dim]→ Applying contextual emoji overlays...[/dim]")
    
    # Collect emoji overlays
    overlays = []
    for cap in captions:
        if cap['emoji']:
            emoji_cfg = cap['emoji']
            img_path = EMOJI_DIR / emoji_cfg['file']
            if img_path.exists():
                pos = POSITIONS.get(emoji_cfg['pos'], (780, 950))
                overlays.append({
                    'path': img_path,
                    'x': pos[0],
                    'y': pos[1],
                    'size': emoji_cfg['size'],
                    'start': cap['start'],
                    'end': cap['end'] + 0.5,
                })
    
    if not overlays:
        console.print("  [yellow]No emoji triggers found, copying video...[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
    console.print(f"  [dim]Adding {len(overlays)} contextual emojis...[/dim]")
    
    # Build FFmpeg command
    inputs = ["-i", str(video_path)]
    filter_parts = []
    last_out = "[0:v]"
    
    for i, ov in enumerate(overlays):
        idx = i + 1
        inputs.extend(["-i", str(ov['path'])])
        
        # Scale emoji
        filter_parts.append(f"[{idx}:v]scale={ov['size']}:{ov['size']}[ov{idx}]")
        
        # Overlay at safe zone position
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
        console.print(f"[red]FFmpeg error: {result.stderr.decode()[:500]}[/red]")
        # Fallback: copy without emojis
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print(f"  [green]✓ Applied {len(overlays)} emojis[/green]")

def extract_zoom_out(start: float, end: float, output: Path) -> Path:
    """v4 zoom-out logic (user favorite)"""
    console.print("  [dim]→ Extracting with 20% zoom out...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v9_raw.mp4"
    
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
    
    # 25% wider crop for zoom-out effect
    crop_w = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output)
    ], capture_output=True, check=True)
    
    console.print("  [green]✓ Extracted with zoom out[/green]")
    return output

def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn ASS captions into video"""
    console.print("  [dim]→ Burning captions...[/dim]")
    
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ], capture_output=True, check=True)
    
    console.print("  [green]✓ Captions burned[/green]")
    return output_path

def verify_output(output_path: Path) -> bool:
    """Verify output quality"""
    console.print("[dim]→ Verifying output...[/dim]")
    
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=duration,codec_type",
        "-of", "json", str(output_path)
    ], capture_output=True, text=True)
    
    data = json.loads(result.stdout)
    durations = {}
    for s in data['streams']:
        durations[s['codec_type']] = float(s.get('duration', 0))
    
    video_dur = durations.get('video', 0)
    audio_dur = durations.get('audio', 0)
    diff = abs(video_dur - audio_dur)
    
    console.print(f"  Video: {video_dur:.2f}s | Audio: {audio_dur:.2f}s | Diff: {diff:.2f}s")
    
    if diff < 0.5:
        console.print("  [green]✓ Sync verified[/green]")
        return True
    else:
        console.print("  [red]✗ Sync issue detected[/red]")
        return False

def build_clip1_v9():
    """Build Clip 1 with reference-matched captions"""
    console.print(Panel.fit(
        "[bold cyan]🎬 Building Clip 1 v9[/bold cyan]\n"
        "• Two-line captions (WHITE + YELLOW)\n"
        "• Contextual emoji triggers\n"
        "• Safe zone positioning",
        title="Reference-Matched Style"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Load transcript and create semantic captions
    console.print("\n[bold]Step 1: Generate semantic captions[/bold]")
    transcript = load_transcript()
    captions = get_semantic_captions(transcript, START, END)
    console.print(f"  [green]✓ Created {len(captions)} two-line captions[/green]")
    
    # Preview
    console.print("  [dim]Preview:[/dim]")
    for cap in captions[:3]:
        console.print(f"    [{cap['start']:5.2f}s] {cap['line1']} | {cap['line2']}")
    
    # 2. Extract with zoom out
    console.print("\n[bold]Step 2: Extract video[/bold]")
    base_clip = TEMP_DIR / "clip1_v9_base.mp4"
    extract_zoom_out(START, END, base_clip)
    
    # 3. Apply contextual emojis
    console.print("\n[bold]Step 3: Contextual emojis[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v9_emoji.mp4"
    render_contextual_emojis(base_clip, captions, emoji_clip)
    
    # 4. Generate and burn captions
    console.print("\n[bold]Step 4: Two-line captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v9.ass"
    generate_two_line_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v9.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    # 5. Verify
    console.print("\n[bold]Step 5: Verify[/bold]")
    verify_output(final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))

if __name__ == "__main__":
    build_clip1_v9()

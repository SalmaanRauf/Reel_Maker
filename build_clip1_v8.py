#!/usr/bin/env python3
"""
Clip Builder v8 - Smart Sticker Placement (Manual Coordinates)
- Base: v4 Logic (Timing/Zoom)
- Emojis: Placed manually in "Safe Zones" (Shoulders, Corners)
- Captions: Anchored strictly to bottom
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

# Settings
ZOOM_OUT_PCT = 0.20

# Manual Coordinate Map for Clip 1
# 1080x1920 Canvas
# Center X = 540
# Approx Face Zone: y=400 to y=900
EMOJI_CONFIG = {
    "purple": {
        "file": "purple.png",
        "x": 750, "y": 400, "w": 250, # Top Right "Idea"
    },
    "surgery": {
        "file": "surgery.png",
        "x": 100, "y": 1100, "w": 250, # Left "Shoulder" area
    },
    "doctor": {
        "file": "doctor.png",
        "x": 100, "y": 400, "w": 250, # Top Left
    },
    "arm": {
        "file": "arm.png",
        "x": 750, "y": 1100, "w": 250, # Right "Shoulder"
    },
    "tendon": {
        "file": "tendon.png",
        "x": 750, "y": 1100, "w": 250, # Right
    },
    "weeks": {
        "file": "weeks.png",
        "x": 700, "y": 500, "w": 300, # Top Right (Calendar Ref)
    },
    "weight": {
        "file": "weight.png",
        "x": 100, "y": 1100, "w": 250, # Left
    },
    "friend": {
        "file": "friend.png",
        "x": 750, "y": 1000, "w": 250, # Right Shoulder
    },
    "larry": {
        "file": "larry.png",
        "x": 100, "y": 300, "w": 250, # Top Left
    },
    "needle": {
        "file": "surgery.png",
        "x": 100, "y": 1000, "w": 200, # Left
    },
    "healed": {
        "file": "healed.png",
        "x": 415, "y": 200, "w": 250, # Top Center (Godly/Halo spot)
    },
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

def get_word_level_captions(transcript: Dict, start: float, end: float, words_per_caption: int = 3) -> List[Dict]:
    """v4 Logic"""
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
    for i in range(0, len(all_words), words_per_caption):
        chunk = all_words[i:i + words_per_caption]
        if not chunk: continue
        captions.append({
            'text': ' '.join(w['text'] for w in chunk),
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
        })
    return captions

def generate_ass_text_only(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with Bottom Alignment"""
    console.print(f"  [dim]→ Generating ASS (Bottom Aligned)...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v8
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,150,1
Style: BigText,Arial Rounded MT Bold,80,&H0000FFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Note: PrimaryColour &H0000FFFF is Yellow (BGR) -> FFFF00 is Cyan... wait BGR.
    # Yellow is R=255, G=255, B=0. In HEX: FFFF00. In BGR: 00FFFF.
    # &H0000FFFF is Yellow.
    
    def fmt(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"
    
    events = []
    for cap in captions:
        text = cap['text'].upper()
        if text.lower().strip() in ['yeah', 'yep', 'yeah,', 'yep,']: continue
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},Default,,0,0,0,,{anim}{text}")
        
    final_t = 44.0
    events.append(f"Dialogue: 2,{fmt(final_t)},{fmt(final_t+2)},BigText,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2})\\c&HFFFFFF&}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 2,{fmt(final_t)},{fmt(final_t+2)},BigText,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2+120})\\c&H00D7FF&}}NO SURGERY")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    return output_path

def render_with_smart_overlays(video_path: Path, captions: List[Dict], output_path: Path):
    """
    Apply Smart Sticker Overlays via FFmpeg
    """
    console.print("[dim]→ Building smart sticker overlay chain...[/dim]")
    
    overlays = []
    for cap in captions:
        text = cap['text'].lower()
        for word in text.split():
            clean = word.strip(".,!?")
            if clean in EMOJI_CONFIG:
                cfg = EMOJI_CONFIG[clean]
                img_path = EMOJI_DIR / cfg['file']
                if img_path.exists():
                    overlays.append({
                        'path': img_path,
                        'x': cfg['x'],
                        'y': cfg['y'],
                        'w': cfg['w'],
                        'start': cap['start'],
                        'end': cap['end'] + 0.8 # Linger longer
                    })
    
    if not overlays:
        subprocess.run(["cp", str(video_path), str(output_path)])
        return

    inputs = ["-i", str(video_path)]
    filter_chain = []
    last_out = "[0:v]"
    
    for i, ov in enumerate(overlays):
        idx = i + 1
        inputs.extend(["-i", str(ov['path'])])
        # Scale
        filter_chain.append(f"[{idx}:v]scale={ov['w']}:{ov['w']}[ov{idx}]")
        # Overlay at specific X/Y
        filter_chain.append(f"{last_out}[ov{idx}]overlay=x={ov['x']}:y={ov['y']}:enable='between(t,{ov['start']},{ov['end']})'[v{idx}]")
        last_out = f"[v{idx}]"
        
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_chain),
        "-map", last_out,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    subprocess.run(cmd, capture_output=True, check=True)

def extract_simple_zoom_out(start: float, end: float, output: Path) -> Path:
    """v4 Logic"""
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v8_raw.mp4"
    subprocess.run(["ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH), "-t", str(duration), "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(raw_path)], capture_output=True, check=True)
    
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)], capture_output=True, text=True)
    w, h = map(int, res.stdout.strip().split(','))
    crop_w = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    subprocess.run(["ffmpeg", "-y", "-i", str(raw_path), "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy", str(output)], capture_output=True, check=True)
    return output

def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run(["ffmpeg", "-y", "-i", str(video_path), "-vf", f"subtitles='{ass_escaped}'", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy", str(output_path)], capture_output=True, check=True)
    return output_path

def build_clip1_v8():
    console.print("[bold cyan]🎬 Building Clip 1 v8 (Smart Stickers)[/bold cyan]")
    START, END = 3938.0, 3984.0
    
    # 1. Transcript
    transcript = load_transcript()
    captions = get_word_level_captions(transcript, START, END)
    
    # 2. Base Clip
    base_clip = TEMP_DIR / "clip1_v8_base.mp4"
    extract_simple_zoom_out(START, END, base_clip)
    
    # 3. Smart Stickers
    sticker_clip = TEMP_DIR / "clip1_v8_stickers.mp4"
    render_with_smart_overlays(base_clip, captions, sticker_clip)
    
    # 4. Captions (Bottom)
    ass_path = TEMP_DIR / "clip1_v8.ass"
    generate_ass_text_only(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v8.mp4"
    burn_captions(sticker_clip, ass_path, final_path)
    
    console.print(f"\n[green]✅ Done: {final_path}[/green]")

if __name__ == "__main__":
    build_clip1_v8()

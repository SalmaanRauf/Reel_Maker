#!/usr/bin/env python3
"""
Clip Builder v6 - Based on v4 (User Favorite) + Simple Emoji B-Roll
- Uses original transcript timestamps (v4 logic)
- Adds simple Emoji overlays via ASS subtitles (User requested "keyboard emojis")
- Maintains 20% zoom out
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

# Settings
ZOOM_OUT_PCT = 0.20
# Simple Emoji Map
EMOJI_MAP = {
    "purple": "🟣",
    "surgery": "💉",
    "doctor": "👨‍⚕️",
    "arm": "💪",
    "tricep": "💪",
    "tendon": "🦴",
    "weeks": "📅",
    "weight": "🏋️‍♂️",
    "lifting": "🏋️‍♂️",
    "friend": "🤝",
    "larry": "🦁", # Larry Wheels = Lion/Beast
    "needle": "💉",
    "healed": "✨",
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
    """v4 Logic: Flatten words then group"""
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

def generate_ass_with_emojis(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with captions AND emoji overlays"""
    console.print(f"  [dim]→ Generating ASS with captions & emojis...[/dim]")
    
    header = f"""[Script Info]
Title: Viral Clip v6
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1
Style: Emoji,Apple Color Emoji,200,&H00FFFFFF,&H00000000,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,50,50,550,1
Style: BigText,Arial Rounded MT Bold,80,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,8,50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def fmt_time(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"
    
    events = []
    
    # 1. Captions
    for cap in captions:
        text = cap['text'].upper()
        if text.lower().strip() in ['yeah', 'yep', 'yeah,', 'yep,']: continue
        
        # Pop animation
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{fmt_time(cap['start'])},{fmt_time(cap['end'])},Default,,0,0,0,,{anim}{text}")
        
        # 2. Check for Emojis
        # We check each word in the caption
        for word in text.split():
            clean_word = word.lower().strip('.,!?')
            if clean_word in EMOJI_MAP:
                emoji = EMOJI_MAP[clean_word]
                # Emoji appears for the duration of the caption + bit more
                # Position: Alignment 5 (Center), vertically shifted by margin
                # Animation: Pop in
                e_anim = r"{\fscx0\fscy0\t(0,150,\fscx100\fscy100)\t(150,300,\fscx120\fscy120)\t(300,500,\fscx100\fscy100)}"
                events.append(f"Dialogue: 1,{fmt_time(cap['start'])},{fmt_time(cap['end']+0.5)},Emoji,,0,0,0,,{e_anim}{emoji}")
                
    # 3. Final Text Overlay (preserved from previous verify)
    final_t = 44.0
    events.append(f"Dialogue: 2,{fmt_time(final_t)},{fmt_time(final_t+2)},BigText,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2})}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 2,{fmt_time(final_t)},{fmt_time(final_t+2)},BigText,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2+120})\\c&H00D7FF&}}NO SURGERY")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header + '\n'.join(events))
    
    return output_path

def extract_simple_zoom_out(start: float, end: float, output: Path) -> Path:
    """v4 Logic: 20% zoom out with centered crop"""
    console.print(f"  [dim]→ Extracting with {int(ZOOM_OUT_PCT*100)}% zoom out...[/dim]")
    duration = end - start
    
    # Extract raw
    raw_path = TEMP_DIR / "clip1_v6_raw.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH), "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "aac", "-b:a", "192k",
        str(raw_path)
    ], capture_output=True, check=True)
    
    # Calculate crop
    res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(raw_path)], capture_output=True, text=True)
    w, h = map(int, res.stdout.strip().split(','))
    
    crop_w_zoomed = min(int((h * 9 / 16) * 1.25), w)
    crop_x = (w - crop_w_zoomed) // 2
    
    subprocess.run([
        "ffmpeg", "-y", "-i", str(raw_path),
        "-vf", f"crop={crop_w_zoomed}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy",
        str(output)
    ], capture_output=True, check=True)
    
    return output

def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path), "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-c:a", "copy",
        str(output_path)
    ], capture_output=True, check=True)
    return output_path

def build_clip1_v6():
    console.print("[bold cyan]🎬 Building Clip 1 v6 (User Favorite + Emojis)[/bold cyan]")
    START, END = 3938.0, 3984.0
    
    # 1. Transcript (v4 logic)
    transcript = load_transcript()
    captions = get_word_level_captions(transcript, START, END)
    
    # 2. Extract (v4 logic)
    main_clip = TEMP_DIR / "clip1_v6_main.mp4"
    extract_simple_zoom_out(START, END, main_clip)
    
    # 3. Generate ASS with Emojis
    ass_path = TEMP_DIR / "clip1_v6.ass"
    generate_ass_with_emojis(captions, ass_path)
    
    # 4. Burn
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v6.mp4"
    burn_captions(main_clip, ass_path, final_path)
    
    console.print(f"\n[green]✅ Done: {final_path}[/green]")

if __name__ == "__main__":
    build_clip1_v6()

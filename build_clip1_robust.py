#!/usr/bin/env python3
"""
Clip 1 - Robust VFX Builder
Re-architected pipeline to eliminate sync issues and distortions.
- Uses strict stream normalization (FPS, AR, Resolution)
- Uses filter_complex overlays instead of concatenation
- Verifies stream duration equality
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Tuple
import whisper
from rich.console import Console
from rich.panel import Panel

# Import engines
from broll_engine import BRollEngine
from sfx_engine import SFXEngine

console = Console()

# Configuration
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
SFX_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/assets/sfx")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# VFX Markers relative to the MAIN CLIP (no offsets needed now)
VFX_MARKERS = {
    'purple_mention': 10.5,
    'purple_end': 14.0,
    'surgery_mention': 14.5,
    'tendon_inject': 17.5,
    'tendon_end': 21.0,
    'four_weeks': 22.0,
    'four_weeks_end': 24.0,
    'final_text_start': 44.0,
}

def extract_clip(start: float, end: float, output: Path) -> Path:
    """Extract main clip with forced normalization"""
    console.print(f"  [dim]→ Extracting clip {start}-{end}...[/dim]")
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(end - start),
        # Normalize video: 30fps, 4:2:0 colorspace, square pixels
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-r", "30", "-pix_fmt", "yuv420p",
        # Normalize audio: 44.1kHz, stereo
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output

def transcribe_and_gen_ass(video_path: Path, output_ass: Path) -> List[Dict]:
    """Transcribe and generate ASS subtitles"""
    console.print("  [dim]→ Transcribing with Whisper...[/dim]")
    model = whisper.load_model("base")
    result = model.transcribe(str(video_path), word_timestamps=True)
    
    words = []
    for seg in result['segments']:
        if 'words' in seg:
            for w in seg['words']:
                words.append({'text': w['word'].strip(), 'start': w['start'], 'end': w['end']})
    
    # Group into captions
    captions = []
    for i in range(0, len(words), 3):
        chunk = words[i:i+3]
        if not chunk: continue
        text = ' '.join(w['text'] for w in chunk).upper()
        if text.strip() in ['YEAH', 'YEP']: continue
        captions.append({'text': text, 'start': chunk[0]['start'], 'end': chunk[-1]['end']})
        
    # Generate ASS
    header = f"""[Script Info]
Title: Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1
Style: Yellow,Arial Rounded MT Bold,72,&H0000D7FF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1
Style: Big,Arial Rounded MT Bold,90,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,4,2,50,50,100,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt(s):
        h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"
        
    events = []
    for cap in captions:
        style = "Yellow" if any(x in cap['text'].lower() for x in ['purple', 'surgery', 'bpc']) else "Default"
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{fmt(cap['start'])},{fmt(cap['end'])},{style},,0,0,0,,{anim}{cap['text']}")
        
    # Final text
    t = VFX_MARKERS['final_text_start']
    events.append(f"Dialogue: 1,{fmt(t)},{fmt(t+2)},Big,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2})}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 1,{fmt(t)},{fmt(t+2)},Yellow,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2+100})}}4 WEEKS (NO SURGERY)")
    
    with open(output_ass, 'w') as f:
        f.write(header + '\n'.join(events))
        
    return captions

def perform_robust_render(
    main_video: Path,
    broll_map: Dict[str, Path],
    ass_path: Path,
    output_path: Path
) -> Path:
    """
    Robust Render:
    1. Zoom out main video
    2. Overlay B-roll using strict timebase
    3. Mix SFX
    4. Burn captions
    ALL in one FFmpeg pass if possible, or strictly controlled steps.
    """
    console.print("[dim]→ Starting robust render chain...[/dim]")
    
    # 1. Prepare main video crop (20% zoom out)
    # Get dims
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(main_video)],
        capture_output=True, text=True
    )
    w, h = map(int, probe.stdout.strip().split(','))
    crop_w = min(int(h * 9 / 16 * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    # Filter: crop -> scale -> pad
    main_filter = f"[0:v]crop={crop_w}:{h}:{crop_x}:0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[main]"
    
    # Build B-roll inputs
    inputs = ["-i", str(main_video)]
    
    # SFX Inputs
    sfx_start_idx = 0
    sfx_filters = []
    
    # SFX1 (Whoosh)
    whoosh = SFX_DIR / "whoosh.wav"
    inputs.append("-i"); inputs.append(str(whoosh))
    sfx1_idx = 1
    t1 = VFX_MARKERS['purple_mention']
    sfx_filters.append(f"[{sfx1_idx}:a]adelay={int(t1*1000)}|{int(t1*1000)},volume=0.6[sfx1]")
    
    # SFX2 (Dramatic)
    dramatic = SFX_DIR / "dramatic_hit.wav"
    inputs.append("-i"); inputs.append(str(dramatic))
    sfx2_idx = 2
    t2 = VFX_MARKERS['surgery_mention']
    sfx_filters.append(f"[{sfx2_idx}:a]adelay={int(t2*1000)}|{int(t2*1000)},volume=0.8[sfx2]")
    
    current_vid_input_idx = 3 # Next available index
    
    # B-roll overlay chain
    broll_filters = []
    overlay_base = "[main]"
    
    # Injection B-roll
    if 'injection' in broll_map:
        inputs.append("-i"); inputs.append(str(broll_map['injection']))
        idx = current_vid_input_idx
        start, end = VFX_MARKERS['tendon_inject'], VFX_MARKERS['tendon_end']
        broll_filters.append(
            f"[{idx}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
            f"trim=0:{end-start},setpts=PTS-STARTPTS[broll_inj]"
        )
        broll_filters.append(f"{overlay_base}[broll_inj]overlay=enable='between(t,{start},{end})':eof_action=pass[v1]")
        overlay_base = "[v1]"
        current_vid_input_idx += 1
        
    # Calendar B-roll
    if 'calendar' in broll_map:
        inputs.append("-i"); inputs.append(str(broll_map['calendar']))
        idx = current_vid_input_idx
        start, end = VFX_MARKERS['four_weeks'], VFX_MARKERS['four_weeks_end']
        broll_filters.append(
            f"[{idx}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
            f"trim=0:{end-start},setpts=PTS-STARTPTS[broll_cal]"
        )
        broll_filters.append(f"{overlay_base}[broll_cal]overlay=enable='between(t,{start},{end})':eof_action=pass[v2]")
        overlay_base = "[v2]"
        current_vid_input_idx += 1
        
    # Subtitles
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    sub_filter = f"{overlay_base}subtitles='{ass_escaped}'[outv]"
    
    # Audio Mix
    amix = f"[0:a][sfx1][sfx2]amix=inputs=3:duration=first[outa]"
    
    # Combine all filters
    full_filter = ";".join([main_filter] + sfx_filters + broll_filters + [sub_filter, amix])
    
    # Execute
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", full_filter,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]
    
    console.print("  [dim]→ Filtering complex chain...[/dim]")
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path

def verify_output(output_path: Path):
    """Verify stream durations match"""
    console.print("  [dim]→ Verifying stream integrity...[/dim]")
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "stream=duration,codec_type", "-of", "json",
        str(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(res.stdout)
    
    durations = {}
    for s in data['streams']:
        durations[s['codec_type']] = float(s['duration'])
        
    console.print(f"  Video: {durations.get('video', 0):.2f}s")
    console.print(f"  Audio: {durations.get('audio', 0):.2f}s")
    
    diff = abs(durations.get('video', 0) - durations.get('audio', 0))
    if diff > 0.1:
        console.print(f"  [red]❌ SYNC FAIL: Diff {diff:.2f}s[/red]")
    else:
        console.print(f"  [green]✅ SYNC OK: Diff {diff:.2f}s[/green]")

def build_clip1_robust():
    console.print("[bold]🎬 Building Clip 1 (Robust Architecture)[/bold]")
    
    START = 3938.0
    END = 3984.0
    
    # 1. Extract Main Clip (Normalized)
    main_clip = TEMP_DIR / "clip1_norm.mp4"
    extract_clip(START, END, main_clip)
    
    # 2. Transcribe & Props
    ass_path = TEMP_DIR / "clip1_robust.ass"
    transcribe_and_gen_ass(main_clip, ass_path)
    
    # 3. Fetch B-roll
    engine = BRollEngine()
    broll = {}
    
    # Pexels fetch
    c1 = engine.fetch_broll("medical injection treatment")
    if c1 and c1.local_path: broll['injection'] = c1.local_path
    
    c2 = engine.fetch_broll("calendar time passing days")
    if c2 and c2.local_path: broll['calendar'] = c2.local_path
    
    # 4. Render
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_robust.mp4"
    perform_robust_render(main_clip, broll, ass_path, final_path)
    
    # 5. Verify
    verify_output(final_path)

if __name__ == "__main__":
    build_clip1_robust()

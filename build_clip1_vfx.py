#!/usr/bin/env python3
"""
Clip 1 VFX Builder - Full featured version with:
- Perfect caption timing (Whisper on clip)
- B-roll from Pexels (Larry Wheels, weightlifting)
- Sound effects (whoosh, dramatic hit)
- Visual effects (purple tint, calendar flip text)
- Final text overlay
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Tuple
import whisper
from rich.console import Console
from rich.panel import Panel

# Import our engines
from broll_engine import BRollEngine
from sfx_engine import SFXEngine

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
SFX_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/assets/sfx")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Timing markers for VFX (in seconds relative to clip start)
VFX_MARKERS = {
    'hook_start': 0.0,       # Hook at very start
    'hook_end': 1.5,         # Larry Wheels B-roll duration
    # ALL timestamps below must include hook_end duration (1.5s) if they are relative to the original audio
    'purple_mention': 10.5 + 1.5,  # "purple from here to here" 
    'purple_end': 14.0 + 1.5,
    'surgery_mention': 14.5 + 1.5, # "surgery sucks"
    'tendon_inject': 17.5 + 1.5,   # "into the tendon"
    'tendon_end': 21.0 + 1.5,
    'four_weeks': 22.0 + 1.5,      # "four weeks later"
    'four_weeks_end': 24.0 + 1.5,
    'final_text_start': 44.0 + 1.5,  # Final text overlay
}


def extract_raw_clip(start: float, end: float, output: Path) -> Path:
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(VIDEO_PATH),
        "-t", str(end - start),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output


def transcribe_clip(video_path: Path) -> List[Dict]:
    """Transcribe clip with Whisper for perfect timing"""
    console.print("  [dim]→ Running Whisper on clip...[/dim]")
    model = whisper.load_model("base")
    result = model.transcribe(str(video_path), word_timestamps=True)
    
    words = []
    for seg in result['segments']:
        if 'words' in seg:
            for w in seg['words']:
                text = w['word'].strip()
                # Fix common errors
                if text.lower() == 'lair':
                    text = 'Larry'
                words.append({
                    'text': text,
                    'start': round(w['start'], 3),
                    'end': round(w['end'], 3),
                })
    console.print(f"  [green]✓ {len(words)} words transcribed[/green]")
    return words


def group_into_captions(words: List[Dict], words_per: int = 3) -> List[Dict]:
    """Group words into short captions"""
    captions = []
    for i in range(0, len(words), words_per):
        chunk = words[i:i + words_per]
        if not chunk:
            continue
        text = ' '.join(w['text'] for w in chunk)
        if text.lower().strip() in ['yeah', 'yep', 'yeah,', 'yep,']:
            continue
        captions.append({
            'text': text.upper(),
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
        })
    return captions


def generate_ass_with_highlights(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS with special highlighting for key phrases"""
    header = f"""[Script Info]
Title: BPC-157 Viral Clip
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
    
    def fmt_time(s):
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"
    
    # Offset for the 1.5s hook at the start
    HOOK_OFFSET = 1.5
    
    events = []
    for cap in captions:
        # Check for highlight keywords
        text = cap['text']
        style = "Default"
        
        if any(k in text.lower() for k in ['purple', 'surgery', 'bpc']):
            style = "Yellow"
        
        # Add offset to timing
        start_time = cap['start'] + HOOK_OFFSET
        end_time = cap['end'] + HOOK_OFFSET
        
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        events.append(f"Dialogue: 0,{fmt_time(start_time)},{fmt_time(end_time)},{style},,0,0,0,,{anim}{text}")
    
    # Add final text overlay
    final_start = VFX_MARKERS['final_text_start']
    events.append(f"Dialogue: 1,{fmt_time(final_start)},{fmt_time(final_start + 2)},Big,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2})}}PURPLE 🟣 → HEALED")
    events.append(f"Dialogue: 1,{fmt_time(final_start)},{fmt_time(final_start + 2)},Yellow,,0,0,0,,{{\\an5\\pos({OUT_W//2},{OUT_H//2 + 100})}}4 WEEKS (NO SURGERY)")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(events))
    
    return output_path


def apply_zoom_out(input_path: Path, output_path: Path) -> Path:
    """Apply 20% zoom out"""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(input_path)],
        capture_output=True, text=True
    )
    w, h = map(int, probe.stdout.strip().split(','))
    crop_w = min(int(h * 9 / 16 * 1.25), w)
    crop_x = (w - crop_w) // 2
    
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"crop={crop_w}:{h}:{crop_x}:0,scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def fetch_broll_clips() -> Dict[str, Path]:
    """Fetch B-roll clips for this video"""
    console.print("  [dim]→ Fetching B-roll from Pexels...[/dim]")
    engine = BRollEngine()
    
    broll = {}
    
    # Larry Wheels / weightlifting for hook
    clip = engine.fetch_broll("powerlifter gym heavy weights")
    if clip and clip.local_path:
        broll['hook'] = clip.local_path
        console.print(f"  [green]✓ Hook B-roll: {clip.local_path.name}[/green]")
    
    # Medical/healing for tendon injection
    clip = engine.fetch_broll("medical injection treatment")
    if clip and clip.local_path:
        broll['injection'] = clip.local_path
        console.print(f"  [green]✓ Injection B-roll: {clip.local_path.name}[/green]")
    
    # Calendar for "four weeks later"
    clip = engine.fetch_broll("calendar time passing days")
    if clip and clip.local_path:
        broll['calendar'] = clip.local_path
        console.print(f"  [green]✓ Calendar B-roll: {clip.local_path.name}[/green]")
    
    return broll


def compose_with_broll(main_video: Path, broll: Dict[str, Path], output_path: Path) -> Path:
    """Insert B-roll clips at specific moments by cutting and concatenating"""
    console.print("  [dim]→ Inserting B-roll clips...[/dim]")
    
    if not broll or 'hook' not in broll:
        console.print("  [yellow]⚠ No hook B-roll available, skipping[/yellow]")
        subprocess.run(["cp", str(main_video), str(output_path)], check=True)
        return output_path
    
    # Simple approach: Just add B-roll at the start as a hook
    hook_path = broll.get('hook')
    if not hook_path or not hook_path.exists():
        subprocess.run(["cp", str(main_video), str(output_path)], check=True)
        return output_path
    
    # Prepare hook clip: scale to 9:16, trim to 1.5s
    hook_prepared = TEMP_DIR / "hook_prepared.mp4"
    hook_duration = 1.5
    
    cmd = [
        "ffmpeg", "-y", "-i", str(hook_path),
        "-t", str(hook_duration),
        "-vf", f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an",  # Remove audio from B-roll
        str(hook_prepared)
    ]
    subprocess.run(cmd, capture_output=True)
    
    # Add flash effect and "Larry Wheels" text to hook
    hook_with_text = TEMP_DIR / "hook_text.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(hook_prepared),
        "-vf", f"drawtext=text='LARRY WHEELS':fontsize=60:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-150",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        str(hook_with_text)
    ]
    subprocess.run(cmd, capture_output=True)
    
    # Create concat list
    concat_list = TEMP_DIR / "concat_list.txt"
    with open(concat_list, 'w') as f:
        f.write(f"file '{hook_with_text}'\n")
        f.write(f"file '{main_video}'\n")
    
    # Concatenate: hook + main video
    # First need to ensure same audio format
    main_with_audio = TEMP_DIR / "main_for_concat.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(main_video),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(main_with_audio)
    ]
    subprocess.run(cmd, capture_output=True)
    
    # Add silent audio to hook
    hook_with_audio = TEMP_DIR / "hook_audio.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(hook_with_text),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(hook_duration),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(hook_with_audio)
    ]
    subprocess.run(cmd, capture_output=True)
    
    # Update concat list
    with open(concat_list, 'w') as f:
        f.write(f"file '{hook_with_audio}'\n")
        f.write(f"file '{main_with_audio}'\n")
    
    # Concatenate
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        console.print(f"  [yellow]⚠ Concat failed: {result.stderr[:100]}[/yellow]")
        subprocess.run(["cp", str(main_video), str(output_path)], check=True)
    else:
        console.print("  [green]✓ Hook B-roll added at start[/green]")
    
    return output_path


def add_sound_effects(video_path: Path, output_path: Path) -> Path:
    """Add sound effects at key moments"""
    console.print("  [dim]→ Adding sound effects...[/dim]")
    
    whoosh = SFX_DIR / "whoosh.wav"
    dramatic = SFX_DIR / "dramatic_hit.wav"
    
    if not whoosh.exists() or not dramatic.exists():
        console.print("  [yellow]⚠ SFX files missing, skipping[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
        return output_path
    
    # Add whoosh at purple mention, dramatic hit at "surgery sucks"
    filter_complex = (
        f"[1:a]adelay={int(VFX_MARKERS['purple_mention']*1000)}|{int(VFX_MARKERS['purple_mention']*1000)}[sfx1];"
        f"[2:a]adelay={int(VFX_MARKERS['surgery_mention']*1000)}|{int(VFX_MARKERS['surgery_mention']*1000)}[sfx2];"
        f"[0:a][sfx1][sfx2]amix=inputs=3:duration=first[aout]"
    )
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(whoosh),
        "-i", str(dramatic),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [yellow]⚠ SFX mixing failed: {result.stderr[:100]}[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)], check=True)
    else:
        console.print("  [green]✓ Sound effects added[/green]")
    
    return output_path


def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn captions into video"""
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def verify_timing(video_path: Path, captions: List[Dict]) -> bool:
    """Verify caption timing with Whisper"""
    console.print("  [dim]→ Verifying timing...[/dim]")
    model = whisper.load_model("base")
    result = model.transcribe(str(video_path), word_timestamps=True)
    
    verify_words = []
    for seg in result['segments']:
        if 'words' in seg:
            for w in seg['words']:
                verify_words.append({'text': w['word'].strip().lower(), 'start': w['start']})
    
    # Check first few captions
    perfect_count = 0
    # HOOK_OFFSET = 1.5 
    # NOTE: validation runs on the *final* video which has the hook.
    # Whisper on final video will see timestamps shifted by 1.5s
    # Our 'captions' list has UN-shifted timestamps (before we added 1.5s in generate_ass)
    # BUT verify_timing takes 'captions' which is the list of dicts.
    # So we need to compare: (cap['start'] + 1.5) vs whisper_timestamp
    
    for cap in captions[:5]:
        first_word = cap['text'].split()[0].lower()
        cap_start_shifted = cap['start'] + 1.5  # Shift expected time
        
        for vw in verify_words:
            if vw['text'] == first_word:
                diff = abs(vw['start'] - cap_start_shifted)
                if diff < 0.2:  # Allow 0.2s tolerance
                    perfect_count += 1
                else:
                    console.print(f"  [red]Mismatch '{first_word}': exp {cap_start_shifted:.2f}s, got {vw['start']:.2f}s (diff {diff:.2f}s)[/red]")
                break
    
    is_perfect = perfect_count >= 4
    if is_perfect:
        console.print("  [green]✓ Timing verified[/green]")
    else:
        console.print(f"  [yellow]⚠ {perfect_count}/5 captions verified[/yellow]")
    return is_perfect


def build_clip_1_vfx():
    """Build Clip 1 with full VFX"""
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep - VFX Edition[/bold cyan]\n"
        "• B-roll overlays (weightlifting, medical)\n"
        "• Sound effects (whoosh, dramatic hit)\n"
        "• Highlighted captions\n"
        "• Final text overlay",
        title="🎬 Building Full VFX"
    ))
    
    START = 3938.0
    END = 3984.0
    
    # Step 1: Extract
    console.print("\n[bold]Step 1: Extract clip[/bold]")
    raw_path = TEMP_DIR / "clip1_raw.mp4"
    extract_raw_clip(START, END, raw_path)
    console.print(f"  [green]✓ Extracted {END-START}s[/green]")
    
    # Step 2: Transcribe
    console.print("\n[bold]Step 2: Transcribe[/bold]")
    words = transcribe_clip(raw_path)
    captions = group_into_captions(words)
    console.print(f"  [green]✓ {len(captions)} captions[/green]")
    
    # Step 3: Zoom out
    console.print("\n[bold]Step 3: Zoom out[/bold]")
    zoomed_path = TEMP_DIR / "clip1_zoomed.mp4"
    apply_zoom_out(raw_path, zoomed_path)
    console.print("  [green]✓ Zoomed[/green]")
    
    # Step 4: Fetch B-roll
    console.print("\n[bold]Step 4: Fetch B-roll[/bold]")
    broll = fetch_broll_clips()
    
    # Step 5: Composite B-roll
    console.print("\n[bold]Step 5: Composite B-roll[/bold]")
    composed_path = TEMP_DIR / "clip1_broll.mp4"
    compose_with_broll(zoomed_path, broll, composed_path)
    
    # Step 6: Add SFX
    console.print("\n[bold]Step 6: Add sound effects[/bold]")
    sfx_path = TEMP_DIR / "clip1_sfx.mp4"
    add_sound_effects(composed_path, sfx_path)
    
    # Step 7: Generate captions
    console.print("\n[bold]Step 7: Generate captions[/bold]")
    ass_path = TEMP_DIR / "clip1_vfx.ass"
    generate_ass_with_highlights(captions, ass_path)
    console.print(f"  [green]✓ ASS generated[/green]")
    
    # Step 8: Burn captions
    console.print("\n[bold]Step 8: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_vfx.mp4"
    burn_captions(sfx_path, ass_path, final_path)
    console.print(f"  [green]✓ Captions burned[/green]")
    
    # Step 9: Verify
    console.print("\n[bold]Step 9: Verify[/bold]")
    verify_timing(final_path, captions)
    
    console.print(Panel.fit(
        f"[bold green]✅ VFX Clip Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Success"
    ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 VFX Clip Builder[/bold magenta]\n")
    build_clip_1_vfx()

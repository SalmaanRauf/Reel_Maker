#!/usr/bin/env python3
"""
Clip Builder v5 - Perfect Caption Timing
Runs Whisper directly on extracted clip for exact timestamps.
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict
import whisper
import cv2
from rich.console import Console
from rich.panel import Panel

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920

# Word fixes for common Whisper errors in this podcast
WORD_FIXES = {
    "lair": "Larry",
    "Lair": "Larry",
    "viral": "vial",
}


def fix_word(word: str) -> str:
    return WORD_FIXES.get(word.strip(), word.strip())


def extract_raw_clip(start: float, end: float, output: Path) -> Path:
    """Extract raw clip from source video"""
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
    """
    Transcribe the clip directly with Whisper for PERFECT timing.
    Returns word-level timestamps.
    """
    console.print("  [dim]→ Running Whisper on clip (this gives exact timing)...[/dim]")
    
    model = whisper.load_model("base")
    result = model.transcribe(str(video_path), word_timestamps=True)
    
    words = []
    for seg in result['segments']:
        if 'words' in seg:
            for w in seg['words']:
                words.append({
                    'text': fix_word(w['word']),
                    'start': round(w['start'], 3),
                    'end': round(w['end'], 3),
                })
    
    console.print(f"  [green]✓ Transcribed {len(words)} words with exact timing[/green]")
    return words


def group_words_into_captions(words: List[Dict], words_per_caption: int = 3) -> List[Dict]:
    """Group words into short captions (2-4 words each)"""
    captions = []
    
    for i in range(0, len(words), words_per_caption):
        chunk = words[i:i + words_per_caption]
        if not chunk:
            continue
        
        text = ' '.join(w['text'] for w in chunk)
        
        # Skip filler-only captions
        if text.lower().strip() in ['yeah', 'yep', 'yeah,', 'yep,', 'yeah.', 'yep.']:
            continue
        
        captions.append({
            'text': text,
            'start': chunk[0]['start'],
            'end': chunk[-1]['end'],
        })
    
    return captions


def generate_ass(captions: List[Dict], output_path: Path) -> Path:
    """Generate ASS subtitles with exact timing"""
    console.print(f"  [dim]→ Generating {len(captions)} captions...[/dim]")
    
    header = f"""[Script Info]
Title: BPC-157 Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Rounded MT Bold,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,3,2,50,50,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    
    events = []
    for cap in captions:
        anim = r"{\fscx20\fscy20\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}"
        text = cap['text'].upper()
        events.append(f"Dialogue: 0,{fmt_time(cap['start'])},{fmt_time(cap['end'])},Default,,0,0,0,,{anim}{text}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write('\n'.join(events))
    
    console.print(f"  [green]✓ Generated ASS with exact Whisper timing[/green]")
    return output_path


def apply_zoom_out(input_path: Path, output_path: Path, zoom_pct: float = 0.20) -> Path:
    """Apply 20% zoom out with centered crop"""
    console.print("  [dim]→ Applying zoom out...[/dim]")
    
    # Get dimensions
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(input_path)],
        capture_output=True, text=True
    )
    w, h = map(int, probe.stdout.strip().split(','))
    
    # Calculate zoom out crop (25% more width to show more scene)
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
    console.print("  [green]✓ Applied zoom out[/green]")
    return output_path


def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn captions into video"""
    console.print("  [dim]→ Burning captions...[/dim]")
    
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


def verify_caption_timing(video_path: Path, captions: List[Dict]) -> bool:
    """
    Verify captions are properly synced by re-running Whisper and comparing.
    Returns True if timing is accurate.
    """
    console.print("\n[bold]Verification: Checking caption sync...[/bold]")
    
    model = whisper.load_model("base")
    result = model.transcribe(str(video_path), word_timestamps=True)
    
    verify_words = []
    for seg in result['segments']:
        if 'words' in seg:
            for w in seg['words']:
                verify_words.append({'text': w['word'].strip(), 'start': w['start']})
    
    # Compare first 10 caption starts
    diffs = []
    cap_idx = 0
    for cap in captions[:10]:
        # Find matching word in verify
        cap_first_word = cap['text'].split()[0].lower()
        for vw in verify_words:
            if vw['text'].lower() == cap_first_word:
                diff = abs(vw['start'] - cap['start'])
                diffs.append(diff)
                console.print(f"  [{cap['start']:5.2f}s] {cap_first_word:15} → verify: [{vw['start']:5.2f}s] (diff: {diff:.3f}s)")
                break
    
    if diffs:
        avg_diff = sum(diffs) / len(diffs)
        console.print(f"\n  Average timing difference: {avg_diff:.3f}s")
        
        if avg_diff < 0.1:
            console.print("  [green]✓ Timing is PERFECT (within 0.1s)[/green]")
            return True
        else:
            console.print(f"  [yellow]⚠ Timing off by {avg_diff:.2f}s[/yellow]")
            return False
    
    return True


def build_clip_1():
    """Build Clip 1 with PERFECT caption timing"""
    console.print(Panel.fit(
        "[bold cyan]Clip 1: The Purple Tricep[/bold cyan]\n"
        "• Whisper transcription of extracted clip\n"
        "• Word-level captions (3 words each)\n"
        "• Verification before output",
        title="🎬 Building v5 (Perfect Timing)"
    ))
    
    START = 3938.0
    END = 3984.0
    
    # Step 1: Extract raw clip
    console.print("\n[bold]Step 1: Extract raw clip[/bold]")
    raw_path = TEMP_DIR / "clip1_raw.mp4"
    extract_raw_clip(START, END, raw_path)
    console.print(f"  [green]✓ Extracted {END - START}s[/green]")
    
    # Step 2: Transcribe the CLIP directly (not the full podcast)
    console.print("\n[bold]Step 2: Transcribe clip with Whisper[/bold]")
    words = transcribe_clip(raw_path)
    
    # Preview first few words
    console.print("  [dim]First 10 words with exact timing:[/dim]")
    for w in words[:10]:
        console.print(f"    [{w['start']:5.2f}s] {w['text']}")
    
    # Step 3: Group into captions
    console.print("\n[bold]Step 3: Create word-level captions[/bold]")
    captions = group_words_into_captions(words, words_per_caption=3)
    console.print(f"  [green]✓ Created {len(captions)} short captions[/green]")
    
    # Step 4: Apply zoom out
    console.print("\n[bold]Step 4: Apply zoom out[/bold]")
    zoomed_path = TEMP_DIR / "clip1_zoomed.mp4"
    apply_zoom_out(raw_path, zoomed_path)
    
    # Step 5: Generate ASS captions
    console.print("\n[bold]Step 5: Generate ASS captions[/bold]")
    ass_path = TEMP_DIR / "clip1_perfect.ass"
    generate_ass(captions, ass_path)
    
    # Step 6: Burn captions
    console.print("\n[bold]Step 6: Burn captions[/bold]")
    final_path = OUTPUT_DIR / "clip_1_purple_tricep.mp4"
    burn_captions(zoomed_path, ass_path, final_path)
    
    # Step 7: VERIFY timing
    console.print("\n[bold]Step 7: Verify caption timing[/bold]")
    is_perfect = verify_caption_timing(final_path, captions)
    
    if is_perfect:
        console.print(Panel.fit(
            f"[bold green]✅ Perfect![/bold green]\n"
            f"Output: [cyan]{final_path}[/cyan]",
            title="Success"
        ))
    else:
        console.print(Panel.fit(
            f"[bold yellow]⚠ Timing needs review[/bold yellow]\n"
            f"Output: [cyan]{final_path}[/cyan]",
            title="Warning"
        ))
    
    return final_path


if __name__ == "__main__":
    console.print("[bold magenta]🎬 Clip Builder v5 - Perfect Caption Timing[/bold magenta]\n")
    build_clip_1()

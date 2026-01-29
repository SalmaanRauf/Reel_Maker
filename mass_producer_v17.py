#!/usr/bin/env python3
"""
Mass Clip Producer v17
Builds all 11 viral clips with:
- Karaoke word-by-word red highlight captions
- Static top title (Santa Cruz & Dr. Bakri)
- Impact font 72pt, MarginV=340
- 9:16 vertical format (1080x1920)
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Paths
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")
TRANSCRIPT_PATH = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

OUT_W, OUT_H = 1080, 1920
FONT_SIZE = 72
WORDS_PER_LINE = 4

# Word fixes
WORD_FIXES = {"lair": "Larry", "Lair": "Larry", "viral": "vial", "larry": "Larry"}

# All 11 clips with their configurations
CLIPS = [
    {
        "clip_id": 1,
        "name": "clip_01_purple_tricep",
        "start": 3938.0,
        "end": 3984.0,
        "title_line1": "Santa Cruz & Dr. Bakri Explain",
        "title_line2": "How BPC-157 Heals Torn Tendons"
    },
    {
        "clip_id": 2,
        "name": "clip_02_rat_acl",
        "start": 2305.0,
        "end": 2334.0,
        "title_line1": "Santa Cruz & Dr. Bakri Reveal",
        "title_line2": "BPC-157 Regrew a Torn ACL 100%"
    },
    {
        "clip_id": 3,
        "name": "clip_03_blocks_amphetamines",
        "start": 2318.0,
        "end": 2348.0,
        "title_line1": "Santa Cruz & Dr. Bakri Discuss",
        "title_line2": "BPC-157 Blocked Lethal Drug Doses"
    },
    {
        "clip_id": 4,
        "name": "clip_04_bolus_protocol",
        "start": 4175.0,
        "end": 4210.0,
        "title_line1": "Santa Cruz & Dr. Bakri Share",
        "title_line2": "The High-Dose BPC-157 Protocol"
    },
    {
        "clip_id": 5,
        "name": "clip_05_oral_works",
        "start": 4012.0,
        "end": 4042.0,
        "title_line1": "Santa Cruz & Dr. Bakri Debunk",
        "title_line2": '"BPC-157 Doesn\'t Work Orally"'
    },
    {
        "clip_id": 6,
        "name": "clip_06_fda_loophole",
        "start": 4031.0,
        "end": 4061.0,
        "title_line1": "Santa Cruz & Dr. Bakri Explain",
        "title_line2": "The BPC-157 FDA Ban Loophole"
    },
    {
        "clip_id": 7,
        "name": "clip_07_where_inject",
        "start": 4146.0,
        "end": 4184.0,
        "title_line1": "Santa Cruz & Dr. Bakri Teach",
        "title_line2": "Where to Inject BPC-157"
    },
    {
        "clip_id": 8,
        "name": "clip_08_cancer_truth",
        "start": 5073.0,
        "end": 5110.0,
        "title_line1": "Santa Cruz & Dr. Bakri Address",
        "title_line2": "Does BPC-157 Cause Cancer?"
    },
    {
        "clip_id": 9,
        "name": "clip_09_gateway_drug",
        "start": 80.0,
        "end": 110.0,
        "title_line1": "Santa Cruz & Dr. Bakri Call It",
        "title_line2": "The Gateway Drug of Biohacking"
    },
    {
        "clip_id": 10,
        "name": "clip_10_not_magic",
        "start": 3918.0,
        "end": 3945.0,
        "title_line1": "Santa Cruz & Dr. Bakri Clarify",
        "title_line2": "BPC-157 Isn't Magic—Here's Why"
    },
    {
        "clip_id": 11,
        "name": "clip_11_hgh_stack",
        "start": 4264.0,
        "end": 4303.0,
        "title_line1": "Santa Cruz & Dr. Bakri Reveal",
        "title_line2": "The Secret BPC-157 + HGH Stack"
    }
]

def fix_word(word: str) -> str:
    return WORD_FIXES.get(word, word)

def load_transcript() -> Dict:
    with open(TRANSCRIPT_PATH) as f:
        return json.load(f)

def get_words(transcript: Dict, start: float, end: float) -> List[Dict]:
    words = []
    duration = end - start
    for seg in transcript['segments']:
        if 'words' not in seg:
            continue
        for w in seg['words']:
            if w['end'] > start and w['start'] < end:
                text = fix_word(w['text'].strip())
                if not text:
                    continue
                rel_start = max(0.0, round(w['start'] - start, 3))
                rel_end = min(duration, round(w['end'] - start, 3))
                if rel_end > rel_start:
                    words.append({
                        'text': text.upper(),
                        'start': rel_start,
                        'end': rel_end,
                    })
    return words

def group_words_into_lines(words: List[Dict], words_per_line: int = 4) -> List[List[Dict]]:
    lines = []
    for i in range(0, len(words), words_per_line):
        lines.append(words[i:i + words_per_line])
    return lines

def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_ass_subtitles(lines: List[List[Dict]], output_path: Path, duration: float, 
                           title_line1: str, title_line2: str):
    """Generate ASS with karaoke captions and top title"""
    
    white = "&H00FFFFFF"
    black = "&H00000000"
    red = "&H003D1CE3"
    
    ass_content = f"""[Script Info]
Title: Karaoke Viral Clip
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,{FONT_SIZE},{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,6,6,2,10,10,340,1
Style: TopTitle,Arial,42,{white},{white},{black},{black},-1,0,0,0,100,100,0,0,1,4,2,8,20,20,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    
    # Top title (persists entire video)
    end_time = format_ass_time(duration)
    events.append(f"Dialogue: 0,0:00:00.00,{end_time},TopTitle,,0,0,0,,{title_line1}\\N{title_line2}")
    
    # Karaoke captions
    for line in lines:
        if not line:
            continue
        
        for word_idx, current_word in enumerate(line):
            word_start = format_ass_time(current_word['start'])
            word_end = format_ass_time(current_word['end'])
            
            text_parts = []
            for i, w in enumerate(line):
                if i == word_idx:
                    text_parts.append(f"{{\\3c{red}\\bord14\\shad6}}{w['text']}{{\\3c{black}\\bord6\\shad6}}")
                else:
                    text_parts.append(w['text'])
            
            line_text = " ".join(text_parts)
            events.append(f"Dialogue: 0,{word_start},{word_end},Default,,0,0,0,,{line_text}")
    
    ass_content += "\n".join(events)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

def extract_base_video(start: float, end: float, output: Path) -> Path:
    """Extract and crop video to 9:16"""
    duration = end - start
    raw_path = TEMP_DIR / "temp_raw.mp4"
    
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
    
    return output

def burn_subtitles(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """Burn ASS subtitles into video"""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    
    if result.returncode != 0:
        raise Exception(f"FFmpeg error: {result.stderr.decode()[:500]}")
    
    return output_path

def build_clip(clip_config: Dict, transcript: Dict) -> Path:
    """Build a single clip with all effects"""
    clip_id = clip_config['clip_id']
    name = clip_config['name']
    start = clip_config['start']
    end = clip_config['end']
    title1 = clip_config['title_line1']
    title2 = clip_config['title_line2']
    duration = end - start
    
    console.print(f"\n[bold cyan]Building Clip {clip_id}: {name}[/bold cyan]")
    console.print(f"  Duration: {duration:.1f}s | Title: {title1}")
    
    # Get words
    words = get_words(transcript, start, end)
    if not words:
        console.print(f"  [yellow]Warning: No words found for clip {clip_id}[/yellow]")
        return None
    
    lines = group_words_into_lines(words, WORDS_PER_LINE)
    console.print(f"  ✓ Found {len(words)} words, {len(lines)} lines")
    
    # Generate ASS
    ass_path = TEMP_DIR / f"{name}.ass"
    generate_ass_subtitles(lines, ass_path, duration, title1, title2)
    
    # Extract base video
    base_path = TEMP_DIR / f"{name}_base.mp4"
    extract_base_video(start, end, base_path)
    console.print(f"  ✓ Extracted base video")
    
    # Burn subtitles
    final_path = OUTPUT_DIR / f"{name}.mp4"
    burn_subtitles(base_path, ass_path, final_path)
    console.print(f"  ✓ Burned captions → {final_path.name}")
    
    return final_path

def main():
    console.print(Panel.fit(
        "[bold magenta]🎬 Mass Clip Producer v17[/bold magenta]\n"
        "• 11 viral clips with karaoke captions\n"
        "• Santa Cruz & Dr. Bakri titles\n"
        "• Word-by-word red highlight effect",
        title="Viral Clip Generator"
    ))
    
    # Load transcript once
    console.print("\n[bold]Loading transcript...[/bold]")
    transcript = load_transcript()
    console.print("  ✓ Transcript loaded")
    
    # Build all clips
    successful = []
    failed = []
    
    for clip in CLIPS:
        try:
            result = build_clip(clip, transcript)
            if result:
                successful.append(clip['name'])
        except Exception as e:
            console.print(f"  [red]✗ Error: {e}[/red]")
            failed.append(clip['name'])
    
    # Summary
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Successful: {len(successful)}/{len(CLIPS)}\n"
        f"Failed: {len(failed)}\n"
        f"Output: {OUTPUT_DIR}",
        title="Summary"
    ))
    
    if failed:
        console.print(f"\n[red]Failed clips: {', '.join(failed)}[/red]")

if __name__ == "__main__":
    main()

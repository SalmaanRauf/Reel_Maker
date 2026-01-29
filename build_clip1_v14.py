#!/usr/bin/env python3
"""
Clip Builder v14 - Intelligent PIP with Face Detection
Features:
- Detects which speaker is on-screen (left/right)
- Places PIP of the OTHER person in the opposite corner
- LEFT speaker on-screen → PIP top-RIGHT (host)
- RIGHT speaker on-screen → PIP top-LEFT (Dr. Abud)
"""
import subprocess
import json
import cv2
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from rich.console import Console
from rich.panel import Panel
from face_detection import FaceDetector

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

# Caption Style (from v13)
FONT_SIZE = 72
BASE_MARGIN_V_LINE1 = 280
BASE_MARGIN_V_LINE2 = 190
EMOJI_SIZE = 200
EMOJI_Y = 1340
EMOJI_DURATION = 1.5
EMOJI_GAP = 0.3
EMOJI_COOLDOWN = 10.0

# PIP Configuration
PIP_SIZE = 280  # Size of PIP window
PIP_PADDING = 25  # Padding from edges
PIP_Y = 60  # Y position from top

SLANT_ANGLES = [-4, 4]
MARGIN_VARIATION = [-15, 0, 15]

WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
GREEN = "&H0099FF00"

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

def analyze_speaker_segments(video_path: Path, start: float, end: float, 
                            sample_interval: float = 0.5) -> List[Dict]:
    """
    Analyze the clip to identify speaker segments.
    Returns list of {start, end, speaker} where speaker is 'left' or 'right'.
    """
    console.print("  [dim]→ Analyzing speaker segments with face detection...[/dim]")
    
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    # Seek to start
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    
    detector = FaceDetector()
    samples = []
    
    current_time = start
    frame_interval = int(fps * sample_interval)
    
    while current_time < end:
        ret, frame = cap.read()
        if not ret:
            break
        
        speaker = detector.identify_speaker(frame)
        rel_time = current_time - start  # Relative to clip start
        
        samples.append({
            'time': rel_time,
            'abs_time': current_time,
            'speaker': speaker or 'left',  # Default to left if detection fails
        })
        
        # Skip frames
        for _ in range(frame_interval - 1):
            cap.read()
            current_time += 1 / fps
        
        current_time += 1 / fps
    
    cap.release()
    
    # Convert to segments
    if not samples:
        return [{'start': 0, 'end': end - start, 'speaker': 'left'}]
    
    segments = []
    current_speaker = samples[0]['speaker']
    segment_start = samples[0]['time']
    
    for i, sample in enumerate(samples[1:], 1):
        if sample['speaker'] != current_speaker:
            segments.append({
                'start': segment_start,
                'end': sample['time'],
                'speaker': current_speaker,
            })
            current_speaker = sample['speaker']
            segment_start = sample['time']
    
    # Final segment
    segments.append({
        'start': segment_start,
        'end': samples[-1]['time'] + sample_interval,
        'speaker': current_speaker,
    })
    
    console.print(f"  [green]✓ Found {len(segments)} speaker segments[/green]")
    for seg in segments[:5]:
        console.print(f"    {seg['start']:.1f}s - {seg['end']:.1f}s: {seg['speaker']}")
    if len(segments) > 5:
        console.print(f"    ... and {len(segments) - 5} more")
    
    return segments

def extract_base_video(start: float, end: float, output: Path) -> Path:
    """Extract and crop video using v13's working method"""
    console.print("  [dim]→ Extracting with center crop...[/dim]")
    
    duration = end - start
    raw_path = TEMP_DIR / "clip1_v14_raw.mp4"
    
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

def extract_pip_faces(start: float, end: float) -> Dict[str, Path]:
    """
    Extract reference face images for PIP overlays.
    Returns dict with 'left' and 'right' face image paths.
    """
    console.print("  [dim]→ Extracting reference faces for PIP...[/dim]")
    
    faces = {}
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS)
    detector = FaceDetector()
    
    # Sample through clip to find good frames for each speaker
    current_time = start
    left_face_path = TEMP_DIR / "pip_left.png"
    right_face_path = TEMP_DIR / "pip_right.png"
    
    found_left = False
    found_right = False
    
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    
    while current_time < end and not (found_left and found_right):
        ret, frame = cap.read()
        if not ret:
            break
        
        face_info = detector.detect_faces(frame)
        speaker = detector.identify_speaker(frame)
        
        if speaker and face_info:
            largest_face = max(face_info, key=lambda f: f['width'] * f['height'])
            
            # Extract face region with generous padding for PIP
            h, w = frame.shape[:2]
            pad = 0.7  # Extra padding for context
            
            x1 = max(0, largest_face['x'] - int(largest_face['width'] * pad))
            y1 = max(0, largest_face['y'] - int(largest_face['height'] * pad))
            x2 = min(w, largest_face['x'] + largest_face['width'] + int(largest_face['width'] * pad))
            y2 = min(h, largest_face['y'] + largest_face['height'] + int(largest_face['height'] * pad))
            
            face_crop = frame[y1:y2, x1:x2]
            # Make square
            size = max(face_crop.shape[:2])
            square = cv2.resize(face_crop, (size, size))
            
            if speaker == 'left' and not found_left:
                cv2.imwrite(str(left_face_path), square)
                found_left = True
                console.print(f"    Found LEFT speaker face at {current_time-start:.1f}s")
            elif speaker == 'right' and not found_right:
                cv2.imwrite(str(right_face_path), square)
                found_right = True
                console.print(f"    Found RIGHT speaker face at {current_time-start:.1f}s")
        
        # Skip frames
        for _ in range(int(fps * 0.5)):
            cap.read()
            current_time += 1 / fps
        current_time += 1 / fps
    
    cap.release()
    
    if found_left:
        faces['left'] = left_face_path
    if found_right:
        faces['right'] = right_face_path
    
    console.print(f"  [green]✓ Extracted {len(faces)} reference faces[/green]")
    return faces

def render_intelligent_pip(video_path: Path, segments: List[Dict], 
                          face_refs: Dict[str, Path], output_path: Path):
    """
    Apply PIP overlay based on speaker segments:
    - When LEFT speaks → PIP of RIGHT in TOP-RIGHT corner
    - When RIGHT speaks → PIP of LEFT in TOP-LEFT corner
    """
    console.print("  [dim]→ Applying intelligent PIP overlays...[/dim]")
    
    if 'left' not in face_refs and 'right' not in face_refs:
        console.print("  [yellow]No face refs, copying video...[/yellow]")
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
    # Build FFmpeg filter for PIP overlays based on segments
    inputs = ["-i", str(video_path)]
    
    # Add face reference images
    input_idx = 1
    face_input_map = {}
    if 'left' in face_refs:
        inputs.extend(["-i", str(face_refs['left'])])
        face_input_map['left'] = input_idx
        input_idx += 1
    if 'right' in face_refs:
        inputs.extend(["-i", str(face_refs['right'])])
        face_input_map['right'] = input_idx
    
    filter_parts = []
    
    # Scale face references to PIP size with rounded corners
    for speaker, idx in face_input_map.items():
        filter_parts.append(f"[{idx}:v]scale={PIP_SIZE}:{PIP_SIZE}[pip_{speaker}]")
    
    # Start with video
    last_out = "[0:v]"
    overlay_idx = 0
    
    for seg in segments:
        active_speaker = seg['speaker']
        # PIP shows the OTHER speaker
        pip_speaker = 'right' if active_speaker == 'left' else 'left'
        
        if pip_speaker not in face_input_map:
            continue
        
        # Position: opposite corner from speaker
        # LEFT speaking → PIP in TOP-RIGHT (x = OUT_W - PIP_SIZE - padding)
        # RIGHT speaking → PIP in TOP-LEFT (x = padding)
        if active_speaker == 'left':
            pip_x = OUT_W - PIP_SIZE - PIP_PADDING
        else:
            pip_x = PIP_PADDING
        
        enable = f"between(t,{seg['start']},{seg['end']})"
        
        filter_parts.append(
            f"{last_out}[pip_{pip_speaker}]overlay=x={pip_x}:y={PIP_Y}:"
            f"enable='{enable}'[v{overlay_idx}]"
        )
        last_out = f"[v{overlay_idx}]"
        overlay_idx += 1
    
    if overlay_idx == 0:
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    
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
        console.print(f"[red]PIP overlay failed: {result.stderr.decode()[:500]}[/red]")
        subprocess.run(["cp", str(video_path), str(output_path)])
    else:
        console.print(f"  [green]✓ Applied PIP for {len(segments)} segments[/green]")

# === Caption and Emoji functions from v13 ===

def get_words_with_emojis(transcript: Dict, start: float, end: float) -> List[Dict]:
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
            'line1': line1, 'line2': line2,
            'start': chunk[0]['start'], 'end': chunk[-1]['end'],
            'words': chunk, 'idx': caption_idx,
        })
        caption_idx += 1
        i += chunk_size
    return captions

def schedule_emojis(words: List[Dict], captions: List[Dict]) -> List[Dict]:
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
        caption_start, caption_end = caption_times.get(id(w), (word['start'], word['end']))
        emoji_start = max(word['start'], last_emoji_end + EMOJI_GAP)
        emoji_end = min(emoji_start + EMOJI_DURATION, caption_end)
        if emoji_end - emoji_start < 0.5:
            continue
        scheduled.append({
            'file': word['emoji']['file'],
            'start': emoji_start, 'end': emoji_end,
            'trigger': trigger,
        })
        last_trigger_time[trigger] = word['start']
        last_emoji_end = emoji_end
    return scheduled

def generate_balanced_ass(captions: List[Dict], output_path: Path) -> Path:
    header = f"""[Script Info]
Title: Viral Clip v14
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
    return output_path

def render_scheduled_emojis(video_path: Path, scheduled: List[Dict], output_path: Path):
    if not scheduled:
        subprocess.run(["cp", str(video_path), str(output_path)])
        return
    emoji_x = (OUT_W - EMOJI_SIZE) // 2
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
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", last_out, "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        subprocess.run(["cp", str(video_path), str(output_path)])

def burn_captions(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy", str(output_path)
    ], capture_output=True, check=True)
    return output_path

def build_clip1_v14():
    """Build Clip 1 v14 with intelligent PIP"""
    console.print(Panel.fit(
        "[bold magenta]🎬 Building Clip 1 v14[/bold magenta]\n"
        "• Face detection for speaker ID\n"
        "• Intelligent PIP placement\n"
        "• LEFT speaker → PIP top-RIGHT\n"
        "• RIGHT speaker → PIP top-LEFT\n"
        "• All v13 caption/emoji features",
        title="Intelligent Dual-Face"
    ))
    
    START, END = 3938.0, 3984.0
    
    # 1. Analyze speaker segments
    console.print("\n[bold]Step 1: Analyze speakers[/bold]")
    segments = analyze_speaker_segments(VIDEO_PATH, START, END)
    
    # 2. Extract reference faces
    console.print("\n[bold]Step 2: Extract reference faces[/bold]")
    face_refs = extract_pip_faces(START, END)
    
    # 3. Extract base video
    console.print("\n[bold]Step 3: Extract base video[/bold]")
    base_clip = TEMP_DIR / "clip1_v14_base.mp4"
    extract_base_video(START, END, base_clip)
    
    # 4. Apply intelligent PIP
    console.print("\n[bold]Step 4: Apply intelligent PIP[/bold]")
    pip_clip = TEMP_DIR / "clip1_v14_pip.mp4"
    render_intelligent_pip(base_clip, segments, face_refs, pip_clip)
    
    # 5. Words and captions
    console.print("\n[bold]Step 5: Prepare captions[/bold]")
    transcript = load_transcript()
    words = get_words_with_emojis(transcript, START, END)
    captions = get_balanced_captions(words)
    scheduled = schedule_emojis(words, captions)
    console.print(f"  [green]✓ {len(captions)} captions, {len(scheduled)} emojis[/green]")
    
    # 6. Apply emojis
    console.print("\n[bold]Step 6: Apply emojis[/bold]")
    emoji_clip = TEMP_DIR / "clip1_v14_emoji.mp4"
    render_scheduled_emojis(pip_clip, scheduled, emoji_clip)
    
    # 7. Burn captions
    console.print("\n[bold]Step 7: Burn captions[/bold]")
    ass_path = TEMP_DIR / "clip1_v14.ass"
    generate_balanced_ass(captions, ass_path)
    
    final_path = OUTPUT_DIR / "clip_1_purple_tricep_v14.mp4"
    burn_captions(emoji_clip, ass_path, final_path)
    
    console.print(Panel.fit(
        f"[bold green]✅ Complete![/bold green]\n"
        f"Output: [cyan]{final_path}[/cyan]",
        title="Intelligent PIP Success"
    ))

if __name__ == "__main__":
    build_clip1_v14()

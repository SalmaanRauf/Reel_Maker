"""
Alex Hormozi Style Captioner - Dynamic word-by-word captions
"""
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
import subprocess
from moviepy import VideoFileClip, CompositeVideoClip, TextClip
from rich.console import Console

from transcriber import Word, Transcript

console = Console()

CAPTION_STYLES = {
    "hormozi": {
        "font": "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
        "font_size": 80,
        "color": "white",
        "stroke_color": "black",
        "stroke_width": 4,
        "highlight_color": "#FFD700",
        "position": "center",
        "words_per_line": 3,
        "uppercase": True,
        "pop_scale": 1.15,
    }
}


@dataclass
class CaptionSegment:
    words: List[Word]
    text: str
    start_time: float
    end_time: float


def group_words_for_captions(words: List[Word], words_per_group: int = 3) -> List[CaptionSegment]:
    segments = []
    for i in range(0, len(words), words_per_group):
        group = words[i:i + words_per_group]
        if not group:
            continue
        text = " ".join(w.text for w in group)
        segments.append(CaptionSegment(
            words=group, text=text,
            start_time=group[0].start, end_time=group[-1].end
        ))
    return segments


import textwrap

def create_caption_clips(words: List[Word], video_size: Tuple[int, int], 
                         style_name: str = "hormozi", time_offset: float = 0.0) -> List:
    """
    Create caption clips using direct Image synthesis for perfect control.
    Avoids MoviePy's TextClip issues with font metrics/cropping.
    """
    from moviepy import ImageClip
    from PIL import Image, ImageDraw, ImageFont
    
    style = CAPTION_STYLES.get(style_name, CAPTION_STYLES["hormozi"])
    segments = group_words_for_captions(words, words_per_group=2) 
    clips = []
    
    # Load Font
    try:
        font = ImageFont.truetype(style["font"], style["font_size"])
        # Stroke font (slightly larger)
        stroke_width = style.get("stroke_width", 4)
    except Exception as e:
        console.print(f"[red]Font load error: {e}[/red]")
        return []

    W, H = video_size
    Y_POS = int(H * 0.75)  # Lower third
    MAX_TEXT_WIDTH = W - 200

    for seg in segments:
        text = seg.text.upper() if style.get("uppercase") else seg.text
        # Wrap text
        wrapped_lines = textwrap.wrap(text, width=15) # tight wrap
        
        # Calculate dimensions
        line_height = style["font_size"] * 1.2
        total_height = len(wrapped_lines) * line_height
        
        # Create transparent image
        img = Image.new('RGBA', (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        
        # Draw each line
        current_y = Y_POS - (total_height / 2)
        
        for line in wrapped_lines:
            # Measure line
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
            text_w = bbox[2] - bbox[0]
            x_pos = (W - text_w) / 2
            
            # Draw stroke (outline)
            draw.text((x_pos, current_y), line, font=font, fill=style["stroke_color"], 
                     stroke_width=stroke_width)
            # Draw fill
            draw.text((x_pos, current_y), line, font=font, fill=style["color"])
            
            current_y += line_height
            
        # Convert to Clip
        start = seg.start_time - time_offset
        duration = seg.end_time - seg.start_time
        if start < 0: duration += start; start = 0
        if duration <= 0: continue
        
        img_np = np.array(img)
        clip = ImageClip(img_np).with_duration(duration).with_start(start)
        clips.append(clip)
        
    return clips


def add_captions_to_video(video_path: Path, output_path: Path, words: List[Word],
                          time_offset: float = 0.0, style_name: str = "hormozi") -> Path:
    console.print(f"[cyan]Adding {style_name} style captions...[/cyan]")
    video = VideoFileClip(str(video_path))
    video_size = (video.w, video.h)
    
    caption_clips = create_caption_clips(words, video_size, style_name, time_offset)
    final = CompositeVideoClip([video] + caption_clips) if caption_clips else video
    
    console.print("[cyan]Rendering final video with captions...[/cyan]")
    final.write_videofile(str(output_path), codec='libx264', audio_codec='aac',
                          fps=video.fps, preset='fast', threads=4, logger=None)
    video.close()
    final.close()
    console.print(f"[green]✓ Captioned video saved to {output_path.name}[/green]")
    return output_path

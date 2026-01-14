"""
Caption Animator - Hormozi-style animated captions with ASS subtitles
Generates animated text overlays with pop effects, keyword highlights, and emoji support.
"""
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass

# Import Word from transcriber
import sys
sys.path.insert(0, str(Path(__file__).parent))
from transcriber import Word


@dataclass
class CaptionStyle:
    """Caption styling configuration"""
    font: str = "Arial Rounded MT Bold"
    size: int = 72
    primary_color: str = "&H00FFFFFF"    # White (AABBGGRR format)
    highlight_color: str = "&H0000D7FF"  # Gold 
    outline_color: str = "&H00000000"    # Black outline
    outline_width: int = 4
    shadow_depth: int = 2
    uppercase: bool = True
    animation: str = "pop"               # pop, slide, fade
    margin_v: int = 200                  # Vertical margin from bottom
    words_per_group: int = 3

# Preset styles
STYLES = {
    "hormozi": CaptionStyle(
        font="Arial Rounded MT Bold",
        size=72,
        primary_color="&H00FFFFFF",
        highlight_color="&H0000D7FF",  # Gold
        outline_width=4,
        uppercase=True,
        animation="pop"
    ),
    "minimal": CaptionStyle(
        font="Helvetica Neue",
        size=60,
        primary_color="&H00FFFFFF",
        highlight_color="&H0000FF00",  # Green
        outline_width=2,
        uppercase=False,
        animation="fade"
    ),
    "bold": CaptionStyle(
        font="Impact",
        size=80,
        primary_color="&H00FFFFFF",
        highlight_color="&H000000FF",  # Red
        outline_width=5,
        uppercase=True,
        animation="pop"
    )
}

# Default highlight keywords
DEFAULT_HIGHLIGHT_WORDS = [
    "secret", "truth", "never", "always", "money", "million", 
    "dollar", "free", "important", "critical", "key", "must",
    "stop", "wait", "listen", "warning", "danger", "amazing",
    "incredible", "insane", "crazy", "game-changer"
]


def format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format (H:MM:SS.CC)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    centiseconds = int((s % 1) * 100)
    s = int(s)
    return f"{h}:{m:02d}:{s:02d}.{centiseconds:02d}"


def group_words(words: List[Word], words_per_group: int = 3) -> List[Tuple[List[Word], str, float, float]]:
    """Group words into caption chunks"""
    groups = []
    for i in range(0, len(words), words_per_group):
        group = words[i:i + words_per_group]
        if not group:
            continue
        text = " ".join(w.text for w in group)
        start = group[0].start
        end = group[-1].end
        groups.append((group, text, start, end))
    return groups


def generate_pop_animation(duration_ms: int = 100) -> str:
    """
    Generate ASS animation tags for pop effect.
    Scale: 20% -> 120% -> 100%
    """
    phase1 = duration_ms // 2
    phase2 = duration_ms // 2
    return (
        r"{\fscx20\fscy20"
        rf"\t(0,{phase1},\fscx120\fscy120)"
        rf"\t({phase1},{phase1 + phase2},\fscx100\fscy100)}}"
    )


def generate_slide_animation(duration_ms: int = 150) -> str:
    """Generate ASS animation tags for slide-up effect"""
    return rf"{{\move(540,1200,540,1100,0,{duration_ms})}}"


def generate_fade_animation(duration_ms: int = 100) -> str:
    """Generate ASS animation tags for fade-in effect"""
    return rf"{{\fad({duration_ms},0)}}"


def get_animation_tags(style: CaptionStyle) -> str:
    """Get animation tags based on style"""
    if style.animation == "pop":
        return generate_pop_animation()
    elif style.animation == "slide":
        return generate_slide_animation()
    elif style.animation == "fade":
        return generate_fade_animation()
    return ""


def highlight_text(
    text: str, 
    primary_color: str,
    highlight_color: str,
    keywords: List[str]
) -> str:
    """Apply highlight color to keywords in text"""
    result = text
    for keyword in keywords:
        # Case-insensitive replacement
        import re
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        replacement = rf"{{\c{highlight_color}}}{keyword.upper()}{{\c{primary_color}}}"
        result = pattern.sub(replacement, result)
    return result


def generate_ass_subtitles(
    words: List[Word],
    output_path: Path,
    style_name: str = "hormozi",
    highlight_keywords: Optional[List[str]] = None,
    video_width: int = 1080,
    video_height: int = 1920,
    time_offset: float = 0.0
) -> Path:
    """
    Generate animated ASS subtitle file for FFmpeg burning.
    
    Args:
        words: List of Word objects with timestamps
        output_path: Where to save the .ass file
        style_name: Caption style preset name
        highlight_keywords: Words to highlight in gold
        video_width: Video width in pixels
        video_height: Video height in pixels
        time_offset: Offset to subtract from word timestamps
        
    Returns:
        Path to generated .ass file
    """
    style = STYLES.get(style_name, STYLES["hormozi"])
    keywords = highlight_keywords or DEFAULT_HIGHLIGHT_WORDS
    
    # ASS Header
    header = f"""[Script Info]
Title: Viral Clip Captions
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{style.font},{style.size},{style.primary_color},&H000000FF,{style.outline_color},&H80000000,1,0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow_depth},5,50,50,{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    events = []
    word_groups = group_words(words, style.words_per_group)
    
    for group_words_list, text, start, end in word_groups:
        # Apply time offset
        adj_start = max(0, start - time_offset)
        adj_end = max(0, end - time_offset)
        
        if adj_end <= adj_start:
            continue
        
        # Format text
        display_text = text.upper() if style.uppercase else text
        
        # Apply keyword highlights
        display_text = highlight_text(
            display_text, 
            style.primary_color, 
            style.highlight_color, 
            keywords
        )
        
        # Get animation tags
        anim = get_animation_tags(style)
        
        # Create dialogue line
        start_time = format_ass_time(adj_start)
        end_time = format_ass_time(adj_end)
        
        events.append(
            f"Dialogue: 0,{start_time},{end_time},Main,,0,0,0,,{anim}{display_text}"
        )
    
    # Write ASS file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write("\n".join(events))
    
    return output_path


def burn_subtitles_ffmpeg(
    video_path: Path,
    ass_path: Path,
    output_path: Path
) -> Path:
    """
    Burn ASS subtitles into video using FFmpeg.
    
    Args:
        video_path: Input video file
        ass_path: ASS subtitle file
        output_path: Output video with burned subtitles
        
    Returns:
        Path to output video
    """
    import subprocess
    
    # Escape path for FFmpeg filter
    ass_escaped = str(ass_path).replace(":", r"\:").replace("\\", "/")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle burn failed: {result.stderr}")
    
    return output_path


if __name__ == "__main__":
    # Test with sample words
    test_words = [
        Word(text="This", start=0.0, end=0.3),
        Word(text="is", start=0.3, end=0.5),
        Word(text="the", start=0.5, end=0.7),
        Word(text="secret", start=0.7, end=1.2),
        Word(text="to", start=1.2, end=1.4),
        Word(text="making", start=1.4, end=1.8),
        Word(text="money", start=1.8, end=2.3),
        Word(text="fast", start=2.3, end=2.8),
    ]
    
    output = Path("./temp/test_captions.ass")
    output.parent.mkdir(exist_ok=True)
    
    generate_ass_subtitles(test_words, output)
    print(f"Generated: {output}")
    print(open(output).read())

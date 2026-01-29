"""
Karaoke Caption Configuration
Reusable config for word-by-word highlight captions
"""
from pathlib import Path

# Output dimensions
OUT_W = 1080
OUT_H = 1920

# Caption Style
FONT_PATH = "/System/Library/Fonts/Supplemental/Impact.ttf"  # Bolder, more readable
FONT_SIZE = 80  # Bigger
LINE_HEIGHT = 95

# Position - Bottom third of screen (but not too low)
CAPTION_Y_LINE1 = 1550  # Primary caption line
CAPTION_Y_LINE2 = 1650  # Secondary line below

# Colors
TEXT_COLOR = "white"
OUTLINE_COLOR = "black"
HIGHLIGHT_BOX_COLOR = "0xE31C3D"  # Red
HIGHLIGHT_BOX_OPACITY = 0.95
BOX_PADDING = 14

# Timing
WORDS_PER_LINE = 4

# Word corrections for transcription errors
WORD_FIXES = {
    "lair": "Larry",
    "Lair": "Larry", 
    "viral": "vial",
    "larry": "Larry",
}

# Paths (will be set per-video)
class VideoConfig:
    def __init__(self, video_path: str, transcript_path: str, output_dir: str, temp_dir: str):
        self.video_path = Path(video_path)
        self.transcript_path = Path(transcript_path)
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)

# Default config for current video
DEFAULT_CONFIG = VideoConfig(
    video_path="/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4",
    transcript_path="/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp/Podcast w Dr Abud_transcript.json",
    output_dir="/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_clips",
    temp_dir="/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp"
)

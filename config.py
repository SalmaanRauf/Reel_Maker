"""
Viral Clip Generator - Configuration
"""
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List

# Paths
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp"

# Create directories
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)


class ClipConfig(BaseModel):
    """Configuration for clip generation"""
    # Video settings
    output_width: int = 1080
    output_height: int = 1920  # 9:16 aspect ratio
    fps: int = 30
    
    # Clip settings
    min_clip_duration: float = 15.0  # seconds
    max_clip_duration: float = 90.0  # seconds
    num_clips: int = 5  # number of clips to generate
    
    # Caption settings
    font_name: str = "Montserrat-ExtraBold"  
    font_size: int = 72
    font_color: str = "#FFFFFF"
    highlight_color: str = "#FFD700"  # Gold for emphasis
    stroke_color: str = "#000000"
    stroke_width: int = 4
    caption_position: str = "center"  # center, bottom
    words_per_caption: int = 3  # words to show at once
    
    # Processing
    whisper_model: str = "base"  # tiny, base, small, medium, large
    yolo_model: str = "yolov8n.pt"  # nano model for speed
    
    # Speaker tracking
    smoothing_window: int = 25  # Increased from 15 for smoother tracking
    crop_padding: float = 0.6  # Increased to 0.6 to zoom out significantly


class ViralityConfig(BaseModel):
    """Configuration for viral clip selection"""
    # Weights for scoring (0-1)
    hook_weight: float = 0.35  # Strong opening
    emotion_weight: float = 0.25  # Emotional content
    insight_weight: float = 0.25  # Valuable information
    controversy_weight: float = 0.15  # Debate potential
    
    # Requirements
    require_complete_thought: bool = True
    prefer_questions: bool = True  # Questions engage viewers


# Default configs
DEFAULT_CLIP_CONFIG = ClipConfig()
DEFAULT_VIRALITY_CONFIG = ViralityConfig()

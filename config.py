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
ASSETS_DIR = PROJECT_ROOT / "assets"

# Create directories
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    provider: str = "ollama"  # "ollama", "gemini", "claude"
    ollama_model: str = "llama3.1:8b"  # or gemma2:9b, mistral:7b
    ollama_url: str = "http://localhost:11434"


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


class CaptionConfig(BaseModel):
    """Caption animation settings"""
    style: str = "hormozi"  # hormozi, minimal, bold
    animation: str = "pop"  # pop, slide, fade
    uppercase: bool = True
    highlight_keywords: List[str] = [
        "secret", "money", "truth", "never", "always",
        "million", "important", "key", "stop", "warning"
    ]


class BRollConfig(BaseModel):
    """B-roll automation settings"""
    enabled: bool = True
    pexels_api_key: str = ""  # Free API key from pexels.com/api
    max_duration: float = 5.0
    cache_dir: str = "assets/broll_cache"


class SFXConfig(BaseModel):
    """Sound effects settings"""
    enabled: bool = True
    volume: float = 0.5  # SFX volume level
    trigger_keywords: List[str] = ["boom", "money", "secret", "stop", "warning"]
    sfx_dir: str = "assets/sfx"


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
DEFAULT_LLM_CONFIG = LLMConfig()
DEFAULT_CLIP_CONFIG = ClipConfig()
DEFAULT_CAPTION_CONFIG = CaptionConfig()
DEFAULT_BROLL_CONFIG = BRollConfig()
DEFAULT_SFX_CONFIG = SFXConfig()
DEFAULT_VIRALITY_CONFIG = ViralityConfig()


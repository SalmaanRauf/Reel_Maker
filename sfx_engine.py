"""
SFX Engine - Keyword-triggered sound effect insertion
Auto-inserts sound effects based on transcript keywords.
"""
import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from rich.console import Console

console = Console()

# Default SFX directory
SFX_DIR = Path(__file__).parent / "assets" / "sfx"


@dataclass
class SFXTrigger:
    """A sound effect trigger point"""
    timestamp: float      # When to insert (seconds)
    sfx_file: Path       # Path to sound file
    volume: float = 0.7  # Volume level (0-1)
    keyword: str = ""    # What triggered it


# Keyword to SFX mappings
# Maps transcript keywords to sound effect filenames
SFX_MAPPINGS = {
    # Impact words
    "boom": "boom.wav",
    "bang": "boom.wav",
    "explosion": "boom.wav",
    
    # Money words
    "money": "cash_register.wav",
    "dollar": "cash_register.wav",
    "million": "cash_register.wav",
    "rich": "cash_register.wav",
    "profit": "cash_register.wav",
    
    # Mystery/Secret
    "secret": "whoosh.wav",
    "truth": "whoosh.wav",
    "reveal": "whoosh.wav",
    "hidden": "whoosh.wav",
    
    # Warning
    "warning": "alert.wav",
    "danger": "alert.wav",
    "stop": "record_scratch.wav",
    "wait": "record_scratch.wav",
    
    # Success
    "success": "success_chime.wav",
    "win": "success_chime.wav",
    "victory": "success_chime.wav",
    "amazing": "success_chime.wav",
    
    # Dramatic
    "dramatic": "dramatic_hit.wav",
    "shocking": "dramatic_hit.wav",
    "insane": "dramatic_hit.wav",
    "crazy": "dramatic_hit.wav",
}

# Default SFX files to create if missing
DEFAULT_SFX_SPECS = {
    "whoosh.wav": "A quick swoosh/whoosh transition sound",
    "boom.wav": "Deep bass impact hit",
    "cash_register.wav": "Classic cash register cha-ching",
    "alert.wav": "Short alert/notification ding",
    "record_scratch.wav": "Vinyl record scratch sound",
    "success_chime.wav": "Positive success chime",
    "dramatic_hit.wav": "Dramatic orchestral hit/stinger",
}


def find_sfx_triggers(
    words: List,  # List of Word objects
    sfx_mappings: Dict[str, str] = None
) -> List[SFXTrigger]:
    """
    Find timestamps where SFX should be inserted based on keywords.
    
    Args:
        words: List of Word objects with text and timestamps
        sfx_mappings: Custom keyword->sfx file mappings
        
    Returns:
        List of SFXTrigger objects
    """
    mappings = sfx_mappings or SFX_MAPPINGS
    triggers = []
    
    for word in words:
        word_lower = word.text.lower().strip('.,!?;:')
        
        if word_lower in mappings:
            sfx_file = SFX_DIR / mappings[word_lower]
            
            triggers.append(SFXTrigger(
                timestamp=word.start,
                sfx_file=sfx_file,
                volume=0.5,  # Keep SFX subtle
                keyword=word_lower
            ))
    
    return triggers


def generate_ffmpeg_audio_mix(
    base_audio: Path,
    triggers: List[SFXTrigger],
    output_path: Path,
    base_volume: float = 1.0
) -> str:
    """
    Generate FFmpeg command to mix SFX with base audio.
    
    Args:
        base_audio: Path to base audio file
        triggers: List of SFX triggers
        output_path: Output audio file path
        base_volume: Volume for base audio (for ducking)
        
    Returns:
        FFmpeg command string
    """
    if not triggers:
        # No SFX to add, just copy
        return f'ffmpeg -y -i "{base_audio}" -c:a copy "{output_path}"'
    
    # Build input list
    inputs = [f'-i "{base_audio}"']
    
    # Filter for valid SFX files
    valid_triggers = [t for t in triggers if t.sfx_file.exists()]
    
    if not valid_triggers:
        return f'ffmpeg -y -i "{base_audio}" -c:a copy "{output_path}"'
    
    for trigger in valid_triggers:
        inputs.append(f'-i "{trigger.sfx_file}"')
    
    # Build filter complex
    filters = []
    
    # Process each SFX: delay + volume
    for i, trigger in enumerate(valid_triggers):
        delay_ms = int(trigger.timestamp * 1000)
        vol = trigger.volume
        filters.append(f"[{i+1}]adelay={delay_ms}|{delay_ms},volume={vol}[sfx{i}]")
    
    # Mix all together
    sfx_inputs = "".join(f"[sfx{i}]" for i in range(len(valid_triggers)))
    n_inputs = len(valid_triggers) + 1
    filters.append(f"[0]{sfx_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=0[out]")
    
    filter_str = ";".join(filters)
    
    cmd = f'ffmpeg -y {" ".join(inputs)} -filter_complex "{filter_str}" -map "[out]" "{output_path}"'
    
    return cmd


def mix_sfx_into_audio(
    base_audio: Path,
    triggers: List[SFXTrigger],
    output_path: Path
) -> bool:
    """
    Mix SFX into audio file.
    
    Args:
        base_audio: Path to base audio
        triggers: List of SFX triggers
        output_path: Output path
        
    Returns:
        True if successful
    """
    cmd = generate_ffmpeg_audio_mix(base_audio, triggers, output_path)
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]SFX mix failed: {result.stderr}[/red]")
            return False
        return True
    except Exception as e:
        console.print(f"[red]SFX mix error: {e}[/red]")
        return False


class SFXEngine:
    """
    Engine for managing and applying sound effects.
    
    Usage:
        engine = SFXEngine()
        triggers = engine.find_triggers(words)
        engine.apply_to_video(video_path, triggers, output_path)
    """
    
    def __init__(self, sfx_dir: Path = SFX_DIR):
        self.sfx_dir = sfx_dir
        self.sfx_dir.mkdir(parents=True, exist_ok=True)
        self._check_sfx_files()
    
    def _check_sfx_files(self):
        """Check if SFX files exist and warn if missing"""
        missing = []
        for sfx_name in set(SFX_MAPPINGS.values()):
            sfx_path = self.sfx_dir / sfx_name
            if not sfx_path.exists():
                missing.append(sfx_name)
        
        if missing:
            console.print(f"[yellow]Missing SFX files: {', '.join(missing)}[/yellow]")
            console.print(f"[dim]Add them to: {self.sfx_dir}[/dim]")
    
    def find_triggers(self, words: List) -> List[SFXTrigger]:
        """Find SFX trigger points in words"""
        return find_sfx_triggers(words, SFX_MAPPINGS)
    
    def apply_to_audio(
        self, 
        audio_path: Path, 
        triggers: List[SFXTrigger],
        output_path: Path
    ) -> Path:
        """Apply SFX to audio file"""
        if mix_sfx_into_audio(audio_path, triggers, output_path):
            return output_path
        return audio_path  # Return original if failed
    
    def list_available_sfx(self) -> List[str]:
        """List all available SFX files"""
        if not self.sfx_dir.exists():
            return []
        return [f.name for f in self.sfx_dir.glob("*.wav")]
    
    def add_custom_mapping(self, keyword: str, sfx_file: str):
        """Add a custom keyword -> SFX mapping"""
        SFX_MAPPINGS[keyword.lower()] = sfx_file


if __name__ == "__main__":
    from transcriber import Word
    
    # Test
    test_words = [
        Word(text="Here's", start=0.0, end=0.3),
        Word(text="the", start=0.3, end=0.5),
        Word(text="secret", start=0.5, end=1.0),
        Word(text="to", start=1.0, end=1.2),
        Word(text="making", start=1.2, end=1.6),
        Word(text="money", start=1.6, end=2.1),
    ]
    
    engine = SFXEngine()
    triggers = engine.find_triggers(test_words)
    
    print(f"Found {len(triggers)} SFX triggers:")
    for t in triggers:
        print(f"  {t.timestamp:.1f}s - {t.keyword} -> {t.sfx_file.name}")
    
    print(f"\nAvailable SFX: {engine.list_available_sfx()}")

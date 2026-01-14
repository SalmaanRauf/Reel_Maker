"""
Transcriber Module - Audio extraction and Whisper transcription
"""
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import whisper
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class Word:
    """A single transcribed word with timing"""
    text: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass 
class Segment:
    """A segment of transcription (usually a sentence)"""
    id: int
    text: str
    start: float
    end: float
    words: List[Word]


@dataclass
class Transcript:
    """Full transcript with word-level timestamps"""
    segments: List[Segment]
    language: str
    duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "segments": [
                {
                    "id": s.id,
                    "text": s.text,
                    "start": s.start,
                    "end": s.end,
                    "words": [asdict(w) for w in s.words]
                }
                for s in self.segments
            ],
            "language": self.language,
            "duration": self.duration
        }
    
    def save(self, path: Path):
        """Save transcript to JSON"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: Path) -> 'Transcript':
        """Load transcript from JSON"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        segments = []
        for seg_data in data["segments"]:
            words = [Word(**w) for w in seg_data.get("words", [])]
            segments.append(Segment(
                id=seg_data["id"],
                text=seg_data["text"],
                start=seg_data["start"],
                end=seg_data["end"],
                words=words
            ))
        
        return cls(
            segments=segments,
            language=data["language"],
            duration=data["duration"]
        )
    
    def get_text_in_range(self, start: float, end: float) -> str:
        """Get all text within a time range"""
        texts = []
        for seg in self.segments:
            if seg.start >= start and seg.end <= end:
                texts.append(seg.text)
            elif seg.start < end and seg.end > start:
                # Partial overlap
                texts.append(seg.text)
        return " ".join(texts)
    
    def get_words_in_range(self, start: float, end: float) -> List[Word]:
        """Get all words within a time range"""
        words = []
        for seg in self.segments:
            for word in seg.words:
                if word.start >= start and word.end <= end:
                    words.append(word)
        return words


def extract_audio(video_path: Path, output_path: Path) -> Path:
    """Extract audio from video file using ffmpeg"""
    console.print(f"[cyan]Extracting audio from {video_path.name}...[/cyan]")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # WAV format
        "-ar", "16000",  # 16kHz for Whisper
        "-ac", "1",  # Mono
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    console.print(f"[green]✓ Audio extracted to {output_path.name}[/green]")
    return output_path


def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    language: Optional[str] = None
) -> Transcript:
    """
    Transcribe audio using OpenAI Whisper with word-level timestamps.
    
    Args:
        audio_path: Path to audio file (WAV recommended)
        model_name: Whisper model size (tiny, base, small, medium, large)
        language: Optional language code (e.g., 'en', 'es')
    
    Returns:
        Transcript object with word-level timestamps
    """
    console.print(f"[cyan]Loading Whisper model '{model_name}'...[/cyan]")
    model = whisper.load_model(model_name)
    
    console.print("[cyan]Transcribing audio (this may take a while)...[/cyan]")
    
    # Transcribe with word timestamps
    result = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        verbose=False
    )
    
    # Parse results into our data structure
    segments = []
    for i, seg in enumerate(result["segments"]):
        words = []
        if "words" in seg:
            for w in seg["words"]:
                words.append(Word(
                    text=w["word"].strip(),
                    start=w["start"],
                    end=w["end"],
                    confidence=w.get("probability", 1.0)
                ))
        
        segments.append(Segment(
            id=i,
            text=seg["text"].strip(),
            start=seg["start"],
            end=seg["end"],
            words=words
        ))
    
    # Calculate duration from last segment
    duration = segments[-1].end if segments else 0.0
    
    transcript = Transcript(
        segments=segments,
        language=result.get("language", "en"),
        duration=duration
    )
    
    console.print(f"[green]✓ Transcription complete! {len(segments)} segments, {duration:.1f}s duration[/green]")
    
    return transcript


def transcribe_video(
    video_path: Path,
    output_dir: Path,
    model_name: str = "base",
    language: Optional[str] = None
) -> Transcript:
    """
    Full pipeline: extract audio from video and transcribe.
    
    Args:
        video_path: Path to video file
        output_dir: Directory to save intermediate and final files
        model_name: Whisper model size
        language: Optional language code
    
    Returns:
        Transcript object
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract audio
    audio_path = output_dir / f"{video_path.stem}_audio.wav"
    extract_audio(video_path, audio_path)
    
    # Transcribe
    transcript = transcribe_audio(audio_path, model_name, language)
    
    # Save transcript
    transcript_path = output_dir / f"{video_path.stem}_transcript.json"
    transcript.save(transcript_path)
    console.print(f"[green]✓ Transcript saved to {transcript_path.name}[/green]")
    
    return transcript


if __name__ == "__main__":
    # Test with sample
    import sys
    if len(sys.argv) > 1:
        video = Path(sys.argv[1])
        transcript = transcribe_video(video, Path("./temp"))
        print(f"\nFirst 3 segments:")
        for seg in transcript.segments[:3]:
            print(f"  [{seg.start:.1f}s - {seg.end:.1f}s]: {seg.text}")

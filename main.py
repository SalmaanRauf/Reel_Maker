#!/usr/bin/env python3
"""
Viral Clip Generator - Main Orchestrator
Transforms long-form podcasts into viral-ready short clips.

Usage:
    python main.py --input video.mp4 --topic "health tips" --clips 5
"""
import argparse
from pathlib import Path
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress

from config import OUTPUT_DIR, TEMP_DIR, DEFAULT_CLIP_CONFIG
from transcriber import transcribe_video, Transcript
from analyzer import analyze_transcript, AnalysisResult
from cropper import generate_crop_trajectory, apply_smart_crop
from captioner import add_captions_to_video

console = Console()


def process_video(
    input_path: Path,
    topic: str,
    num_clips: int = 5,
    output_dir: Path = OUTPUT_DIR,
    llm_provider: str = "claude",
    api_key: str = None
) -> list:
    """
    Main pipeline: Transcribe -> Analyze -> Crop -> Caption
    
    Args:
        input_path: Path to input video
        topic: Topic to extract clips about
        num_clips: Number of clips to generate
        output_dir: Where to save output clips
        llm_provider: LLM to use for analysis
        api_key: API key for LLM
    
    Returns:
        List of paths to generated clips
    """
    console.print(Panel.fit(
        f"[bold cyan]🎬 Viral Clip Generator[/bold cyan]\n"
        f"Input: {input_path.name}\n"
        f"Topic: {topic}\n"
        f"Clips: {num_clips}",
        title="Starting Pipeline"
    ))
    
    output_dir.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Transcription
    console.print("\n[bold]📝 Step 1: Transcription[/bold]")
    transcript_path = TEMP_DIR / f"{input_path.stem}_transcript.json"
    
    if transcript_path.exists():
        console.print(f"[dim]Loading existing transcript...[/dim]")
        transcript = Transcript.load(transcript_path)
    else:
        transcript = transcribe_video(
            input_path, TEMP_DIR,
            model_name=DEFAULT_CLIP_CONFIG.whisper_model
        )
    
    # Step 2: Viral Analysis
    console.print("\n[bold]🧠 Step 2: AI Viral Analysis[/bold]")
    analysis_path = TEMP_DIR / f"{input_path.stem}_analysis.json"
    
    analysis = analyze_transcript(
        transcript=transcript,
        topic=topic,
        num_clips=num_clips,
        llm_provider=llm_provider,
        api_key=api_key
    )
    analysis.save(analysis_path)
    
    # Step 3 & 4: Process each clip
    console.print("\n[bold]✂️ Step 3-4: Cropping & Captioning[/bold]")
    
    generated_clips = []
    
    for i, clip in enumerate(analysis.clips, 1):
        console.print(f"\n[cyan]Processing clip {i}/{len(analysis.clips)}: {clip.title}[/cyan]")
        
        # Generate smart crop trajectory
        trajectory = generate_crop_trajectory(
            input_path,
            clip.start_time,
            clip.end_time,
            output_width=DEFAULT_CLIP_CONFIG.output_width,
            output_height=DEFAULT_CLIP_CONFIG.output_height
        )
        
        # Crop video
        cropped_path = TEMP_DIR / f"clip_{i}_cropped.mp4"
        apply_smart_crop(
            input_path, cropped_path,
            clip.start_time, clip.end_time,
            trajectory,
            DEFAULT_CLIP_CONFIG.output_width,
            DEFAULT_CLIP_CONFIG.output_height
        )
        
        # Get words for this time range
        words = transcript.get_words_in_range(clip.start_time, clip.end_time)
        
        # Add captions
        safe_title = "".join(c if c.isalnum() else "_" for c in clip.title)[:30]
        final_path = output_dir / f"clip_{i}_{safe_title}.mp4"
        
        add_captions_to_video(
            cropped_path, final_path,
            words=words,
            time_offset=clip.start_time,
            style_name="hormozi"
        )
        
        generated_clips.append(final_path)
        console.print(f"[green]✓ Clip {i} complete: {final_path.name}[/green]")
    
    # Summary
    console.print(Panel.fit(
        f"[bold green]🎉 Generation Complete![/bold green]\n"
        f"Generated {len(generated_clips)} clips in:\n"
        f"{output_dir}",
        title="Success"
    ))
    
    return generated_clips


def main():
    parser = argparse.ArgumentParser(description="Generate viral clips from podcasts")
    parser.add_argument("--input", "-i", required=True, help="Input video file")
    parser.add_argument("--topic", "-t", required=True, help="Topic to extract clips about")
    parser.add_argument("--clips", "-n", type=int, default=5, help="Number of clips")
    parser.add_argument("--output", "-o", default=None, help="Output directory")
    parser.add_argument("--llm", default="claude", choices=["claude", "gemini"])
    parser.add_argument("--api-key", default=None, help="LLM API key")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]Error: Input file not found: {input_path}[/red]")
        sys.exit(1)
    
    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    process_video(
        input_path=input_path,
        topic=args.topic,
        num_clips=args.clips,
        output_dir=output_dir,
        llm_provider=args.llm,
        api_key=api_key
    )


if __name__ == "__main__":
    main()

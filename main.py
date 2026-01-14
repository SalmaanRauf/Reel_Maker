#!/usr/bin/env python3
"""
Reel Maker - Viral Clip Generator
Transforms long-form podcasts into viral-ready short clips.

Features:
- Free local LLM (Ollama) for clip selection
- Animated Hormozi-style captions
- Auto B-roll from Pexels
- Sound effects insertion
- Smart 9:16 cropping

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
from caption_animator import generate_ass_subtitles, STYLES
from fast_renderer import render_full_clip, RenderConfig
from sfx_engine import SFXEngine
from broll_engine import BRollEngine, PEXELS_API_KEY

console = Console()


def process_video(
    input_path: Path,
    topic: str,
    num_clips: int = 5,
    output_dir: Path = OUTPUT_DIR,
    llm_provider: str = "ollama",
    api_key: str = None,
    enable_broll: bool = True,
    enable_sfx: bool = True,
) -> list:
    """
    Full pipeline: Transcribe -> Analyze -> Crop -> Animate -> Render
    
    Args:
        input_path: Path to input video
        topic: Topic to extract clips about
        num_clips: Number of clips to generate
        output_dir: Where to save output clips
        llm_provider: LLM to use for analysis
        api_key: API key for LLM (not needed for Ollama)
        enable_broll: Enable auto B-roll insertion
        enable_sfx: Enable sound effects
    
    Returns:
        List of paths to generated clips
    """
    console.print(Panel.fit(
        f"[bold cyan]🎬 Reel Maker - Viral Clip Generator[/bold cyan]\n"
        f"Input: {input_path.name}\n"
        f"Topic: {topic}\n"
        f"Clips: {num_clips}\n"
        f"LLM: {llm_provider}",
        title="Starting Pipeline"
    ))
    
    output_dir.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize engines
    sfx_engine = SFXEngine() if enable_sfx else None
    broll_engine = BRollEngine() if enable_broll and PEXELS_API_KEY else None
    
    if broll_engine:
        console.print("[green]✓ B-roll enabled (Pexels API)[/green]")
    else:
        console.print("[dim]B-roll disabled (no PEXELS_KEY)[/dim]")
    
    if sfx_engine:
        sfx_files = sfx_engine.list_available_sfx()
        console.print(f"[green]✓ SFX enabled ({len(sfx_files)} sounds)[/green]")
    
    # ═══════════════════════════════════════════════════════════════════
    # Step 1: Transcription
    # ═══════════════════════════════════════════════════════════════════
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
    
    console.print(f"[green]✓ {len(transcript.segments)} segments, {transcript.duration:.0f}s duration[/green]")
    
    # ═══════════════════════════════════════════════════════════════════
    # Step 2: Viral Analysis
    # ═══════════════════════════════════════════════════════════════════
    console.print("\n[bold]🧠 Step 2: AI Viral Analysis[/bold]")
    console.print(f"[dim]Using {llm_provider} for clip selection...[/dim]")
    
    analysis = analyze_transcript(
        transcript=transcript,
        topic=topic,
        num_clips=num_clips,
        llm_provider=llm_provider,
        api_key=api_key
    )
    analysis.save(TEMP_DIR / f"{input_path.stem}_analysis.json")
    
    # ═══════════════════════════════════════════════════════════════════
    # Step 3: Process each clip
    # ═══════════════════════════════════════════════════════════════════
    console.print(f"\n[bold]✂️ Step 3: Processing {len(analysis.clips)} Clips[/bold]")
    
    generated_clips = []
    render_config = RenderConfig(
        output_width=DEFAULT_CLIP_CONFIG.output_width,
        output_height=DEFAULT_CLIP_CONFIG.output_height,
    )
    
    for i, clip in enumerate(analysis.clips, 1):
        console.print(f"\n[cyan]━━━ Clip {i}/{len(analysis.clips)}: {clip.title} ━━━[/cyan]")
        console.print(f"[dim]  Time: {clip.start_time:.1f}s - {clip.end_time:.1f}s ({clip.end_time - clip.start_time:.1f}s)[/dim]")
        console.print(f"[dim]  Score: {clip.virality_score:.0f}/100[/dim]")
        
        # Get words for this clip
        words = transcript.get_words_in_range(clip.start_time, clip.end_time)
        
        # ─────────────────────────────────────────────────────────────────
        # 3a. Generate crop trajectory
        # ─────────────────────────────────────────────────────────────────
        console.print("  [dim]→ Analyzing faces for smart crop...[/dim]")
        trajectory = generate_crop_trajectory(
            input_path,
            clip.start_time,
            clip.end_time,
            output_width=DEFAULT_CLIP_CONFIG.output_width,
            output_height=DEFAULT_CLIP_CONFIG.output_height
        )
        
        # ─────────────────────────────────────────────────────────────────
        # 3b. Crop video
        # ─────────────────────────────────────────────────────────────────
        console.print("  [dim]→ Cropping to 9:16...[/dim]")
        cropped_path = TEMP_DIR / f"clip_{i}_cropped.mp4"
        apply_smart_crop(
            input_path, cropped_path,
            clip.start_time, clip.end_time,
            trajectory,
            DEFAULT_CLIP_CONFIG.output_width,
            DEFAULT_CLIP_CONFIG.output_height
        )
        
        # ─────────────────────────────────────────────────────────────────
        # 3c. Generate animated captions (ASS)
        # ─────────────────────────────────────────────────────────────────
        console.print("  [dim]→ Generating animated captions...[/dim]")
        ass_path = TEMP_DIR / f"clip_{i}_captions.ass"
        generate_ass_subtitles(
            words=words,
            output_path=ass_path,
            style_name="hormozi",
            video_width=DEFAULT_CLIP_CONFIG.output_width,
            video_height=DEFAULT_CLIP_CONFIG.output_height,
            time_offset=clip.start_time
        )
        
        # ─────────────────────────────────────────────────────────────────
        # 3d. Burn captions into video
        # ─────────────────────────────────────────────────────────────────
        console.print("  [dim]→ Rendering with captions...[/dim]")
        safe_title = "".join(c if c.isalnum() else "_" for c in clip.title)[:30]
        final_path = output_dir / f"clip_{i}_{safe_title}.mp4"
        
        # Use fast renderer
        from fast_renderer import burn_subtitles
        burn_subtitles(cropped_path, ass_path, final_path, render_config)
        
        generated_clips.append(final_path)
        console.print(f"  [green]✓ Saved: {final_path.name}[/green]")
    
    # ═══════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════
    console.print(Panel.fit(
        f"[bold green]🎉 Generation Complete![/bold green]\n"
        f"Generated {len(generated_clips)} clips in:\n"
        f"[cyan]{output_dir}[/cyan]",
        title="Success"
    ))
    
    # List clips
    for i, path in enumerate(generated_clips, 1):
        console.print(f"  {i}. [cyan]{path.name}[/cyan]")
    
    return generated_clips


def main():
    parser = argparse.ArgumentParser(
        description="Reel Maker - Generate viral clips from podcasts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py -i podcast.mp4 -t "fitness tips" -n 5
  python main.py -i interview.mp4 -t "AI future" --llm ollama
        """
    )
    parser.add_argument("--input", "-i", required=True, help="Input video file")
    parser.add_argument("--topic", "-t", required=True, help="Topic to extract clips about")
    parser.add_argument("--clips", "-n", type=int, default=5, help="Number of clips (default: 5)")
    parser.add_argument("--output", "-o", default=None, help="Output directory")
    parser.add_argument("--llm", default="ollama", choices=["ollama", "claude", "gemini"],
                        help="LLM provider (default: ollama for free local inference)")
    parser.add_argument("--api-key", default=None, help="LLM API key (not needed for ollama)")
    parser.add_argument("--no-broll", action="store_true", help="Disable B-roll insertion")
    parser.add_argument("--no-sfx", action="store_true", help="Disable sound effects")
    
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
        api_key=api_key,
        enable_broll=not args.no_broll,
        enable_sfx=not args.no_sfx,
    )


if __name__ == "__main__":
    main()

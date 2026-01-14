#!/usr/bin/env python3
"""
Process clips without LLM API - uses pre-defined clip data
"""
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from transcriber import Transcript
from cropper import generate_crop_trajectory, apply_smart_crop
from captioner import add_captions_to_video
from config import OUTPUT_DIR, TEMP_DIR, DEFAULT_CLIP_CONFIG

console = Console()

def process_clip(
    video_path: Path,
    transcript: Transcript,
    clip_data: dict,
    output_dir: Path
) -> Path:
    """Process a single clip"""
    clip_id = clip_data["clip_id"]
    start = clip_data["start_time"]
    end = clip_data["end_time"]
    title = clip_data["title"]
    
    console.print(f"\n[cyan]Processing Clip {clip_id}: {title}[/cyan]")
    console.print(f"  Time: {start/60:.1f}min - {end/60:.1f}min ({end-start:.0f}s)")
    
    # Step 1: Smart crop
    console.print("  [dim]Step 1: Analyzing for smart crop...[/dim]")
    trajectory = generate_crop_trajectory(
        video_path, start, end,
        output_width=DEFAULT_CLIP_CONFIG.output_width,
        output_height=DEFAULT_CLIP_CONFIG.output_height,
        sample_rate=10  # Faster processing
    )
    
    cropped_path = TEMP_DIR / f"clip_{clip_id}_cropped.mp4"
    apply_smart_crop(
        video_path, cropped_path,
        start, end, trajectory,
        DEFAULT_CLIP_CONFIG.output_width,
        DEFAULT_CLIP_CONFIG.output_height
    )
    
    # Step 2: Get words for captions
    console.print("  [dim]Step 2: Getting caption words...[/dim]")
    words = transcript.get_words_in_range(start, end)
    console.print(f"  [dim]Found {len(words)} words for captions[/dim]")
    
    # Step 3: Add captions
    console.print("  [dim]Step 3: Adding captions...[/dim]")
    safe_title = "".join(c if c.isalnum() else "_" for c in title)[:30]
    final_path = output_dir / f"clip_{clip_id}_{safe_title}.mp4"
    
    add_captions_to_video(
        cropped_path, final_path,
        words=words,
        time_offset=start,
        style_name="hormozi"
    )
    
    console.print(f"[green]✓ Clip {clip_id} complete: {final_path.name}[/green]")
    return final_path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--clips-json", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--output", default="./output")
    parser.add_argument("--only", type=int, help="Process only this clip number")
    args = parser.parse_args()
    
    video_path = Path(args.video)
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Load clips
    with open(args.clips_json) as f:
        clips = json.load(f)
    
    # Load transcript
    transcript = Transcript.load(Path(args.transcript))
    
    console.print(Panel.fit(
        f"[bold cyan]🎬 Processing {len(clips)} clips[/bold cyan]\n"
        f"Video: {video_path.name}",
        title="Viral Clip Generator"
    ))
    
    results = []
    for clip in clips:
        if args.only and clip["clip_id"] != args.only:
            continue
        result = process_clip(video_path, transcript, clip, output_dir)
        results.append(result)
    
    console.print(Panel.fit(
        f"[bold green]✓ Done! Generated {len(results)} clips[/bold green]",
        title="Complete"
    ))


if __name__ == "__main__":
    main()

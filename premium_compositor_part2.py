#!/usr/bin/env python3
"""
Premium VFX Clips - Part 2 (Clips 7-11)
"""
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoFileClip, ImageClip, CompositeVideoClip
import textwrap
from rich.console import Console

console = Console()

ASSET_DIR = Path("/Users/salmaanrauf/.gemini/antigravity/brain/863b4285-bb7c-4ecc-85c2-c5ebc7824d68")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_premium")
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")

OUT_W, OUT_H = 1080, 1920


def add_bold_caption(text: str, duration: float, start: float,
                     color: str = "yellow", position: str = "bottom") -> ImageClip:
    """Create bold caption overlay"""
    img = Image.new('RGBA', (OUT_W, OUT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 70)
    except:
        font = ImageFont.load_default()
    
    lines = textwrap.wrap(text, width=25)
    line_height = 80
    total_height = len(lines) * line_height
    
    if position == "bottom":
        y_start = OUT_H - total_height - 350
    elif position == "top":
        y_start = 150
    else:
        y_start = (OUT_H - total_height) // 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (OUT_W - text_w) // 2
        y = y_start + i * line_height
        
        for dx in [-3, -2, 0, 2, 3]:
            for dy in [-3, -2, 0, 2, 3]:
                draw.text((x + dx, y + dy), line, font=font, fill="black")
        
        fill_color = color if color != "yellow" else "#FFD700"
        draw.text((x, y), line, font=font, fill=fill_color)
    
    clip = ImageClip(np.array(img)).with_duration(duration).with_start(start)
    return clip


def crop_to_vertical(video):
    """Crop video to 9:16"""
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    return video.resized((OUT_W, OUT_H))


def build_clip_7_injection():
    """Clip 7: Where to Inject"""
    console.print("[cyan]Building Clip 7: Where to Inject[/cyan]")
    
    video = crop_to_vertical(VideoFileClip(str(VIDEO_PATH)).subclipped(4146.0, 4184.0))
    layers = [video]
    
    captions = [
        ("Where should you INJECT?", 0, 4, "white"),
        ("The CLOSER to the injury, the BETTER", 5, 10, "yellow"),
        ("Elbow injury? Inject near ELBOW", 12, 17, "white"),
        ("Avoid blood vessels and nerves", 18, 23, "yellow"),
        ("Get it in the FAT 💉", 25, 30, "white"),
    ]
    
    for text, start, end, color in captions:
        layers.append(add_bold_caption(text, end - start, start, color=color))
    
    layers.append(add_bold_caption("Stomach or Elbow? 🤔 Where to inject for FAST healing", 
                                   5.0, video.duration - 5, color="yellow"))
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_7_injection_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")


def build_clip_8_cancer():
    """Clip 8: Cancer Question"""
    console.print("[cyan]Building Clip 8: Cancer Question[/cyan]")
    
    video = crop_to_vertical(VideoFileClip(str(VIDEO_PATH)).subclipped(5073.0, 5110.0))
    layers = [video]
    
    captions = [
        ("Does BPC cause CANCER? 🦀", 0, 5, "white"),
        ("The only study on BPC and tumors...", 6, 11, "yellow"),
        ("Showed BPC DECREASED angiogenesis", 12, 17, "yellow"),
        ("It's a POORLY designed study", 18, 23, "white"),
        ("But it's NOT that deterministic", 25, 30, "yellow"),
    ]
    
    for text, start, end, color in captions:
        layers.append(add_bold_caption(text, end - start, start, color=color))
    
    layers.append(add_bold_caption("Does BPC-157 Feed Cancer? 🦀 (The Truth)", 
                                   5.0, video.duration - 5, color="yellow"))
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_8_cancer_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")


def build_clip_9_gateway():
    """Clip 9: Gateway Drug"""
    console.print("[cyan]Building Clip 9: Gateway Drug[/cyan]")
    
    video = crop_to_vertical(VideoFileClip(str(VIDEO_PATH)).subclipped(80.0, 110.0))
    layers = [video]
    
    captions = [
        ("BPC-157 is the GATEWAY DRUG", 0, 5, "yellow"),
        ("Like marijuana leads to heavy drugs...", 6, 11, "white"),
        ("BPC leads to ALL the peptides", 12, 17, "yellow"),
        ("Down the rabbit hole 🐰🕳️", 18, 25, "white"),
    ]
    
    for text, start, end, color in captions:
        layers.append(add_bold_caption(text, end - start, start, color=color))
    
    layers.append(add_bold_caption("Why BPC-157 is the 'Gateway Drug' of Biohacking 🚪💊", 
                                   5.0, video.duration - 5, color="yellow"))
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_9_gateway_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")


def build_clip_10_homeostasis():
    """Clip 10: It's Not Magic, It's Homeostasis"""
    console.print("[cyan]Building Clip 10: Homeostasis[/cyan]")
    
    video = crop_to_vertical(VideoFileClip(str(VIDEO_PATH)).subclipped(3918.0, 3945.0))
    layers = [video]
    
    captions = [
        ("BPC doesn't do MAGIC ✨", 0, 4, "white"),
        ("It brings you back to HOMEOSTASIS", 5, 10, "yellow"),
        ("FASTER than you would otherwise", 11, 16, "yellow"),
        ("Natural healing... ACCELERATED ⏩", 18, 23, "white"),
    ]
    
    for text, start, end, color in captions:
        layers.append(add_bold_caption(text, end - start, start, color=color))
    
    layers.append(add_bold_caption("It's not Magic 🪄 It's SPEED ⏩", 
                                   5.0, video.duration - 5, color="yellow"))
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_10_homeostasis_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")


def build_clip_11_magic_stack():
    """Clip 11: Magic Stack (BPC + HGH)"""
    console.print("[cyan]Building Clip 11: Magic Stack (BPC+HGH)[/cyan]")
    
    # Approximate timecode (42:64 = around 2564s)
    video = crop_to_vertical(VideoFileClip(str(VIDEO_PATH)).subclipped(4264.0, 4303.0))
    layers = [video]
    
    captions = [
        ("The SECRET STACK 🧬", 0, 4, "yellow"),
        ("BPC increases growth hormone RECEPTORS", 5, 10, "white"),
        ("On tendons and ligaments", 11, 15, "yellow"),
        ("Then you bring in the HGH", 16, 20, "white"),
        ("Athletes heal SO FAST 💪", 22, 27, "yellow"),
    ]
    
    for text, start, end, color in captions:
        layers.append(add_bold_caption(text, end - start, start, color=color))
    
    layers.append(add_bold_caption("The Athlete's Secret Stack: BPC + HGH 🧬⚡", 
                                   5.0, video.duration - 5, color="yellow"))
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_11_magic_stack_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")


def main():
    console.print("[bold magenta]🎬 Premium VFX Clips - Part 2[/bold magenta]")
    
    try: build_clip_7_injection()
    except Exception as e: console.print(f"[red]Clip 7 failed: {e}[/red]")
    
    try: build_clip_8_cancer()
    except Exception as e: console.print(f"[red]Clip 8 failed: {e}[/red]")
    
    try: build_clip_9_gateway()
    except Exception as e: console.print(f"[red]Clip 9 failed: {e}[/red]")
    
    try: build_clip_10_homeostasis()
    except Exception as e: console.print(f"[red]Clip 10 failed: {e}[/red]")
    
    try: build_clip_11_magic_stack()
    except Exception as e: console.print(f"[red]Clip 11 failed: {e}[/red]")
    
    console.print("[bold green]✓ Part 2 complete![/bold green]")


if __name__ == "__main__":
    main()

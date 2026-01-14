#!/usr/bin/env python3
"""
Premium VFX Video Compositor
Builds viral clips with image overlays, effects, and captions
"""
import json
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    VideoFileClip, ImageClip, CompositeVideoClip, 
    concatenate_videoclips, AudioFileClip
)
import cv2
from rich.console import Console
from rich.progress import track

console = Console()

# Asset paths
ASSET_DIR = Path("/Users/salmaanrauf/.gemini/antigravity/brain/863b4285-bb7c-4ecc-85c2-c5ebc7824d68")
OUTPUT_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/output_premium")
TEMP_DIR = Path("/Users/salmaanrauf/Documents/Other/viral_clip_generator/temp")
VIDEO_PATH = Path("/Users/salmaanrauf/Documents/Other/Podcast w Dr Abud.mp4")

OUTPUT_DIR.mkdir(exist_ok=True)

# Output dimensions (9:16 vertical)
OUT_W, OUT_H = 1080, 1920


def load_asset(name_pattern: str) -> Optional[Path]:
    """Find asset by partial name match"""
    matches = list(ASSET_DIR.glob(f"*{name_pattern}*.png"))
    return matches[0] if matches else None


def create_overlay_image(asset_path: Path, size: Tuple[int, int], 
                         position: str = "center", opacity: float = 0.9) -> ImageClip:
    """Create an overlay from an asset image, scaled and positioned"""
    img = Image.open(asset_path).convert("RGBA")
    
    # Scale to fit within bounds while maintaining aspect ratio
    target_w, target_h = size
    img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    
    # Create canvas at full video size
    canvas = Image.new('RGBA', (OUT_W, OUT_H), (0, 0, 0, 0))
    
    # Position the image
    x = (OUT_W - img.width) // 2
    if position == "center":
        y = (OUT_H - img.height) // 2
    elif position == "top":
        y = 100
    elif position == "bottom":
        y = OUT_H - img.height - 300
    else:
        y = (OUT_H - img.height) // 2
    
    canvas.paste(img, (x, y), img)
    
    # Apply opacity
    if opacity < 1.0:
        alpha = canvas.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        canvas.putalpha(alpha)
    
    return ImageClip(np.array(canvas))


def add_bold_caption(text: str, duration: float, start: float,
                     color: str = "yellow", position: str = "bottom") -> ImageClip:
    """Create bold caption overlay"""
    img = Image.new('RGBA', (OUT_W, OUT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", 70)
    except:
        font = ImageFont.load_default()
    
    # Wrap text
    import textwrap
    lines = textwrap.wrap(text, width=25)
    
    # Calculate position
    line_height = 80
    total_height = len(lines) * line_height
    
    if position == "bottom":
        y_start = OUT_H - total_height - 350
    elif position == "top":
        y_start = 150
    else:
        y_start = (OUT_H - total_height) // 2
    
    # Draw each line
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (OUT_W - text_w) // 2
        y = y_start + i * line_height
        
        # Draw stroke
        for dx in [-3, -2, 0, 2, 3]:
            for dy in [-3, -2, 0, 2, 3]:
                draw.text((x + dx, y + dy), line, font=font, fill="black")
        
        # Draw fill
        fill_color = color if color != "yellow" else "#FFD700"
        draw.text((x, y), line, font=font, fill=fill_color)
    
    clip = ImageClip(np.array(img)).with_duration(duration).with_start(start)
    return clip


def apply_grayscale_effect(clip: VideoFileClip) -> VideoFileClip:
    """Apply black and white effect to video"""
    def to_gray(frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    return clip.transform(to_gray)


def build_clip_1_purple_tricep():
    """Build Clip 1: Purple Tricep with Larry Wheels"""
    console.print("[cyan]Building Clip 1: Purple Tricep (Larry Wheels)[/cyan]")
    
    # Load base video segment
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(3938.0, 3977.0)
    
    # Smart crop to vertical (center)
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add warning overlay at start (0-2s)
    warning_asset = load_asset("warning_graphic")
    if warning_asset:
        warning = create_overlay_image(warning_asset, (800, 400), position="center")
        warning = warning.with_duration(2.0).with_start(0)
        layers.append(warning)
    
    # Add purple bruise overlay (5-10s) 
    bruise_asset = load_asset("purple_bruise")
    if bruise_asset:
        bruise = create_overlay_image(bruise_asset, (600, 600), position="center", opacity=0.7)
        bruise = bruise.with_duration(5.0).with_start(5.0)
        layers.append(bruise)
    
    # Add calendar flip (25-30s)
    calendar_asset = load_asset("calendar_week")
    if calendar_asset:
        calendar = create_overlay_image(calendar_asset, (700, 500), position="center")
        calendar = calendar.with_duration(5.0).with_start(25.0)
        layers.append(calendar)
    
    # Add captions
    captions = [
        ("I was lifting with LARRY WHEELS", 0, 4, "white"),
        ("My tricep... PURPLE from here to here", 5, 10, "yellow"),
        ("I put BPC RIGHT INTO THE TENDON", 12, 17, "white"),
        ("4 WEEKS LATER... WE'RE BACK", 25, 30, "yellow"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    # Final hook caption
    hook = add_bold_caption("My Arm was PURPLE 🟣 -> Healed in 4 Weeks", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    # Composite
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_1_purple_tricep_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def build_clip_2_rat_acl():
    """Build Clip 2: Rat ACL Experiment"""
    console.print("[cyan]Building Clip 2: Rat ACL Experiment[/cyan]")
    
    # Load video segment (timestamps from user brief: 38:25 - 38:34 = 2305s - 2314s)
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(2305.0, 2334.0)
    
    # Smart crop
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add torn rope overlay (5-10s)
    rope_torn = load_asset("torn_rope")
    if rope_torn:
        rope = create_overlay_image(rope_torn, (800, 600), position="center")
        rope = rope.with_duration(5.0).with_start(5.0)
        layers.append(rope)
    
    # Add healing rope (15-20s)
    rope_heal = load_asset("rope_healing")
    if rope_heal:
        heal = create_overlay_image(rope_heal, (800, 600), position="center")
        heal = heal.with_duration(5.0).with_start(15.0)
        layers.append(heal)
    
    # Captions
    captions = [
        ("They BLEW OUT the ACL of these rats", 0, 5, "white"),
        ("Injected BPC-157...", 6, 10, "yellow"),
        ("100% REGROWTH", 15, 20, "yellow"),
        ("The ligament GREW BACK 🤯", 20, 25, "white"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    # Final hook
    hook = add_bold_caption("They severed a Rat's ACL 🐀 and it GREW BACK", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_2_rat_acl_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def build_clip_3_amphetamine():
    """Build Clip 3: Amphetamine Immunity"""
    console.print("[cyan]Building Clip 3: Amphetamine Immunity[/cyan]")
    
    # Video segment (38:38 - 38:48 = 2318s - 2328s)
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(2318.0, 2348.0)
    
    # Smart crop
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add pill skull (0-5s)
    pill_skull = load_asset("pill_skull")
    if pill_skull:
        pill = create_overlay_image(pill_skull, (500, 500), position="top")
        pill = pill.with_duration(5.0).with_start(0)
        layers.append(pill)
    
    # Add Windows error (10-20s)
    windows = load_asset("windows_error")
    if windows:
        error = create_overlay_image(windows, (700, 400), position="center")
        error = error.with_duration(10.0).with_start(10.0)
        layers.append(error)
    
    # Captions
    captions = [
        ("They gave rats LETHAL doses of amphetamines", 0, 5, "white"),
        ("Then injected BPC...", 6, 10, "yellow"),
        ("The amphetamines STOPPED WORKING", 10, 15, "yellow"),
        ("Your Adderall won't kick in! 💊", 18, 25, "white"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    hook = add_bold_caption("BPC-157 makes Stimulants STOP working? 💊🚫", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_3_amphetamine_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def build_clip_4_dosage():
    """Build Clip 4: Dosage Secret (10mg)"""
    console.print("[cyan]Building Clip 4: Dosage Secret (10mg)[/cyan]")
    
    # Video segment (41:75 - 41:90 approx = 2505s - 2520s)
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(4175.0, 4205.0)
    
    # Smart crop
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add syringe comparison (10-20s)
    syringe = load_asset("syringe_comparison")
    if syringe:
        syr = create_overlay_image(syringe, (900, 600), position="center")
        syr = syr.with_duration(10.0).with_start(10.0)
        layers.append(syr)
    
    # Captions  
    captions = [
        ("Low doses DON'T WORK for big injuries", 0, 5, "white"),
        ("My dose: 5-10 MILLIGRAMS", 10, 15, "yellow"),
        ("That's the FULL VIAL", 15, 20, "yellow"),
        ("BOLUS it day 1, then micro-dose", 20, 25, "white"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    hook = add_bold_caption("Why Micro-Dosing FAILED You 📉 (10mg Protocol)", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_4_dosage_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def build_clip_5_oral_bpc():
    """Build Clip 5: Oral BPC Truth"""
    console.print("[cyan]Building Clip 5: Oral BPC Truth[/cyan]")
    
    # Video segment 
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(4012.0, 4042.0)
    
    # Smart crop
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add pill surviving acid (10-20s)
    pill_acid = load_asset("pill_surviving")
    if pill_acid:
        acid = create_overlay_image(pill_acid, (700, 700), position="center")
        acid = acid.with_duration(10.0).with_start(10.0)
        layers.append(acid)
    
    # Captions
    captions = [
        ("People say BPC doesn't work ORALLY", 0, 5, "white"),
        ("That's NOT TRUE", 5, 8, "yellow"),
        ("BPC SURVIVES stomach acid", 10, 15, "white"),
        ("Because it's MADE in the stomach!", 15, 20, "yellow"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    hook = add_bold_caption("Stop Injecting? 💉 Oral BPC Actually WORKS ✅", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_5_oral_bpc_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def build_clip_6_fda_conspiracy():
    """Build Clip 6: FDA Name Change"""
    console.print("[cyan]Building Clip 6: FDA Name Change[/cyan]")
    
    video = VideoFileClip(str(VIDEO_PATH)).subclipped(4031.0, 4061.0)
    
    # Smart crop
    w, h = video.size
    crop_w = int(h * 9 / 16)
    x_center = w // 2
    video = video.cropped(x1=x_center - crop_w//2, x2=x_center + crop_w//2)
    video = video.resized((OUT_W, OUT_H))
    
    layers = [video]
    
    # Add FDA redacted document (0-10s)
    fda_doc = load_asset("fda_redacted")
    if fda_doc:
        doc = create_overlay_image(fda_doc, (700, 700), position="center", opacity=0.85)
        doc = doc.with_duration(10.0).with_start(0)
        layers.append(doc)
    
    # Add hacker terminal (15-25s)
    hacker = load_asset("hacker_terminal")
    if hacker:
        term = create_overlay_image(hacker, (800, 600), position="center")
        term = term.with_duration(10.0).with_start(15.0)
        layers.append(term)
    
    # Captions
    captions = [
        ("BPC is under FDA CATEGORY 2 BAN", 0, 5, "white"),
        ("But doctors found a LOOPHOLE", 8, 13, "yellow"),
        ("They renamed it...", 15, 18, "white"),
        ("PENTADECAPEPTIDE 🤫", 18, 25, "yellow"),
    ]
    
    for text, start, end, color in captions:
        cap = add_bold_caption(text, end - start, start, color=color)
        layers.append(cap)
    
    hook = add_bold_caption("The FDA banned it... Doctors RENAMED it 🤫", 
                           5.0, video.duration - 5, color="yellow")
    layers.append(hook)
    
    final = CompositeVideoClip(layers)
    output_path = OUTPUT_DIR / "clip_6_fda_conspiracy_vfx.mp4"
    final.write_videofile(str(output_path), fps=30, codec='libx264', audio_codec='aac')
    console.print(f"[green]✓ Saved: {output_path.name}[/green]")
    return output_path


def main():
    """Build all premium clips"""
    console.print("[bold magenta]🎬 Premium VFX Clip Builder[/bold magenta]")
    console.print(f"Asset directory: {ASSET_DIR}")
    console.print(f"Output directory: {OUTPUT_DIR}")
    
    # List available assets
    assets = list(ASSET_DIR.glob("*.png"))
    console.print(f"Found {len(assets)} image assets")
    
    # Build clips
    clips = []
    
    try:
        clips.append(build_clip_1_purple_tricep())
    except Exception as e:
        console.print(f"[red]Clip 1 failed: {e}[/red]")
    
    try:
        clips.append(build_clip_2_rat_acl())
    except Exception as e:
        console.print(f"[red]Clip 2 failed: {e}[/red]")
    
    try:
        clips.append(build_clip_3_amphetamine())
    except Exception as e:
        console.print(f"[red]Clip 3 failed: {e}[/red]")
    
    try:
        clips.append(build_clip_4_dosage())
    except Exception as e:
        console.print(f"[red]Clip 4 failed: {e}[/red]")
    
    try:
        clips.append(build_clip_5_oral_bpc())
    except Exception as e:
        console.print(f"[red]Clip 5 failed: {e}[/red]")
    
    try:
        clips.append(build_clip_6_fda_conspiracy())
    except Exception as e:
        console.print(f"[red]Clip 6 failed: {e}[/red]")
    
    console.print(f"\n[bold green]✓ Built {len(clips)} premium clips![/bold green]")
    console.print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

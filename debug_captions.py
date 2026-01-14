"""
Debug script to fix caption positioning and wrapping
"""
from moviepy import ColorClip, TextClip, CompositeVideoClip
from pathlib import Path

OUTPUT_DIR = Path("./temp/debug")
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

# TikTok/Reels Safe Zone approx (1080x1920)
# Top 250px blocked, Bottom 400px blocked, Sides 50px blocked
SAFE_ZONE_MARGIN_X = 50
SAFE_ZONE_TOP = 250
SAFE_ZONE_BOTTOM = 400

def create_debug_video():
    # Create dummy vertical video (black background)
    W, H = 1080, 1920
    bg = ColorClip(size=(W, H), color=(50, 50, 50), duration=5)
    
    # Text to test wrapping
    long_text = "THIS IS A VERY LONG SENTENCE TO TEST IF THE CAPTIONS ARE GOING TO BE CROPPED OR IF THEY WRAP CORRECTLY ON THE SCREEN"
    
    # Try the style we used
    try:
        txt_clip = TextClip(
            text=long_text, 
            font_size=80, 
            color="white",
            font="/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
            stroke_color="black", 
            stroke_width=4,
            size=(W - 100, None),  # Width constraint
            method='caption',
            text_align='center'
        )
        
        txt_clip = txt_clip.with_duration(5)
        txt_clip = txt_clip.with_position(("center", "center"))
        
        final = CompositeVideoClip([bg, txt_clip])
        final.write_videofile(str(OUTPUT_DIR / "test_caption_center.mp4"), fps=24)
        print("Generated center test")
        
        # Test bottom position (where it likely failed)
        txt_clip_bottom = txt_clip.with_position(("center", H - 500))
        final_bottom = CompositeVideoClip([bg, txt_clip_bottom])
        final_bottom.write_videofile(str(OUTPUT_DIR / "test_caption_bottom.mp4"), fps=24)
        print("Generated bottom test")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    create_debug_video()

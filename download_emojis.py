import os
import subprocess

EMOJI_MAP = {
    "purple": "🟣",
    "surgery": "💉",
    "doctor": "👨‍⚕️",
    "arm": "💪",
    "tendon": "🦴",
    "weeks": "📅",
    "weight": "🏋️‍♂️",
    "friend": "🤝",
    "larry": "🦁",
    "healed": "✨",
    "cross": "❌",
}

OS_PATH = "assets/emojis"
os.makedirs(OS_PATH, exist_ok=True)

for name, emoji in EMOJI_MAP.items():
    url = f"https://emojicdn.elk.sh/{emoji}?style=apple"
    out = f"{OS_PATH}/{name}.png"
    print(f"Downloading {name} ({emoji})...")
    subprocess.run(["curl", "-s", "-o", out, url], check=True)

print("Done!")

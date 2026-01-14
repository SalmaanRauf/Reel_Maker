# 🎬 Viral Clip Generator

Automatically transform long-form podcasts into viral-ready short clips for TikTok, Instagram Reels, and YouTube Shorts.

## Features

- **AI-Powered Clip Selection**: Uses Claude to identify the most viral-worthy moments
- **Smart Cropping**: YOLOv8-powered person detection with smooth tracking
- **Hormozi-Style Captions**: Bold, animated word-by-word captions
- **Whisper Transcription**: Accurate word-level timestamps for perfect caption sync

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY="your-key-here"

# Generate clips
python main.py --input "path/to/podcast.mp4" --topic "health tips" --clips 5
```

## Usage

```bash
python main.py \
    --input "Podcast w Dr Abud.mp4" \
    --topic "medicine" \
    --clips 5 \
    --output ./output
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--input, -i` | Input video file | Required |
| `--topic, -t` | Topic to extract clips about | Required |
| `--clips, -n` | Number of clips to generate | 5 |
| `--output, -o` | Output directory | ./output |
| `--llm` | LLM provider (claude/gemini) | claude |
| `--api-key` | LLM API key | Uses env var |

## Pipeline

1. **Transcription** - Whisper extracts audio and generates word-level timestamps
2. **Analysis** - Claude identifies the most viral moments based on your topic
3. **Smart Crop** - YOLOv8 detects speakers and creates smooth 9:16 crops
4. **Captions** - Adds bold, animated captions in Hormozi style
5. **Export** - Outputs ready-to-upload vertical clips

## Output

Clips are saved to `./output/` with names like:
- `clip_1_This_Changed_Everything.mp4`
- `clip_2_Nobody_Tells_You_This.mp4`

## Requirements

- Python 3.10+
- FFmpeg installed (`brew install ffmpeg`)
- Anthropic API key (for Claude)

# Reel Maker 🎬

Free, local Opus Clip alternative for generating viral short-form clips from podcasts.

## Features

- **100% Free** - Uses Ollama for local LLM inference (no API keys needed)
- **Smart Clip Selection** - AI identifies the most viral-worthy moments
- **Animated Captions** - Hormozi-style pop animations with keyword highlights
- **Auto B-Roll** - Fetches relevant stock footage from Pexels (free API)
- **Sound Effects** - Keyword-triggered SFX insertion
- **Smart Cropping** - AI-powered 9:16 framing with face tracking

## Quick Start

```bash
# 1. Install Ollama (one-time)
brew install ollama
ollama pull llama3.1:8b

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run!
python main.py \
    --input "Podcast.mp4" \
    --topic "health and fitness" \
    --clips 5
```

## Project Structure

```
├── main.py              # Main orchestrator
├── config.py            # Configuration settings
├── transcriber.py       # Whisper transcription with word timestamps
├── analyzer.py          # LLM-powered viral clip selection (Ollama/Claude/Gemini)
├── cropper.py           # YOLOv8 face detection + smart cropping
├── captioner.py         # MoviePy-based caption rendering
├── caption_animator.py  # ASS subtitle generation with pop effects
├── broll_engine.py      # Auto B-roll from Pexels API
├── sfx_engine.py        # Sound effect insertion
└── fast_renderer.py     # FFmpeg-based fast rendering
```

## Configuration

Set optional environment variables:
```bash
export PEXELS_API_KEY="your_free_key"  # For B-roll (get at pexels.com/api)
```

## LLM Options

| Provider | Cost | Setup |
|----------|------|-------|
| Ollama (default) | Free | `ollama pull llama3.1:8b` |
| Claude | Paid | Set `ANTHROPIC_API_KEY` |
| Gemini | Paid | Set `GOOGLE_API_KEY` |

## Requirements

- Python 3.10+
- FFmpeg
- Ollama (for free local LLM)
- ~5GB disk space for models

## License

MIT - Free for personal and commercial use.

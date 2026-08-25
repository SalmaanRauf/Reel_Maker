# Agentic Podcast Studio

A local-first podcast editing engine designed to be operated by Claude Code or Codex through existing subscriptions. The language model makes editorial decisions; deterministic local tools handle transcription, timecodes, cuts, captions, reframing, overlays, sound, rendering, and quality control.

This package lives inside the `Reel_Maker` repository while the original proof-of-concept scripts remain available for reference.

## What it is

Podcast Studio is not a prompt that emits FFmpeg commands. It provides:

- A versioned non-destructive timeline and style system.
- Semantic direction for hooks, claims, numbers, contrasts, mechanisms, evidence, caveats, and payoffs.
- Responsive word-timed captions with collision-aware layout.
- Discrete punch-ins and eased motion rather than constant template zooms.
- Licensed, provenance-aware B-roll and proof selection.
- Local Whisper transcription.
- Multicamera audio synchronization.
- Dead-zone smoothed face-aware vertical reframing.
- Speech-first audio finishing, music ducking, and restrained SFX.
- Technical and aesthetic QC.
- A CLI and project-scoped MCP server.
- Claude Code and Codex skills that encode the editorial doctrine.

## Installation

Apple Silicon recommended setup:

```bash
brew install ffmpeg
cd studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mlx,vision,sync,dev]'
podcast-studio doctor
```

Cross-platform CPU setup:

```bash
cd studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[whisper,vision,sync,dev]'
podcast-studio doctor
```

`ffmpeg` and `ffprobe` are required. At least one local transcription engine is recommended. Claude Code and Codex are optional for deterministic operations but required for subscription-backed editorial reasoning.

## First episode

```bash
podcast-studio init ~/podcasts/episode-001 --name "Episode 001"

podcast-studio add ~/podcasts/episode-001 \
  /path/to/camera-a.mp4 \
  /path/to/camera-b.mp4 \
  --role camera --mode reference

podcast-studio add ~/podcasts/episode-001 \
  /path/to/master-audio.wav \
  --role audio --mode reference

podcast-studio install-agent ~/podcasts/episode-001 --client both
```

The add command returns stable asset IDs. Run the end-to-end preview pipeline with one source:

```bash
podcast-studio auto ~/podcasts/episode-001 <ASSET_ID> \
  --agent claude \
  --count 8 \
  --style authority \
  --preview
```

Use `--agent codex` to use the authenticated Codex CLI. The child process is launched without `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, Azure credentials, Bedrock credentials, or Vertex credentials by default so the editorial layer uses the signed-in subscription instead of silently switching to metered API billing.

## Conversational operation

After `install-agent`:

```bash
cd ~/podcasts/episode-001
claude
```

or:

```bash
cd ~/podcasts/episode-001
codex
```

Recommended first instruction:

> Inspect all sources, synchronize the cameras and master audio, transcribe locally, and propose the strongest standalone clips. Preserve every material qualifier. Do not fabricate hooks or use decorative stock footage. After I approve the slate, direct and render previews, inspect every cut and overlay boundary, run technical and aesthetic QC, revise failures, and only then render final exports.

## CLI surface

```text
podcast-studio init
podcast-studio add
podcast-studio summary
podcast-studio doctor
podcast-studio transcribe
podcast-studio discover
podcast-studio select
podcast-studio sync
podcast-studio reframe
podcast-studio direct
podcast-studio render
podcast-studio qc
podcast-studio install-agent
podcast-studio auto
```

Every source-media operation is non-destructive. Derived artifacts are written beneath the episode workspace.

## MCP surface

The project-scoped stdio server exposes narrow tools for workspace management, media ingest, local transcription, clip discovery, direction, plan validation, rendering, QC, multicamera synchronization, reframing, and JSON artifact exchange.

Run it directly for protocol testing:

```bash
python -m podcast_studio.mcp_server
```

The installer writes:

```text
.claude/skills/podcast-editor/SKILL.md
.mcp.json
.agents/skills/podcast-editor/SKILL.md
.codex/config.toml
AGENTS.md
```

It does not change global Claude or Codex configuration.

## Editorial presets

The default `authority` profile is for expert-led medicine, science, business, law, and educational content:

- Proof-first inserts.
- Restrained semantic punch-ins.
- Clean typography.
- Stable vertical framing.
- Minimal SFX.
- Natural skin tone.
- Captions subordinate to the speaker.

Higher-density profiles remain semantic. They do not convert every sentence into large kinetic type or decorate weak clips with unrelated stock footage.

## Quality model

The gate rejects, among other issues:

- Constant unmotivated zoom drift.
- Excessive simultaneous visual events.
- Competing captions and editorial text.
- Generic B-roll presented as proof.
- Missing license/provenance data.
- Repeated media.
- Unsupported source paths.
- Dropped qualifiers.
- Loud or repetitive SFX.
- Unreadable text.
- Unsafe vertical framing.
- Black/frozen frames and unexpected silence.
- Incorrect duration, dimensions, loudness, or stream structure.

The expected loop is plan → preview → inspect → QC → revise → final. A successful process exit is not a quality pass.

## Specialty model features

Eye-contact correction, background replacement, translated dubbing, lip synchronization, voice cloning, avatars, and generated image/video/music/SFX require specialty models. The core provides consent-gated, executable-allowlisted provider adapters rather than pretending those proprietary model capabilities can be reproduced by FFmpeg.

Copy `src/podcast_studio/templates/providers.example.json`, configure a local or explicitly approved provider, and keep identity/voice features behind a consent receipt.

## Development

```bash
cd studio
pip install -e '.[dev]'
pytest -q
python -m compileall -q src
python -m build
```

The test suite covers timeline semantics, direction calibration, captions, B-roll ranking, FFmpeg graph construction, rendering dynamics, aesthetic QC, transcript interchange, silence protection, subscription isolation, workspace behavior, reframing, clip discovery, and MCP protocol handling.

## License

Apache-2.0 for the Podcast Studio implementation. Review third-party model and media licenses independently before distribution.

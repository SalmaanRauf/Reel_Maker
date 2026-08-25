# Podcast Studio

The production-grade agentic podcast editor is implemented under [`studio/`](studio/README.md).

It is designed for Claude Code or Codex subscription operation and includes the complete local capture-to-publish workflow:

- Camera recording and teleprompter.
- Subscription-backed script generation.
- Local word-timed transcription.
- Clip discovery and source-faithful selection.
- Transcript edits, multicamera sync, active-speaker planning, and stable vertical reframing.
- Responsive captions, semantic text, discrete punch-ins, proof, licensed B-roll, motion graphics, audio finishing, music, and restrained SFX.
- Preview/final rendering, technical and aesthetic QC, and a local review room.
- Publishing packages, thumbnail concepts, reference-style measurement, NLE interchange, benchmarking, and blind human review.
- Consent-gated adapters for eye contact, dubbing, lip sync, voice cloning, avatars, and generated media.

Start here:

```bash
cd studio
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mlx,vision,sync,dev]'
podcast-studio doctor
```

Documentation:

- [`studio/README.md`](studio/README.md) — installation and complete workflow.
- [`docs/CAPTIONS_PARITY_STATUS.md`](docs/CAPTIONS_PARITY_STATUS.md) — market map, gap analysis, and parity status.
- [`docs/MARKET_GAP_AUDIT.md`](docs/MARKET_GAP_AUDIT.md) — deeper architecture and market audit.
- [`studio/THIRD_PARTY.md`](studio/THIRD_PARTY.md) — third-party runtime/model/media boundaries.

# Third-Party Runtime and Model Notes

Podcast Studio is implemented independently under Apache-2.0. It invokes or optionally integrates with third-party software and models whose licenses remain separate.

## Required runtime

- **FFmpeg / ffprobe** — external executables. The license depends on how the installed build was configured. Distributors must review whether their build is LGPL or GPL and comply with that build's notices and source-offer obligations.
- **Pillow** — Python Imaging Library fork; HPND-style license.

## Optional Python dependencies

- **NumPy** — BSD-3-Clause.
- **OpenCV** — Apache-2.0 for current OpenCV releases; bundled codecs and data may have separate terms.
- **OpenTimelineIO** — Apache-2.0.
- **faster-whisper / CTranslate2** — MIT; model weights have their own terms.
- **mlx-whisper / MLX** — MIT; model weights have their own terms.
- **OpenAI Whisper reference implementation** — MIT; model weights and downstream use remain subject to their accompanying terms.

## External agent clients

Claude Code and Codex are launched as separately installed, authenticated command-line programs. Their subscriptions, acceptable-use rules, privacy terms, and output rights are governed by their respective providers. Podcast Studio does not bundle either client or their model weights.

## Specialty providers

Eye-contact correction, background matting, translation, voice cloning, lip synchronization, avatars, and generated image/video/music/SFX are provider interfaces only. Enabling one does not confer rights to its model, training data, generated output, or a depicted person's identity or voice. Review the selected provider's license and obtain all required consent before use.

## Media assets

The project records source and licensing metadata for B-roll, music, sound effects, fonts, screenshots, studies, charts, documents, and other external media. The operator remains responsible for validating the recorded license and attribution requirements before publication.

## Not incorporated

The repository may cite or study other open-source editors for market and architectural comparison. GPL-licensed implementations such as SynthCut are not copied into the Apache-2.0 Podcast Studio package.

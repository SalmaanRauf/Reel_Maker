# Captions-Grade Podcast Editing: Market and Gap Audit

Last updated: 2026-08-24

## Objective

Build a local-first, agent-operated podcast editor that can be driven by an authenticated Claude Code or Codex subscription and that produces edits with the visual grammar, pacing, typography, reframing, B-roll, audio polish, and review discipline expected from the best commercial short-form editors.

The target is not “more effects.” The target is a coherent editorial system in which every cut, crop, zoom, caption treatment, insert, transition, and sound event has a reason tied to the spoken idea.

## Products studied

Primary benchmark:

- Captions: AI Edit, Clips, caption styles, edit intensity, custom/generated media, horizontal and vertical formats, automatic reframing, eye contact, background removal, dubbing, avatars, and generative media.

Adjacent leaders:

- OpusClip: clip curation, hook/flow/value/trend scoring, reframing, animated captions, and social workflow.
- Submagic: transcript-synchronized zooms, B-roll frequency control, caption templates, transitions, silence/filler/bad-take removal, brand kits, and multi-format delivery.
- Descript: text-based editing, Automatic Multicam, reaction shots, group views, Studio Sound, filler removal, captions, eye contact, and reusable layouts.
- Riverside: Smart Layouts, speaker-aware scenes, split/grid/PiP layouts, pause removal, Magic Audio, and podcast-native recording/editing.
- Adobe Premiere Pro: text-based editing, J/L cuts, Auto Reframe, Media Intelligence, responsive graphics, Enhance Speech, color management, music remix, and professional interchange/review.

Open-source foundations reviewed:

- SynthCut: MCP-operated nonlinear editor, FFmpeg core, transcript editing, motion graphics, auto-reframe, inspection, and OTIO.
- video-edit-cli: agent-authored edit plans, podcast/short workflows, transcription, sync, restoration, provenance.
- video-use: transcript-first reasoning, on-demand visual composites, rendered cut-boundary self-evaluation.

## What the legacy Reel_Maker already attempted

The legacy repository contains useful experiments:

- Whisper transcription and clip analysis
- animated captions
- face-aware crops
- Pexels B-roll retrieval
- sound effects
- FFmpeg and MoviePy rendering
- multiple iterations of a specific Dr. Abud/BPC-157 edit

The problem is structural. Most creative decisions are embedded in one-off scripts and absolute local paths. A new look or timing revision creates another `build_clip1_v*` file. There is no canonical timeline, no validated style language, no deterministic agent contract, and no aesthetic quality gate.

## User-calibrated quality bar

The default house style must enforce these preferences:

1. Dense, hand-edited information, but not visual noise.
2. A meaningful new visual beat roughly every 0.3–1.2 seconds when the content supports it.
3. Semantic B-roll that matches concrete spoken nouns, actions, evidence, or locations.
4. Layered compositions: talking head + concise headline + proof/source/UI/product detail when useful.
5. Progressive disclosure rather than displaying the entire answer at once.
6. Punch-ins and crop changes tied to emphasis, contrast, surprise, or a new argument.
7. No constant linear slow zooms.
8. No generic AI imagery, decorative stock clips, random emojis, or unearned overlays.
9. No giant centered all-caps template typography.
10. Captions remain readable and subordinate to the content hierarchy.
11. Scientific and medical claims preserve qualifiers and distinguish evidence, hypothesis, and anecdote.
12. For restrained Dr. Abud walking/talking clips, captions plus one strong on-screen phrase may be the correct edit; the engine must not add B-roll merely to satisfy a quota.

## Capability matrix and gaps

Legend:

- **Implemented**: deterministic local behavior exists.
- **Partial**: primitive exists but lacks production grammar or QA.
- **Adapter**: interface exists; model/provider is not bundled.
- **Missing**: must be built.

| Area | Commercial benchmark | Previous local build | Gap to close |
|---|---|---:|---|
| Transcript editing | word-level cuts, filler/retake removal | Implemented | add continuity and qualifier-retention QA |
| Clip selection | hook, flow, value, trend, relevance | Partial | stronger editorial rubric, standalone resolution, evidence safety |
| Shot grammar | semantic cuts, reactions, section changes | Partial | cadence model, reaction/group views, J/L-cut intent |
| Dynamic zoom | multiple styles, transcript-synced | Partial | keyframes, easing, punch/pull/whip/rack profiles, density rules |
| Reframing | speaker tracking and multi-speaker switching | Partial | time-varying tracking, dead-zone, smoothing, look-room, layout fallback |
| Multicam | active speaker plus reactions/group views | Partial | conversational grammar and minimum/maximum shot logic |
| Captions | 100+ styles, active word, auto scale/move | Partial | responsive typography, per-word animation, safe zones, collision QA |
| Text hierarchy | headlines, labels, evidence cards | Partial | typed text roles, progressive disclosure, responsive sizing |
| B-roll | contextual/generated/custom media | Partial | semantic ranking, provenance, duplicate control, motion, fit QA |
| Proof inserts | screenshots/sources/product/UI evidence | Missing | source card model, crop callouts, readable proof layouts |
| Layouts | full, split, grid, PiP, content share | Missing | responsive scene layout model and renderer |
| Transitions | cut, dissolve, zoom, B-roll transitions | Partial | typed transition grammar and overuse limits |
| Sound design | music, ducking, SFX, hits | Partial | semantic SFX events, loudness caps, repetition and density QA |
| Audio repair | denoise, EQ, compression, loudness | Implemented | per-track intensity and A/B metadata |
| Color | correction, matching, LUTs | Partial | shot matching and skin-tone guardrails |
| Edit intensity | user-controllable creative density | Missing | normalized intensity profile across every subsystem |
| Brand kit | fonts, colors, logos, templates | Missing | validated brand tokens and responsive variants |
| Multi-format | 9:16, 4:5, 1:1, 16:9 | Partial | safe-region-aware responsive re-layout per format |
| Eye contact | model-based correction | Adapter | choose and benchmark a local/provider model |
| Background removal | person segmentation | Adapter | choose and benchmark a local/provider model |
| Dubbing/lip sync | translation and visual sync | Adapter | choose consent-safe model stack |
| Avatars/AI twins | proprietary generative models | Adapter | outside deterministic editing core |
| Generative media | images/video/music/SFX | Adapter | provider selection, provenance, quality gate |
| Aesthetic QA | product-specific hidden evaluation | Missing | explicit measurable edit-quality scorecard |
| Visual self-review | render and revise | Partial | representative frames, cut boundaries, captions, density metrics |
| Reproducibility | cloud project state | Implemented | retain plan/receipt/provenance through every revision |

## Required editorial timeline model

Every creative choice must be represented as data rather than hard-coded FFmpeg or MoviePy calls:

- source shots and master audio
- source and timeline time ranges
- layout and active speakers
- transform keyframes
- crop anchors and subject tracks
- transition events
- caption cues and per-word emphasis
- text cards and proof/source cards
- B-roll and image events
- sound effects and music beds
- color/audio treatments
- brand kit and output profile
- rationale, confidence, source provenance, and approval state

The plan must round-trip through JSON, validate before rendering, and remain editable by both an agent and a human.

## Motion grammar

### Approved motion

- **Punch-in:** 1.00 → 1.06–1.14 over 80–180 ms on a strong claim, number, contrast, or punchline.
- **Settle:** slight return after emphasis, usually after 0.7–2.0 seconds.
- **Reframe cut:** hard crop change at a semantic boundary; preferred over an endless zoom.
- **Push-through:** brief larger push into a proof insert or B-roll transition.
- **Pull-back:** reveal context after a close emotional or surprising beat.
- **Pan/recenter:** only to preserve subject framing or guide attention.
- **Ken Burns:** only for still evidence/images and only when direction supports the subject.

### Motion constraints

- Do not begin a new punch before the prior motion visually settles.
- Do not stack a punch-in, text-card entrance, B-roll entrance, and SFX on the same microbeat unless it is a deliberate climax.
- Avoid identical zoom amplitudes and intervals.
- Avoid motion during delicate scientific qualifiers unless it improves clarity.
- Avoid digital zoom above the profile limit unless source resolution supports it.
- Preserve eyes and mouth inside the format’s subject-safe area.

## Caption grammar

Captions are a reading system, not decoration.

- Use speech-rate-aware phrase grouping.
- Prefer 2–6 words per reveal; allow longer grammatical phrases only when reading speed remains safe.
- Maximum two lines for normal captions.
- Responsive size uses output height, phrase width, and line count—not a fixed pixel value.
- Reserve active-word color for semantic emphasis, not every word.
- Use active background or scale sparingly.
- Keep caption and proof/text-card lanes separate.
- Support sentence case by default; uppercase is a style choice, not a default.
- Preserve punctuation when it improves comprehension.
- Never obscure a face, mouth, source label, or essential B-roll detail.
- Prevent captions from colliding with platform chrome and lower-third safe zones.

## B-roll grammar

A B-roll event must answer at least one of these questions:

- What concrete object/person/location is being discussed?
- What action is occurring?
- What source or evidence supports the claim?
- What before/after, mechanism, comparison, or sequence needs visualization?
- What product/UI/document detail cannot be understood from the talking head?

No event should be added only because an elapsed-time threshold was reached.

Every B-roll asset must retain:

- origin and license
- query or semantic reason
- transcript span
- fit confidence
- duplicate/near-duplicate fingerprint
- crop/reframe decision
- whether it is evidence, illustration, context, or atmosphere

Generic stock footage, synthetic filler, and irrelevant “mood” shots should fail the default quality gate.

## Cut and layout grammar

- Use hard cuts for most podcast edits.
- Use J/L cuts to hide camera changes and preserve conversational flow.
- Avoid cutting every sentence at a fixed interval.
- A camera change should correspond to speaker change, argument change, reaction, proof insert, emotional beat, or reset after a long hold.
- Keep reaction shots long enough to be legible; do not manufacture reactions out of context.
- Rapid exchanges may use a group or split view rather than ping-ponging every fraction of a second.
- Minimum shot duration is profile-dependent; extremely short shots require a specific reason.
- Do not remove breaths that carry emotion or make speech sound synthetic.

## Aesthetic quality gate

A render should not pass solely because FFmpeg succeeded. The quality report must assess:

### Pacing

- hook latency
- shot-length distribution
- repeated framing runs
- cut density relative to edit intensity
- unmotivated microcuts
- long static holds without a reason

### Motion

- zoom count and amplitude distribution
- repeated motion patterns
- constant drift detection
- overlapping motion events
- excessive digital crop

### Typography

- minimum effective font size
- maximum reading speed
- line count and line length
- safe-zone compliance
- caption/text-card collision
- excessive uppercase and emphasis density

### B-roll and proof

- semantic confidence
- B-roll coverage and density
- repeated assets
- minimum and maximum insert duration
- source/provenance completeness
- readability of screenshots/source cards

### Audio

- integrated loudness and true peak
- speech/music balance
- SFX peak and density
- abrupt cut artifacts
- unexpected silence

### Integrity

- clip stands alone
- hook is supported by source content
- qualifiers are preserved
- no reordered words that alter meaning
- evidence/hypothesis/anecdote labels are retained where relevant

## Definition of “complete” for podcast editing

The deterministic podcast-editing core is considered feature-complete when it can:

1. Ingest one or more cameras plus isolated/master audio.
2. Transcribe with word timing and speaker labels.
3. Select and validate standalone clips.
4. Produce a structured edit plan with semantic beats.
5. Remove dead space, false starts, and approved filler without damaging cadence.
6. Apply speaker-aware layouts and reframing.
7. Schedule and render non-linear semantic motion.
8. Render responsive, animated, collision-safe captions.
9. Insert ranked B-roll, proof cards, screenshots, and text hierarchy.
10. Apply transitions, music, ducking, SFX, color, and audio mastering.
11. Export vertical, square, portrait, and landscape variants.
12. Run both technical and aesthetic quality control.
13. Present previews and evidence to Claude/Codex for revision.
14. Preserve a reproducible timeline and provenance receipt.

Eye-contact correction, translated dubbing/lip sync, avatars, and fully generated media remain specialty model capabilities. The editor must expose them through stable adapters and quality gates without pretending that open-source deterministic code reproduces proprietary model weights.

## Implementation order

1. Canonical timeline, brand kit, intensity and motion models.
2. Style profiles and semantic director.
3. Responsive caption layout and animation.
4. Keyframed renderer and transition grammar.
5. B-roll/proof asset catalog and ranking.
6. Multi-speaker layouts and tracking.
7. Aesthetic quality gate and render-inspection loop.
8. Claude/Codex subscription interface and MCP tools.
9. Review UI, format variants, benchmark fixtures, and regression tests.
10. Specialty-model adapters and benchmark harness.

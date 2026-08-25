from pathlib import Path
import shutil

import pytest

from podcast_studio.media import probe_media
from podcast_studio.models import (
    AudioBed,
    CaptionStyle,
    EditPlan,
    EditSegment,
    EvidenceCard,
    EvidenceKind,
    MotionKeyframe,
    MotionKind,
    MotionTrack,
    Overlay,
    OverlayKind,
    SoundEvent,
    TextOverlay,
    TextRole,
    Transcript,
    Transition,
    TransitionKind,
    Word,
)
from podcast_studio.process import run_command
from podcast_studio.project import ProjectWorkspace
from podcast_studio.render import compile_render, render_plan


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_dynamic_motion_transition_broll_text_music_sfx_and_captions_render(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    run_command([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-t", "5", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
    ])
    workspace = ProjectWorkspace.create(tmp_path / "project", name="Dynamics")
    asset = workspace.add_media([source], mode="copy")[0]

    overlay = workspace.root / "assets" / "proof.png"
    run_command([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x1c2f4a:s=600x800", "-frames:v", "1", overlay,
    ])
    music = workspace.root / "assets" / "music.wav"
    sfx = workspace.root / "assets" / "hit.wav"
    run_command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=48000", "-t", "5", music])
    run_command(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "0.15", sfx])

    transcript = Transcript(
        asset_id=asset.id,
        words=[
            Word("This", .2, .48), Word("claim", .49, .82), Word("needs", .83, 1.08), Word("proof.", 1.09, 1.42),
            Word("Here", 2.5, 2.75), Word("is", 2.76, 2.9), Word("the", 2.91, 3.02), Word("result.", 3.03, 3.42),
        ],
    )
    motion = MotionTrack(
        kind=MotionKind.PUNCH_IN,
        keyframes=[
            MotionKeyframe(0, 1.0, .5, .48),
            MotionKeyframe(.7, 1.0, .5, .48),
            MotionKeyframe(.86, 1.12, .52, .47),
            MotionKeyframe(2.2, 1.08, .52, .47),
        ],
        reason="claim emphasis",
    )
    plan = EditPlan(
        id="dynamic-integration",
        title="Dynamic integration",
        width=360,
        height=640,
        fps=24,
        caption_style=CaptionStyle(min_font_size=22, max_font_size=42, font_size_ratio=.04),
        segments=[
            EditSegment(
                source_id=asset.id,
                source_start=0,
                source_end=2.2,
                reason="claim",
                motion=motion,
                transition_to_next=Transition(TransitionKind.DISSOLVE, .2, reason="proof bridge"),
            ),
            EditSegment(source_id=asset.id, source_start=2.4, source_end=4.4, reason="result"),
        ],
        overlays=[
            Overlay(
                path=str(overlay.relative_to(workspace.root)),
                start=1.0,
                end=1.9,
                kind=OverlayKind.PROOF,
                width=280,
                height=360,
                fit="contain",
                semantic_reason="show source evidence",
                semantic_confidence=.93,
                source_url="https://example.test/study",
                license="fair-use excerpt",
            )
        ],
        text_overlays=[TextOverlay(.1, .9, "ONE CLEAR CLAIM", role=TextRole.HEADLINE, font_size=36, min_font_size=22, max_font_size=42, box=True)],
        evidence_cards=[EvidenceCard(2.25, 3.45, "37% measured difference", kind=EvidenceKind.CHART, source_name="2024 study")],
        music=AudioBed(path=str(music.relative_to(workspace.root)), gain_db=-30, duck=True),
        sound_effects=[SoundEvent(path=str(sfx.relative_to(workspace.root)), start=.82, gain_db=-22, duration=.15, reason="claim accent")],
    )
    output = workspace.root / "renders" / "dynamic.mp4"
    job = compile_render(workspace, plan, output, transcript=transcript, preview=True)
    assert "zoompan=" in job.filter_graph
    assert "xfade=transition=fade" in job.filter_graph
    assert "drawtext=" in job.filter_graph
    assert "sidechaincompress" in job.filter_graph
    assert "subtitles=" in job.filter_graph
    result = render_plan(workspace, plan, output, transcript=transcript, preview=True)
    probe = probe_media(result.output)
    assert probe.width == 360
    assert probe.height == 640
    assert abs(probe.duration - plan.duration) < .15
    assert Path(result.caption_path).is_file()

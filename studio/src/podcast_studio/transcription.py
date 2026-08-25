from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .exceptions import DependencyError, ValidationError
from .models import Transcript
from .process import run_command
from .transcript import save_transcript, transcript_from_json
from .util import dump_json


@dataclass(slots=True, frozen=True)
class TranscriptionEngine:
    name: str
    available: bool
    detail: str
    local: bool = True
    word_timestamps: bool = True


def available_engines() -> list[TranscriptionEngine]:
    apple_silicon = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    return [
        TranscriptionEngine(
            "mlx-whisper",
            apple_silicon and importlib.util.find_spec("mlx_whisper") is not None,
            "Best default on Apple Silicon; install podcast-studio[mlx].",
        ),
        TranscriptionEngine(
            "faster-whisper",
            importlib.util.find_spec("faster_whisper") is not None,
            "CTranslate2 local Whisper; install podcast-studio[whisper].",
        ),
        TranscriptionEngine(
            "openai-whisper",
            importlib.util.find_spec("whisper") is not None,
            "Reference local Whisper implementation.",
        ),
        TranscriptionEngine(
            "whisper.cpp",
            any(shutil.which(name) for name in ("whisper-cli", "whisper-cpp", "main")),
            "Fast native binary; set WHISPER_CPP_MODEL to a local model path.",
        ),
    ]


def select_engine(requested: str = "auto") -> str:
    normalized = requested.strip().lower().replace("_", "-")
    aliases = {"mlx": "mlx-whisper", "faster": "faster-whisper", "whisper": "openai-whisper", "cpp": "whisper.cpp"}
    normalized = aliases.get(normalized, normalized)
    engines = {engine.name: engine for engine in available_engines()}
    if normalized != "auto":
        if normalized not in engines:
            raise ValidationError(f"Unknown transcription engine: {requested}")
        if not engines[normalized].available:
            raise DependencyError(f"{normalized} is not installed. {engines[normalized].detail}")
        return normalized
    for preferred in ("mlx-whisper", "faster-whisper", "openai-whisper", "whisper.cpp"):
        if engines[preferred].available:
            return preferred
    raise DependencyError(
        "No local transcription engine is installed. On Apple Silicon run "
        "`pip install -e '.[mlx]'`; otherwise install the `whisper` extra or whisper.cpp."
    )


def transcribe_media(
    media_path: str | Path,
    output_dir: str | Path,
    *,
    asset_id: str = "unknown",
    engine: str = "auto",
    model: str = "large-v3-turbo",
    language: str | None = None,
    ffmpeg: str = "ffmpeg",
) -> Transcript:
    source = Path(media_path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Media not found: {source}")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    selected = select_engine(engine)
    with tempfile.TemporaryDirectory(prefix="podcast-studio-transcribe-") as temporary:
        audio = Path(temporary) / "audio.wav"
        _extract_audio(source, audio, ffmpeg=ffmpeg)
        if selected == "mlx-whisper":
            payload = _transcribe_mlx(audio, model=model, language=language)
        elif selected == "faster-whisper":
            payload = _transcribe_faster(audio, model=model, language=language)
        elif selected == "openai-whisper":
            payload = _transcribe_openai(audio, model=model, language=language)
        else:
            payload = _transcribe_cpp(audio, model=model, language=language)
    payload["asset_id"] = asset_id
    payload["engine"] = selected
    payload.setdefault("model", model)
    transcript = transcript_from_json(payload, asset_id=asset_id)
    save_transcript(transcript, destination / "transcript.json")
    save_transcript(transcript, destination / "transcript.srt")
    save_transcript(transcript, destination / "transcript.vtt")
    dump_json(
        {
            "asset_id": asset_id,
            "source": str(source),
            "engine": selected,
            "model": model,
            "language": transcript.language,
            "local_processing": True,
            "network_used": False,
        },
        destination / "transcription.receipt.json",
    )
    return transcript


def _extract_audio(source: Path, output: Path, *, ffmpeg: str) -> None:
    result = run_command(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
        ],
        check=False,
    )
    if result.returncode != 0 or not output.exists():
        raise DependencyError(f"Unable to extract transcription audio with FFmpeg: {result.stderr[-1200:]}")


def _transcribe_mlx(audio: Path, *, model: str, language: str | None) -> dict[str, Any]:
    import mlx_whisper  # type: ignore

    options: dict[str, Any] = {"path_or_hf_repo": _mlx_model_name(model), "word_timestamps": True, "verbose": False}
    if language:
        options["language"] = language
    result = mlx_whisper.transcribe(str(audio), **options)
    return _normalize_whisper_payload(result)


def _transcribe_faster(audio: Path, *, model: str, language: str | None) -> dict[str, Any]:
    from faster_whisper import WhisperModel  # type: ignore

    device = "cpu"
    compute_type = "int8"
    if shutil.which("nvidia-smi"):
        device, compute_type = "cuda", "float16"
    whisper_model = WhisperModel(_faster_model_name(model), device=device, compute_type=compute_type)
    segments, info = whisper_model.transcribe(
        str(audio),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=True,
    )
    normalized_segments: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        normalized_segments.append(
            {
                "id": index,
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
                "words": [
                    {
                        "start": float(word.start),
                        "end": float(word.end),
                        "word": word.word.strip(),
                        "probability": float(word.probability),
                    }
                    for word in (segment.words or [])
                    if word.start is not None and word.end is not None and word.word.strip()
                ],
            }
        )
    return {"language": info.language, "segments": normalized_segments}


def _transcribe_openai(audio: Path, *, model: str, language: str | None) -> dict[str, Any]:
    import whisper  # type: ignore

    loaded = whisper.load_model(_openai_model_name(model))
    result = loaded.transcribe(str(audio), language=language, word_timestamps=True, verbose=False, fp16=False)
    return _normalize_whisper_payload(result)


def _transcribe_cpp(audio: Path, *, model: str, language: str | None) -> dict[str, Any]:
    binary = next((path for name in ("whisper-cli", "whisper-cpp", "main") if (path := shutil.which(name))), None)
    model_path = os.environ.get("WHISPER_CPP_MODEL")
    if not binary or not model_path or not Path(model_path).is_file():
        raise DependencyError("whisper.cpp requires a whisper-cli binary and WHISPER_CPP_MODEL pointing to local weights")
    with tempfile.TemporaryDirectory(prefix="podcast-studio-whispercpp-") as temporary:
        prefix = Path(temporary) / "transcript"
        command = [
            binary, "-m", model_path, "-f", str(audio), "-ojf", "-of", str(prefix), "-pp", "-nt",
        ]
        if language:
            command.extend(["-l", language])
        result = run_command(command, check=False)
        output = Path(f"{prefix}.json")
        if result.returncode != 0 or not output.exists():
            raise DependencyError(f"whisper.cpp failed: {result.stderr[-1200:]}")
        raw = json.loads(output.read_text(encoding="utf-8"))
    transcription = raw.get("transcription", [])
    segments = []
    for index, item in enumerate(transcription):
        offsets = item.get("offsets", {})
        start = float(offsets.get("from", 0)) / 1000.0
        end = float(offsets.get("to", 0)) / 1000.0
        tokens = item.get("tokens", [])
        words = []
        for token in tokens:
            token_offsets = token.get("offsets", {})
            token_text = str(token.get("text") or "").strip()
            if token_text:
                words.append(
                    {
                        "word": token_text,
                        "start": float(token_offsets.get("from", offsets.get("from", 0))) / 1000.0,
                        "end": float(token_offsets.get("to", offsets.get("to", 0))) / 1000.0,
                        "probability": float(token.get("p", 0.0)),
                    }
                )
        segments.append({"id": index, "start": start, "end": end, "text": str(item.get("text") or "").strip(), "words": words})
    return {"language": raw.get("result", {}).get("language", language or "en"), "segments": segments}


def _normalize_whisper_payload(payload: dict[str, Any]) -> dict[str, Any]:
    segments = []
    for index, segment in enumerate(payload.get("segments") or []):
        words = []
        for word in segment.get("words") or []:
            text = str(word.get("word") or word.get("text") or "").strip()
            if text and word.get("start") is not None and word.get("end") is not None:
                words.append(
                    {
                        "word": text,
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                        "probability": word.get("probability", word.get("confidence")),
                    }
                )
        segments.append(
            {
                "id": segment.get("id", index),
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": str(segment.get("text") or "").strip(),
                "words": words,
            }
        )
    return {"language": payload.get("language") or "en", "segments": segments}


def _mlx_model_name(model: str) -> str:
    if "/" in model:
        return model
    mapping = {
        "large-v3": "mlx-community/whisper-large-v3-mlx",
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "medium": "mlx-community/whisper-medium-mlx",
        "small": "mlx-community/whisper-small-mlx",
    }
    return mapping.get(model, model)


def _faster_model_name(model: str) -> str:
    return "turbo" if model == "large-v3-turbo" else model


def _openai_model_name(model: str) -> str:
    return "turbo" if model == "large-v3-turbo" else model

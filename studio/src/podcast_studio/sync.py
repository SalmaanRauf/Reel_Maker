from __future__ import annotations

import math
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .exceptions import DependencyError, ValidationError
from .process import run_command
from .util import dump_json


@dataclass(slots=True, frozen=True)
class SyncResult:
    reference: str
    target: str
    offset_seconds: float
    confidence: float
    sample_rate: int
    analyzed_seconds: float
    method: str = "fft-cross-correlation"

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "target": self.target,
            "offset_seconds": self.offset_seconds,
            "confidence": self.confidence,
            "sample_rate": self.sample_rate,
            "analyzed_seconds": self.analyzed_seconds,
            "method": self.method,
        }


def estimate_offset(
    reference: str | Path,
    target: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    sample_rate: int = 8000,
    maximum_offset_seconds: float = 45.0,
    analyze_seconds: float = 900.0,
) -> SyncResult:
    try:
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise DependencyError("Multicamera sync requires NumPy. Install podcast-studio[sync].") from exc

    reference_path = Path(reference).expanduser().resolve()
    target_path = Path(target).expanduser().resolve()
    if not reference_path.is_file() or not target_path.is_file():
        raise ValidationError("Both sync sources must exist")
    if reference_path == target_path:
        return SyncResult(str(reference_path), str(target_path), 0.0, 1.0, sample_rate, 0.0)

    with tempfile.TemporaryDirectory(prefix="podcast-studio-sync-") as temporary:
        ref_wav = Path(temporary) / "reference.wav"
        target_wav = Path(temporary) / "target.wav"
        _extract_pcm(reference_path, ref_wav, ffmpeg=ffmpeg, sample_rate=sample_rate, seconds=analyze_seconds)
        _extract_pcm(target_path, target_wav, ffmpeg=ffmpeg, sample_rate=sample_rate, seconds=analyze_seconds)
        ref = _read_pcm(ref_wav)
        other = _read_pcm(target_wav)

    usable = min(len(ref), len(other), int(analyze_seconds * sample_rate))
    if usable < sample_rate * 3:
        raise ValidationError("At least three seconds of shared audio are required for synchronization")
    ref, other = ref[:usable], other[:usable]
    ref = _feature_signal(ref, sample_rate)
    other = _feature_signal(other, sample_rate)
    max_lag = min(int(maximum_offset_seconds * sample_rate / 80), len(ref) - 2)
    correlation = _fft_correlate(other, ref, np)
    center = len(ref) - 1
    window = correlation[max(0, center - max_lag): min(len(correlation), center + max_lag + 1)]
    peak_index = int(np.argmax(window))
    lag = peak_index + max(0, center - max_lag) - center
    peak = float(window[peak_index])

    exclusion = max(2, int(0.35 * sample_rate / 80))
    masked = window.copy()
    left, right = max(0, peak_index - exclusion), min(len(masked), peak_index + exclusion + 1)
    masked[left:right] = -np.inf
    second = float(np.max(masked)) if np.isfinite(masked).any() else 0.0
    spread = float(np.std(window)) + 1e-9
    peak_prominence = max(0.0, (peak - second) / (abs(peak) + 1e-9))
    z_score = max(0.0, (peak - float(np.median(window))) / spread)
    confidence = max(0.0, min(1.0, 0.55 * peak_prominence + 0.45 * min(1.0, z_score / 12.0)))

    feature_rate = sample_rate / 80.0
    return SyncResult(
        reference=str(reference_path),
        target=str(target_path),
        offset_seconds=float(lag / feature_rate),
        confidence=round(confidence, 4),
        sample_rate=sample_rate,
        analyzed_seconds=usable / sample_rate,
    )


def synchronize_many(
    reference: str | Path,
    targets: Iterable[str | Path],
    output: str | Path,
    **kwargs: object,
) -> list[SyncResult]:
    results = [estimate_offset(reference, target, **kwargs) for target in targets]
    dump_json({"reference": str(Path(reference).resolve()), "results": [item.to_dict() for item in results]}, output)
    return results


def apply_offset(source: str | Path, output: str | Path, offset_seconds: float, *, ffmpeg: str = "ffmpeg") -> Path:
    input_path = Path(source).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if offset_seconds >= 0:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-itsoffset", f"{offset_seconds:.6f}", "-i", str(input_path), "-c", "copy", str(destination),
        ]
    else:
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", f"{-offset_seconds:.6f}", "-i", str(input_path), "-c", "copy", str(destination),
        ]
    result = run_command(command, check=False)
    if result.returncode != 0:
        raise DependencyError(f"FFmpeg offset application failed: {result.stderr[-1200:]}")
    return destination


def _extract_pcm(source: Path, output: Path, *, ffmpeg: str, sample_rate: int, seconds: float) -> None:
    result = run_command(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(source), "-t", f"{seconds:.3f}", "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-c:a", "pcm_s16le", str(output),
        ],
        check=False,
    )
    if result.returncode != 0 or not output.exists():
        raise DependencyError(f"Unable to extract sync audio: {result.stderr[-1200:]}")


def _read_pcm(path: Path):
    import numpy as np  # type: ignore

    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def _feature_signal(signal, sample_rate: int):
    import numpy as np  # type: ignore

    block = 80
    usable = len(signal) - (len(signal) % block)
    if usable <= block:
        return signal
    framed = signal[:usable].reshape(-1, block)
    energy = np.sqrt(np.mean(framed * framed, axis=1) + 1e-10)
    derivative = np.abs(np.diff(energy, prepend=energy[0]))
    feature = 0.68 * energy + 0.32 * derivative
    feature -= np.mean(feature)
    norm = np.linalg.norm(feature)
    return feature / norm if norm > 1e-9 else feature


def _fft_correlate(a, b, np):
    size = 1 << math.ceil(math.log2(len(a) + len(b) - 1))
    spectrum = np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size))
    circular = np.fft.irfft(spectrum, size)
    return np.concatenate((circular[-(len(b) - 1):], circular[:len(a)]))

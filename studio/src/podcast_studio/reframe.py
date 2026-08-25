from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .exceptions import DependencyError, ValidationError
from .util import dump_json


@dataclass(slots=True, frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)


@dataclass(slots=True, frozen=True)
class FaceObservation:
    time: float
    box: Box
    confidence: float = 1.0
    speaker: str | None = None
    track_id: str | None = None


@dataclass(slots=True, frozen=True)
class CropKeyframe:
    time: float
    x: float
    y: float
    width: float
    height: float
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "time": self.time,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(slots=True, frozen=True)
class ReframePlan:
    source_width: int
    source_height: int
    output_width: int
    output_height: int
    keyframes: list[CropKeyframe]
    method: str = "face-track-deadzone-v1"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_width": self.source_width,
            "source_height": self.source_height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "method": self.method,
            "keyframes": [item.to_dict() for item in self.keyframes],
        }


def plan_reframe(
    observations: Iterable[FaceObservation],
    *,
    source_width: int,
    source_height: int,
    output_width: int = 1080,
    output_height: int = 1920,
    minimum_confidence: float = 0.55,
    smoothing_seconds: float = 0.65,
    dead_zone_fraction: float = 0.065,
    maximum_pan_fraction_per_second: float = 0.38,
    headroom_fraction: float = 0.16,
    look_room_fraction: float = 0.04,
) -> ReframePlan:
    if min(source_width, source_height, output_width, output_height) <= 0:
        raise ValidationError("Source and output dimensions must be positive")
    ordered = sorted((item for item in observations if item.confidence >= minimum_confidence), key=lambda item: item.time)
    crop_width, crop_height = crop_dimensions(source_width, source_height, output_width, output_height)
    if not ordered:
        centered = CropKeyframe(
            time=0.0,
            x=(source_width - crop_width) / 2.0,
            y=(source_height - crop_height) / 2.0,
            width=crop_width,
            height=crop_height,
            confidence=0.0,
            reason="No confident face track; stable center crop",
        )
        return ReframePlan(source_width, source_height, output_width, output_height, [centered])

    keyframes: list[CropKeyframe] = []
    smooth_x: float | None = None
    smooth_y: float | None = None
    previous_time: float | None = None
    velocity_x = 0.0
    velocity_y = 0.0

    for observation in ordered:
        target_x = observation.box.center_x - crop_width / 2.0
        target_y = observation.box.y - headroom_fraction * crop_height
        if observation.speaker:
            direction = -1.0 if hash(observation.speaker) % 2 == 0 else 1.0
            target_x += direction * look_room_fraction * crop_width
        target_x = _clamp(target_x, 0.0, source_width - crop_width)
        target_y = _clamp(target_y, 0.0, source_height - crop_height)

        if smooth_x is None or smooth_y is None or previous_time is None:
            smooth_x, smooth_y = target_x, target_y
            reason = "Acquire subject"
        else:
            delta_time = max(1 / 120.0, observation.time - previous_time)
            alpha = 1.0 - math.exp(-delta_time / max(0.05, smoothing_seconds))
            dead_x = dead_zone_fraction * crop_width
            dead_y = dead_zone_fraction * crop_height
            dx = target_x - smooth_x
            dy = target_y - smooth_y
            desired_vx = 0.0 if abs(dx) <= dead_x else (dx - math.copysign(dead_x, dx)) / delta_time
            desired_vy = 0.0 if abs(dy) <= dead_y else (dy - math.copysign(dead_y, dy)) / delta_time
            acceleration_alpha = min(1.0, alpha * 1.7)
            velocity_x += (desired_vx - velocity_x) * acceleration_alpha
            velocity_y += (desired_vy - velocity_y) * acceleration_alpha
            maximum_velocity = maximum_pan_fraction_per_second * crop_width
            velocity_x = _clamp(velocity_x, -maximum_velocity, maximum_velocity)
            velocity_y = _clamp(velocity_y, -maximum_velocity, maximum_velocity)
            projected_x = smooth_x + velocity_x * delta_time
            projected_y = smooth_y + velocity_y * delta_time
            smooth_x += (projected_x - smooth_x) * alpha
            smooth_y += (projected_y - smooth_y) * alpha
            smooth_x = _clamp(smooth_x, 0.0, source_width - crop_width)
            smooth_y = _clamp(smooth_y, 0.0, source_height - crop_height)
            reason = "Hold dead zone" if abs(dx) <= dead_x and abs(dy) <= dead_y else "Ease pan to subject"

        candidate = CropKeyframe(
            time=observation.time,
            x=round(smooth_x, 3),
            y=round(smooth_y, 3),
            width=crop_width,
            height=crop_height,
            confidence=observation.confidence,
            reason=reason,
        )
        if not keyframes or _meaningful_change(keyframes[-1], candidate, crop_width, crop_height):
            keyframes.append(candidate)
        previous_time = observation.time

    return ReframePlan(source_width, source_height, output_width, output_height, keyframes)


def crop_dimensions(source_width: int, source_height: int, output_width: int, output_height: int) -> tuple[float, float]:
    target_aspect = output_width / output_height
    source_aspect = source_width / source_height
    if source_aspect >= target_aspect:
        height = float(source_height)
        width = height * target_aspect
    else:
        width = float(source_width)
        height = width / target_aspect
    return width, height


def detect_faces(
    video_path: str | Path,
    *,
    every_seconds: float = 0.25,
    minimum_confidence: float = 0.55,
    maximum_seconds: float | None = None,
) -> tuple[list[FaceObservation], tuple[int, int]]:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise DependencyError("Face-aware reframing requires OpenCV. Install podcast-studio[vision].") from exc

    source = Path(video_path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Video not found: {source}")
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValidationError(f"OpenCV could not open {source}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_step = max(1, round(every_seconds * fps))
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    observations: list[FaceObservation] = []
    frame_number = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        time = frame_number / fps
        if maximum_seconds is not None and time > maximum_seconds:
            break
        if frame_number % frame_step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(48, 48))
            if len(faces):
                x, y, face_width, face_height = max(faces, key=lambda item: item[2] * item[3])
                relative_area = (face_width * face_height) / max(1, width * height)
                confidence = min(0.99, max(minimum_confidence, 0.55 + relative_area * 2.8))
                observations.append(
                    FaceObservation(
                        time=time,
                        box=Box(float(x), float(y), float(face_width), float(face_height)),
                        confidence=confidence,
                    )
                )
        frame_number += 1
    capture.release()
    return observations, (width, height)


def analyze_and_write(
    video_path: str | Path,
    output: str | Path,
    *,
    output_width: int = 1080,
    output_height: int = 1920,
    every_seconds: float = 0.25,
) -> ReframePlan:
    observations, (source_width, source_height) = detect_faces(video_path, every_seconds=every_seconds)
    plan = plan_reframe(
        observations,
        source_width=source_width,
        source_height=source_height,
        output_width=output_width,
        output_height=output_height,
    )
    payload = plan.to_dict()
    payload["source"] = str(Path(video_path).resolve())
    payload["observation_count"] = len(observations)
    dump_json(payload, output)
    return plan


def choose_layout(face_count: int, *, output_aspect: float, same_scene: bool = True) -> str:
    if face_count <= 1:
        return "speaker"
    if output_aspect < 0.8:
        return "stacked" if same_scene else "active-speaker"
    if output_aspect < 1.2:
        return "split"
    return "two-shot" if same_scene else "active-speaker"


def _meaningful_change(previous: CropKeyframe, current: CropKeyframe, width: float, height: float) -> bool:
    movement = math.hypot((current.x - previous.x) / max(1.0, width), (current.y - previous.y) / max(1.0, height))
    return current.time - previous.time >= 1.2 or movement >= 0.018


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))

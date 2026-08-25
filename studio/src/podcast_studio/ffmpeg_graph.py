from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Sequence

from .exceptions import ValidationError
from .models import Easing, MotionKeyframe, MotionTrack, Transform, TransitionKind
from .util import clamp

TRANSITION_MAP: dict[TransitionKind, str] = {
    TransitionKind.DISSOLVE: "fade",
    TransitionKind.DIP_TO_BLACK: "fadeblack",
    TransitionKind.DIP_TO_WHITE: "fadewhite",
    TransitionKind.ZOOM: "zoomin",
    TransitionKind.BLUR: "smoothleft",
    TransitionKind.WIPE_LEFT: "wipeleft",
    TransitionKind.WIPE_RIGHT: "wiperight",
    TransitionKind.WHIP: "slideleft",
}


def even(value: int | float) -> int:
    rounded = int(math.ceil(float(value)))
    return rounded if rounded % 2 == 0 else rounded + 1


def filter_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def drawtext_text(value: str) -> str:
    return (
        value.replace("\\", r"\\\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace("%", r"\%")
        .replace("\n", r"\n")
    )


def safe_expression(value: str) -> str:
    if not re.fullmatch(r"[0-9A-Za-z_+\-*/()., '\\]+", value):
        raise ValidationError(f"Unsafe FFmpeg expression: {value}")
    return value


def validate_custom_filter(value: str) -> str:
    lowered = value.lower()
    forbidden = ("movie=", "amovie=", "sendcmd", "zmq", "subtitles=", "concat=", "metadata=", "aevalsrc=")
    if any(item in lowered for item in forbidden):
        raise ValidationError(f"Unsafe or structural custom filter rejected: {value}")
    if "[" in value or "]" in value or ";" in value:
        raise ValidationError("Custom filters cannot introduce labels or new chains")
    return value


def responsive_text_size(
    text: str,
    *,
    requested: int,
    minimum: int,
    maximum: int,
    width: int,
    max_width_ratio: float,
    max_lines: int = 2,
) -> tuple[int, str]:
    requested = int(clamp(requested, minimum, maximum))
    words = text.split()
    if not words:
        return requested, ""
    target_width = width * max_width_ratio
    best_size = requested
    best_lines = [text]
    for font_size in range(requested, minimum - 1, -2):
        lines = _balanced_lines(words, font_size, target_width, max_lines=max_lines)
        if all(_measure_text(line, font_size) <= target_width for line in lines):
            best_size, best_lines = font_size, lines
            break
    return int(clamp(best_size, minimum, maximum)), "\n".join(best_lines)


def motion_filter(
    motion: MotionTrack,
    transform: Transform,
    *,
    width: int,
    height: int,
    fps: float,
    duration: float,
    prefix_filters: Sequence[str] = (),
) -> str:
    keyframes = list(motion.keyframes)
    if not keyframes:
        keyframes = [
            MotionKeyframe(0.0, transform.zoom, transform.crop_x, transform.crop_y, transform.rotation, transform.opacity, Easing.HOLD),
            MotionKeyframe(duration, transform.zoom, transform.crop_x, transform.crop_y, transform.rotation, transform.opacity, Easing.HOLD),
        ]
    elif keyframes[0].time > 0:
        keyframes.insert(0, MotionKeyframe(0.0, transform.zoom, transform.crop_x, transform.crop_y, transform.rotation, transform.opacity, Easing.HOLD))
    if keyframes[-1].time < duration:
        tail = keyframes[-1]
        keyframes.append(MotionKeyframe(duration, tail.zoom, tail.crop_x, tail.crop_y, tail.rotation, tail.opacity, Easing.HOLD))

    max_zoom = max(item.zoom for item in keyframes)
    base_x = clamp(keyframes[0].crop_x, 0, 1)
    base_y = clamp(keyframes[0].crop_y, 0, 1)
    time_var = f"on/{fps:.9f}"
    zoom = piecewise_expression(keyframes, "zoom", time_var=time_var)
    crop_x = piecewise_expression(keyframes, "crop_x", time_var=time_var)
    crop_y = piecewise_expression(keyframes, "crop_y", time_var=time_var)
    opacity = piecewise_expression(keyframes, "opacity", time_var=time_var)
    filters = [*prefix_filters]
    filters.extend(
        [
            f"scale=w='if(gt(a,{width}/{height}),-2,{width})':h='if(gt(a,{width}/{height}),{height},-2)':flags=lanczos",
            f"crop={width}:{height}:x='(iw-ow)*{base_x:.8f}':y='(ih-oh)*{base_y:.8f}'",
        ]
    )
    if max_zoom > 1.0001 or any(abs(item.crop_x - base_x) > 1e-5 or abs(item.crop_y - base_y) > 1e-5 for item in keyframes):
        filters.append(
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({crop_x})':y='(ih-ih/zoom)*({crop_y})':d=1:s={width}x{height}:fps={fps:.9f}"
        )
    else:
        filters.append(f"fps={fps:.9f}")
    if any(abs(item.rotation) > 0.001 for item in keyframes):
        rotation = piecewise_expression(keyframes, "rotation", time_var="t")
        filters.append(f"rotate=({rotation})*PI/180:ow={width}:oh={height}:fillcolor=black")
    if any(abs(item.opacity - 1) > 0.001 for item in keyframes):
        filters.extend(["format=rgba", f"colorchannelmixer=aa='{opacity}'"])
    filters.extend(["setsar=1", "format=yuv420p"])
    return ",".join(filters)


def overlay_motion_filter(
    motion: MotionTrack,
    *,
    width: int,
    height: int,
    fps: float,
    duration: float,
    fit: str,
    opacity: float,
    transition_in: float = 0.0,
    transition_out: float = 0.0,
) -> str:
    if fit == "cover":
        base = [
            f"scale=w='if(gt(a,{width}/{height}),-2,{width})':h='if(gt(a,{width}/{height}),{height},-2)':flags=lanczos",
            f"crop={width}:{height}",
        ]
    elif fit == "contain":
        base = [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0",
        ]
    elif fit == "stretch":
        base = [f"scale={width}:{height}:flags=lanczos"]
    else:
        raise ValidationError(f"Unknown overlay fit: {fit}")

    keyframes = list(motion.keyframes)
    if keyframes and (max(item.zoom for item in keyframes) > 1.0001 or len(keyframes) > 2):
        zoom = piecewise_expression(keyframes, "zoom", time_var=f"on/{fps:.9f}")
        crop_x = piecewise_expression(keyframes, "crop_x", time_var=f"on/{fps:.9f}")
        crop_y = piecewise_expression(keyframes, "crop_y", time_var=f"on/{fps:.9f}")
        base.append(
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({crop_x})':y='(ih-ih/zoom)*({crop_y})':d=1:s={width}x{height}:fps={fps:.9f}"
        )
    else:
        base.append(f"fps={fps:.9f}")
    base.append("format=rgba")
    if transition_in > 0:
        base.append(f"fade=t=in:st=0:d={min(transition_in, duration / 2):.6f}:alpha=1")
    if transition_out > 0:
        fade = min(transition_out, duration / 2)
        base.append(f"fade=t=out:st={max(0, duration - fade):.6f}:d={fade:.6f}:alpha=1")
    if opacity < 0.999:
        base.append(f"colorchannelmixer=aa={clamp(opacity, 0, 1):.6f}")
    return ",".join(base)


def piecewise_expression(
    keyframes: Sequence[MotionKeyframe],
    field: str,
    *,
    time_var: str = "t",
) -> str:
    if not keyframes:
        raise ValidationError("At least one keyframe is required")
    ordered = sorted(keyframes, key=lambda item: item.time)
    if field not in {"zoom", "crop_x", "crop_y", "rotation", "opacity"}:
        raise ValidationError(f"Unsupported keyframe field: {field}")
    if len(ordered) == 1:
        return _number(getattr(ordered[0], field))

    expression = _number(getattr(ordered[-1], field))
    for left, right in reversed(list(zip(ordered, ordered[1:], strict=False))):
        start, end = left.time, right.time
        left_value, right_value = float(getattr(left, field)), float(getattr(right, field))
        if end <= start or left.easing == Easing.HOLD:
            interval = _number(left_value)
        else:
            progress = f"clip((({time_var})-{start:.9f})/{end - start:.9f},0,1)"
            eased = easing_expression(progress, right.easing)
            interval = f"({_number(left_value)}+({_number(right_value - left_value)})*({eased}))"
        expression = f"if(lt(({time_var}),{end:.9f}),{interval},{expression})"
    return expression


def easing_expression(progress: str, easing: Easing | str) -> str:
    easing = Easing(easing)
    if easing == Easing.HOLD:
        return "0"
    if easing == Easing.LINEAR:
        return progress
    if easing == Easing.EASE_IN:
        return f"pow({progress},2)"
    if easing == Easing.EASE_OUT:
        return f"(1-pow(1-({progress}),2))"
    if easing == Easing.EASE_IN_OUT:
        return f"if(lt({progress},0.5),2*pow({progress},2),1-pow(-2*({progress})+2,2)/2)"
    if easing == Easing.SPRING:
        return f"clip(1-exp(-6*({progress}))*cos(8*({progress})),0,1.08)"
    return progress


def transition_name(kind: TransitionKind | str) -> str:
    kind = TransitionKind(kind)
    if kind == TransitionKind.CUT:
        raise ValidationError("Hard cuts do not use xfade")
    return TRANSITION_MAP[kind]


def _balanced_lines(words: list[str], font_size: int, target_width: float, *, max_lines: int) -> list[str]:
    if max_lines <= 1 or _measure_text(" ".join(words), font_size) <= target_width:
        return [" ".join(words)]
    best: tuple[float, list[str]] | None = None
    for split in range(1, len(words)):
        lines = [" ".join(words[:split]), " ".join(words[split:])]
        widths = [_measure_text(line, font_size) for line in lines]
        overflow = sum(max(0.0, value - target_width) for value in widths)
        balance = abs(widths[0] - widths[1]) * 0.15
        orphan = 100 if len(words[split:]) == 1 else 0
        score = overflow * 10 + balance + orphan
        if best is None or score < best[0]:
            best = score, lines
    return best[1] if best else [" ".join(words)]


def _measure_text(text: str, font_size: int) -> float:
    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.33
        elif character in "ilI1.,'`|!:;":
            units += 0.30
        elif character in "MW@#%&QO0":
            units += 0.79
        elif character.isupper():
            units += 0.63
        else:
            units += 0.53
    return max(1, units * font_size)


def _number(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    return f"{value:.9f}".rstrip("0").rstrip(".")

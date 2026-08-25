from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable

from .exceptions import ValidationError
from .transcript import load_transcript
from .util import dump_json


def direct_clip(
    *,
    transcript_path: str | Path,
    source_asset_id: str,
    start: float,
    end: float,
    output_path: str | Path,
    title: str = "Podcast clip",
    style: str = "authority",
    aspect_ratio: str = "9:16",
    brief: str = "",
) -> dict[str, Any]:
    transcript = load_transcript(transcript_path, asset_id=source_asset_id)
    modules = [
        importlib.import_module("podcast_studio.director_calibrated"),
        importlib.import_module("podcast_studio.director"),
    ]
    values = {
        "transcript": transcript,
        "source_asset_id": source_asset_id,
        "asset_id": source_asset_id,
        "start": start,
        "end": end,
        "in_point": start,
        "out_point": end,
        "title": title,
        "style": style,
        "preset": style,
        "aspect_ratio": aspect_ratio,
        "brief": brief,
        "editorial_brief": brief,
    }
    attempts: list[str] = []
    for module in modules:
        callables: list[Callable[..., Any]] = []
        for name in ("direct_clip", "build_edit_plan", "create_edit_plan", "plan_clip", "direct"):
            candidate = getattr(module, name, None)
            if callable(candidate):
                callables.append(candidate)
        for class_name in ("CalibratedDirector", "EditorialDirector", "Director"):
            director_class = getattr(module, class_name, None)
            if not inspect.isclass(director_class):
                continue
            try:
                instance = _call_with_supported(director_class, **values)
            except TypeError:
                try:
                    instance = director_class()
                except TypeError as exc:
                    attempts.append(f"{module.__name__}.{class_name}: {exc}")
                    continue
            for name in ("direct_clip", "build_edit_plan", "create_edit_plan", "plan", "direct"):
                candidate = getattr(instance, name, None)
                if callable(candidate):
                    callables.append(candidate)
        for function in callables:
            try:
                result = _call_with_supported(function, **values)
                payload = _serialize(result)
                payload.setdefault("title", title)
                payload.setdefault("source_asset_id", source_asset_id)
                payload.setdefault("metadata", {})
                if isinstance(payload["metadata"], dict):
                    payload["metadata"].update(
                        {
                            "editorial_brief": brief,
                            "requested_range": {"start": start, "end": end},
                            "style": style,
                            "aspect_ratio": aspect_ratio,
                        }
                    )
                dump_json(payload, output_path)
                return payload
            except (TypeError, ValidationError) as exc:
                attempts.append(f"{module.__name__}.{getattr(function, '__name__', type(function).__name__)}: {exc}")
    raise ValidationError("No compatible editorial director entry point succeeded: " + " | ".join(attempts[-8:]))


def _call_with_supported(callable_: Callable[..., Any], **values: Any) -> Any:
    signature = inspect.signature(callable_)
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, parameter in signature.parameters.items():
        if parameter.kind not in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}:
            continue
        if name in values:
            kwargs[name] = values[name]
        elif parameter.default is inspect.Parameter.empty:
            missing.append(name)
    if missing:
        raise TypeError(f"unsupported required parameters: {', '.join(missing)}")
    return callable_(**kwargs)


def _serialize(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, dict):
                return payload
    if isinstance(value, str):
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError("Director returned a non-JSON string") from exc
        if isinstance(payload, dict):
            return payload
    raise ValidationError(f"Director returned unsupported type: {type(value).__name__}")

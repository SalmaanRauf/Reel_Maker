from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable

from .exceptions import ValidationError


def load_edit_plan(path: str | Path) -> Any:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Edit plan not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("Edit plan must be a JSON object")
    for module_name, class_name in (
        ("podcast_studio.models", "EditPlan"),
        ("podcast_studio.timeline", "EditPlan"),
        ("podcast_studio.model_core", "EditPlan"),
    ):
        try:
            model_class = getattr(importlib.import_module(module_name), class_name)
        except (ImportError, AttributeError):
            continue
        for factory in ("from_dict", "model_validate", "parse_obj"):
            method = getattr(model_class, factory, None)
            if callable(method):
                return method(payload)
        try:
            return model_class(**payload)
        except TypeError:
            continue
    return payload


def render_plan_file(
    project_root: str | Path,
    plan_path: str | Path,
    output_path: str | Path,
    *,
    preview: bool = False,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    project = Path(project_root).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    plan = load_edit_plan(plan_path)
    module = importlib.import_module("podcast_studio.render")
    callables: list[Callable[..., Any]] = []
    for name in ("render_plan", "render_edit_plan", "render_timeline", "render_project", "render"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            callables.append(candidate)
    renderer_class = getattr(module, "Renderer", None)
    if inspect.isclass(renderer_class):
        try:
            renderer = _construct_with_supported(renderer_class, project_root=project, workspace=project, ffmpeg=ffmpeg, ffprobe=ffprobe)
            for name in ("render_plan", "render", "run"):
                candidate = getattr(renderer, name, None)
                if callable(candidate):
                    callables.append(candidate)
        except TypeError:
            pass
    failures: list[str] = []
    for function in callables:
        try:
            result = _call_with_supported(
                function,
                plan=plan,
                edit_plan=plan,
                timeline=plan,
                project_root=project,
                workspace=project,
                root=project,
                output=output,
                output_path=output,
                destination=output,
                preview=preview,
                quality="preview" if preview else "final",
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            return _result_payload(result, output)
        except TypeError as exc:
            failures.append(f"{getattr(function, '__name__', type(function).__name__)}: {exc}")
    available = ", ".join(name for name in dir(module) if name.startswith("render"))
    raise ValidationError(
        "No compatible render entry point was found. Available render symbols: "
        f"{available or 'none'}. Adapter failures: {' | '.join(failures[-4:])}"
    )


def run_quality_control(media_path: str | Path, *, report_path: str | Path | None = None) -> dict[str, Any]:
    source = Path(media_path).expanduser().resolve()
    if not source.is_file():
        raise ValidationError(f"Rendered media not found: {source}")
    module = importlib.import_module("podcast_studio.qc")
    candidates = [
        getattr(module, name, None)
        for name in ("quality_control", "run_qc", "inspect_render", "analyze_render", "qc_render")
    ]
    for function in candidates:
        if not callable(function):
            continue
        try:
            result = _call_with_supported(function, media_path=source, input_path=source, path=source, report_path=report_path)
            payload = _result_payload(result, source)
            if report_path:
                destination = Path(report_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
            return payload
        except TypeError:
            continue
    raise ValidationError("No compatible QC entry point was found in podcast_studio.qc")


def _construct_with_supported(callable_: Callable[..., Any], **values: Any) -> Any:
    signature = inspect.signature(callable_)
    kwargs = {
        name: values[name]
        for name, parameter in signature.parameters.items()
        if name in values and parameter.kind in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}
    }
    return callable_(**kwargs)


def _call_with_supported(callable_: Callable[..., Any], **values: Any) -> Any:
    signature = inspect.signature(callable_)
    kwargs: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in signature.parameters.items():
        if parameter.kind not in {parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY}:
            continue
        if name in values:
            kwargs[name] = values[name]
        elif parameter.default is inspect.Parameter.empty:
            required.append(name)
    if required:
        raise TypeError(f"unsupported required parameters: {', '.join(required)}")
    return callable_(**kwargs)


def _result_payload(result: Any, expected_path: Path) -> dict[str, Any]:
    if result is None:
        return {"output": str(expected_path), "exists": expected_path.exists()}
    if isinstance(result, Path):
        return {"output": str(result), "exists": result.exists()}
    if isinstance(result, str):
        path = Path(result)
        return {"output": result, "exists": path.exists()}
    if isinstance(result, dict):
        return result
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(result, method_name, None)
        if callable(method):
            payload = method()
            if isinstance(payload, dict):
                return payload
    return {"result": str(result), "output": str(expected_path), "exists": expected_path.exists()}

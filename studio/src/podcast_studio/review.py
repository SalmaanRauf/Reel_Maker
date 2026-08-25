from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .exceptions import ValidationError
from .workspace import load_manifest

_MAX_BODY = 256 * 1024


def build_manifest(root: str | Path) -> dict[str, Any]:
    project = Path(root).expanduser().resolve()
    manifest = load_manifest(project)
    renders: list[dict[str, Any]] = []
    for path in sorted((project / "renders").rglob("*.mp4")):
        relative = path.relative_to(project)
        stem = path.stem
        plan_path = project / "plans" / f"{stem}.json"
        qc_candidates = [
            path.with_suffix(".qc.json"),
            project / "review" / f"{stem}.qc.json",
            project / "renders" / f"{stem}.qc.json",
        ]
        renders.append(
            {
                "id": stem,
                "title": stem.replace("-", " ").strip().title(),
                "path": str(relative),
                "media_url": f"/media/{relative.as_posix()}",
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "preview": "previews" in relative.parts,
                "plan": _load_optional_json(plan_path),
                "qc": next((_load_optional_json(candidate) for candidate in qc_candidates if candidate.is_file()), None),
            }
        )
    decisions = _read_decisions(project / "review" / "decisions.jsonl")
    by_clip = {item["clip_id"]: item for item in decisions}
    for render in renders:
        render["decision"] = by_clip.get(render["id"])
    return {
        "project": {"id": manifest.get("id"), "name": manifest.get("name"), "root": str(project)},
        "renders": renders,
        "counts": {
            "total": len(renders),
            "approved": sum(1 for item in renders if (item.get("decision") or {}).get("decision") == "approved"),
            "revision": sum(1 for item in renders if (item.get("decision") or {}).get("decision") == "revision"),
            "rejected": sum(1 for item in renders if (item.get("decision") or {}).get("decision") == "rejected"),
        },
    }


def serve_review(
    root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> ThreadingHTTPServer:
    project = Path(root).expanduser().resolve()
    load_manifest(project)
    handler = _handler_factory(project)
    server = ThreadingHTTPServer((host, port), handler)
    if open_browser:
        url = f"http://{host}:{server.server_port}/"
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return server


def _handler_factory(project: Path):
    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "PodcastStudioReview/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._send_bytes(_HTML.encode(), "text/html; charset=utf-8")
            if parsed.path == "/api/manifest":
                return self._send_json(build_manifest(project))
            if parsed.path.startswith("/media/"):
                relative = unquote(parsed.path[len("/media/") :])
                try:
                    media = _safe_project_path(project, relative)
                except ValidationError as exc:
                    return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                if not media.is_file():
                    return self._send_json({"error": "Media not found"}, HTTPStatus.NOT_FOUND)
                return self._send_file(media)
            return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/decision":
                return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send_json({"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            if length <= 0 or length > _MAX_BODY:
                return self._send_json({"error": "Invalid request size"}, HTTPStatus.BAD_REQUEST)
            try:
                payload = json.loads(self.rfile.read(length))
                record = _validate_decision(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            destination = project / "review" / "decisions.jsonl"
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            return self._send_json({"ok": True, "decision": record})

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send_bytes(json.dumps(payload, default=str).encode(), "application/json; charset=utf-8", status)

        def _send_file(self, path: Path) -> None:
            size = path.stat().st_size
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            range_header = self.headers.get("Range")
            start, end = 0, size - 1
            status = HTTPStatus.OK
            if range_header and range_header.startswith("bytes="):
                try:
                    raw_start, raw_end = range_header[6:].split("-", 1)
                    start = int(raw_start) if raw_start else 0
                    end = int(raw_end) if raw_end else size - 1
                    start = max(0, min(start, size - 1))
                    end = max(start, min(end, size - 1))
                    status = HTTPStatus.PARTIAL_CONTENT
                except ValueError:
                    return self._send_json({"error": "Invalid Range"}, HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _send_bytes(self, payload: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self' blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(payload)

    return ReviewHandler


def _validate_decision(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("Decision must be an object")
    clip_id = str(payload.get("clip_id") or "").strip()
    decision = str(payload.get("decision") or "").strip().lower()
    notes = str(payload.get("notes") or "").strip()
    if not clip_id or len(clip_id) > 160:
        raise ValidationError("A valid clip_id is required")
    if decision not in {"approved", "revision", "rejected"}:
        raise ValidationError("Decision must be approved, revision, or rejected")
    if len(notes) > 5000:
        raise ValidationError("Notes are too long")
    return {
        "clip_id": clip_id,
        "decision": decision,
        "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _safe_project_path(project: Path, relative: str) -> Path:
    candidate = (project / relative).resolve()
    try:
        candidate.relative_to(project)
    except ValueError as exc:
        raise ValidationError("Path escapes the project workspace") from exc
    return candidate


def _load_optional_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON: {path.name}"}


def _read_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("clip_id"):
            latest[str(item["clip_id"])] = item
    return list(latest.values())


_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Podcast Studio Review</title><style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f7f7f5;background:#0c0c0d;font-synthesis:none}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 68% -10%,#24252a 0,transparent 36%),#0c0c0d}.shell{display:grid;grid-template-columns:310px minmax(0,1fr);min-height:100vh}.rail{border-right:1px solid #2a2a2e;padding:24px 18px;background:rgba(15,15,17,.88);backdrop-filter:blur(22px);overflow:auto;height:100vh;position:sticky;top:0}.brand{font-weight:760;letter-spacing:-.04em;font-size:22px}.sub{color:#92939a;font-size:12px;margin:6px 0 22px}.counts{display:flex;gap:7px;margin-bottom:18px}.pill{border:1px solid #303137;color:#b6b7bd;border-radius:99px;padding:6px 8px;font-size:10px}.clip{width:100%;border:1px solid transparent;background:transparent;color:#d7d7da;border-radius:12px;text-align:left;padding:11px 12px;margin:3px 0;cursor:pointer}.clip:hover{background:#18181b}.clip.active{background:#202126;border-color:#3b3c43;color:white}.clip-title{font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.clip-meta{font-size:10px;color:#81838b;margin-top:5px;display:flex;justify-content:space-between}.stage{padding:28px 36px 48px;display:grid;grid-template-columns:minmax(360px,1fr) 360px;gap:28px;align-items:start}.viewer{position:sticky;top:28px;display:flex;justify-content:center}.frame{background:#050506;border:1px solid #2b2c31;border-radius:18px;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.45);max-height:calc(100vh - 56px);aspect-ratio:9/16}.frame video{display:block;width:100%;height:100%;object-fit:contain;background:#000}.panel{padding-top:2px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;color:#7f8189;font-size:10px}.title{font-size:30px;line-height:1.05;letter-spacing:-.045em;margin:9px 0 8px}.path{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#777982;font-size:10px;overflow-wrap:anywhere}.section{margin-top:22px;padding-top:20px;border-top:1px solid #292a2f}.section h3{font-size:12px;margin:0 0 11px;color:#b8b9bf}.qc{display:grid;gap:7px;font-size:11px;color:#999ba3}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.actions button{border:1px solid #36373d;background:#191a1e;color:#dddde1;border-radius:10px;padding:10px 8px;cursor:pointer;font-weight:650;font-size:11px}.actions button:hover{background:#24252a}.actions button[data-v=approved]{border-color:#315c45}.actions button[data-v=revision]{border-color:#6b5a2c}.actions button[data-v=rejected]{border-color:#6a3434}textarea{width:100%;height:120px;border-radius:12px;border:1px solid #34353b;background:#131316;color:#ececef;padding:12px;resize:vertical;margin:10px 0;font:inherit;font-size:12px;line-height:1.45}.save{width:100%;border:0;border-radius:11px;background:#f2f2ef;color:#111;padding:11px;font-weight:750;cursor:pointer}.empty{color:#999;padding:50px}.toast{position:fixed;right:24px;bottom:24px;padding:10px 14px;background:#f0f0ed;color:#111;border-radius:10px;font-size:12px;opacity:0;transform:translateY(8px);transition:.2s}.toast.show{opacity:1;transform:none}@media(max-width:980px){.shell{grid-template-columns:1fr}.rail{position:relative;height:auto;border-right:0;border-bottom:1px solid #2a2a2e}.stage{grid-template-columns:1fr;padding:22px}.viewer{position:relative;top:0}.frame{height:70vh}.panel{max-width:680px;margin:auto;width:100%}}
</style></head><body><div class="shell"><aside class="rail"><div class="brand">Podcast Studio</div><div class="sub" id="project">Loading review…</div><div class="counts" id="counts"></div><div id="clips"></div></aside><main class="stage" id="stage"><div class="empty">No rendered clips found.</div></main></div><div class="toast" id="toast"></div><script>
let data=null,current=0,pending='revision';const $=s=>document.querySelector(s);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){data=await fetch('/api/manifest').then(r=>r.json());$('#project').textContent=data.project.name;renderRail();render();}
function renderRail(){const c=data.counts;$('#counts').innerHTML=`<span class=pill>${c.total} clips</span><span class=pill>${c.approved} approved</span>`;$('#clips').innerHTML=data.renders.map((x,i)=>`<button class="clip ${i===current?'active':''}" onclick="current=${i};renderRail();render()"><div class=clip-title>${esc(x.title)}</div><div class=clip-meta><span>${x.preview?'Preview':'Final'}</span><span>${esc(x.decision?.decision||'unreviewed')}</span></div></button>`).join('')}
function render(){const x=data.renders[current];if(!x){$('#stage').innerHTML='<div class=empty>No rendered clips found.</div>';return}const qc=x.qc||{};$('#stage').innerHTML=`<div class=viewer><div class=frame><video controls preload=metadata src="${esc(x.media_url)}"></video></div></div><section class=panel><div class=eyebrow>${x.preview?'Preview render':'Final render'}</div><h1 class=title>${esc(x.title)}</h1><div class=path>${esc(x.path)}</div><div class=section><h3>Quality control</h3><div class=qc><div>Score: ${esc(qc.score??qc.aesthetic_score??'Not run')}</div><div>Status: ${esc(qc.status??(qc.passed===true?'passed':qc.passed===false?'failed':'unknown'))}</div><div>${esc((qc.failures||qc.issues||[]).slice(0,5).join(' · ')||'No reported failures')}</div></div></div><div class=section><h3>Decision</h3><div class=actions><button data-v=approved onclick="pick('approved')">Approve <kbd>A</kbd></button><button data-v=revision onclick="pick('revision')">Revise <kbd>R</kbd></button><button data-v=rejected onclick="pick('rejected')">Reject <kbd>X</kbd></button></div><textarea id=notes placeholder="Specific revision notes: pacing, crop, caption, proof, timing, audio…">${esc(x.decision?.notes||'')}</textarea><button class=save onclick=save()>Save ${esc(x.decision?.decision||pending)}</button></div><div class=section><h3>Keyboard</h3><div class=qc>←/→ clip · space play/pause · A approve · R revise · X reject</div></div></section>`;pending=x.decision?.decision||'revision'}
function pick(v){pending=v;document.querySelectorAll('.actions button').forEach(b=>b.style.background=b.dataset.v===v?'#303138':'');document.querySelector('.save').textContent='Save '+v}
async function save(){const x=data.renders[current],notes=$('#notes').value;const r=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clip_id:x.id,decision:pending,notes})}).then(r=>r.json());if(r.error)return toast(r.error);x.decision=r.decision;data.counts={total:data.renders.length,approved:data.renders.filter(y=>y.decision?.decision==='approved').length,revision:data.renders.filter(y=>y.decision?.decision==='revision').length,rejected:data.renders.filter(y=>y.decision?.decision==='rejected').length};renderRail();toast('Decision saved')}
function toast(t){const x=$('#toast');x.textContent=t;x.classList.add('show');setTimeout(()=>x.classList.remove('show'),1600)}
document.addEventListener('keydown',e=>{if(e.target.tagName==='TEXTAREA')return;if(e.key==='ArrowRight'){current=Math.min(data.renders.length-1,current+1);renderRail();render()}if(e.key==='ArrowLeft'){current=Math.max(0,current-1);renderRail();render()}if(e.key==='a')pick('approved');if(e.key==='r')pick('revision');if(e.key==='x')pick('rejected');if(e.key===' '){e.preventDefault();const v=document.querySelector('video');v.paused?v.play():v.pause()}});load();
</script></body></html>'''

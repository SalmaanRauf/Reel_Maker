from __future__ import annotations

import json
import mimetypes
import re
import threading
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .exceptions import ValidationError
from .workspace import add_assets, initialize_workspace

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


def serve_capture(
    root: str | Path,
    *,
    script: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> ThreadingHTTPServer:
    project = Path(root).expanduser().resolve()
    initialize_workspace(project)
    script_text = _load_script(script)
    handler = _handler_factory(project, script_text)
    server = ThreadingHTTPServer((host, port), handler)
    if open_browser:
        url = f"http://{host}:{server.server_port}/"
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return server


def _handler_factory(project: Path, initial_script: str):
    class CaptureHandler(BaseHTTPRequestHandler):
        server_version = "PodcastStudioCapture/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._send_bytes(_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path == "/api/config":
                return self._send_json({"project": project.name, "script": initial_script})
            return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/upload":
                return self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send_json({"error": "Invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            if length <= 0 or length > _MAX_UPLOAD_BYTES:
                return self._send_json({"error": "Recording is empty or exceeds the local upload limit"}, HTTPStatus.BAD_REQUEST)
            query = parse_qs(parsed.query)
            requested_name = query.get("name", [""])[0]
            content_type = self.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].strip().lower()
            suffix = _extension_for(content_type)
            stem = _safe_stem(requested_name) or datetime.now(timezone.utc).strftime("capture-%Y%m%d-%H%M%S")
            captures = project / "sources" / "captures"
            captures.mkdir(parents=True, exist_ok=True)
            destination = _unique_path(captures / f"{stem}{suffix}")
            temporary = destination.with_suffix(destination.suffix + ".partial")
            remaining = length
            try:
                with temporary.open("wb") as handle:
                    while remaining:
                        chunk = self.rfile.read(min(_CHUNK_BYTES, remaining))
                        if not chunk:
                            raise ValidationError("Recording upload ended before Content-Length bytes were received")
                        handle.write(chunk)
                        remaining -= len(chunk)
                temporary.replace(destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            registration: dict[str, Any] | None = None
            warning = None
            try:
                registration = add_assets(project, [destination], role="camera", mode="reference", label=destination.stem)[0]
            except Exception as exc:  # Capture remains safely saved even when ffprobe is unavailable.
                warning = f"Recording saved, but project registration failed: {exc}"
            return self._send_json(
                {
                    "ok": True,
                    "path": str(destination),
                    "size_bytes": destination.stat().st_size,
                    "asset": registration,
                    "warning": warning,
                },
                HTTPStatus.CREATED,
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send_bytes(json.dumps(payload, default=str).encode("utf-8"), "application/json; charset=utf-8", status)

        def _send_bytes(self, payload: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; media-src 'self' blob:; connect-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
            )
            self.end_headers()
            self.wfile.write(payload)

    return CaptureHandler


def _load_script(value: str | Path | None) -> str:
    if value is None:
        return ""
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValidationError(f"Teleprompter script not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            text = payload.get("full_script") or payload.get("script") or payload.get("text")
            if isinstance(text, str):
                return text
        raise ValidationError("Script JSON requires `full_script`, `script`, or `text`")
    return path.read_text(encoding="utf-8")


def _extension_for(content_type: str) -> str:
    known = {
        "video/webm": ".webm",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "audio/webm": ".webm",
        "audio/mp4": ".m4a",
    }
    return known.get(content_type) or mimetypes.guess_extension(content_type) or ".webm"


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).stem).strip(".-_")
    return cleaned[:96]


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValidationError("Unable to allocate a unique capture filename")


_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Podcast Studio Capture</title><style>
:root{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#f5f5f3;background:#09090a}*{box-sizing:border-box}body{margin:0;overflow:hidden;background:#09090a}.app{height:100vh;display:grid;grid-template-columns:minmax(0,1fr) 380px}.stage{position:relative;background:#030304;display:flex;align-items:center;justify-content:center;overflow:hidden}.stage video{width:100%;height:100%;object-fit:contain;background:#000}.stage.mirror video{transform:scaleX(-1)}.countdown{position:absolute;inset:0;display:none;place-items:center;background:rgba(0,0,0,.42);font-size:min(30vw,220px);font-weight:800;letter-spacing:-.07em}.countdown.show{display:grid}.recording{position:absolute;top:24px;left:24px;display:none;align-items:center;gap:9px;background:rgba(0,0,0,.56);border:1px solid rgba(255,255,255,.15);padding:8px 11px;border-radius:99px;font-size:12px}.recording.show{display:flex}.dot{width:9px;height:9px;background:#ff3b36;border-radius:50%;box-shadow:0 0 0 6px rgba(255,59,54,.14)}.prompt{position:absolute;left:8%;right:8%;bottom:7%;height:44%;overflow:hidden;pointer-events:none;text-align:center;text-wrap:balance}.prompt-inner{font-weight:760;line-height:1.22;text-shadow:0 2px 18px rgba(0,0,0,.9);white-space:pre-wrap;transform:translateY(100%);will-change:transform}.panel{height:100vh;overflow:auto;border-left:1px solid #29292d;background:#111113;padding:22px}.brand{font-size:20px;font-weight:760;letter-spacing:-.035em}.sub{font-size:11px;color:#85868e;margin:6px 0 20px}.field{margin:15px 0}.field label{display:flex;justify-content:space-between;color:#a3a4aa;font-size:11px;margin-bottom:7px}select,input,textarea,button{font:inherit}select,input[type=text],textarea{width:100%;background:#19191c;color:#eee;border:1px solid #34343a;border-radius:10px;padding:10px}textarea{height:250px;resize:vertical;line-height:1.45;font-size:12px}.row{display:grid;grid-template-columns:1fr 1fr;gap:9px}.toggle{display:flex;align-items:center;gap:8px;font-size:12px;color:#b5b6bb}.controls{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:16px}button{border:1px solid #37383d;background:#1d1e22;color:#eee;border-radius:11px;padding:11px;cursor:pointer;font-weight:700}button.primary{background:#f1f1ee;color:#111;border-color:#f1f1ee}button.danger{background:#341719;border-color:#6a2c30}button:disabled{opacity:.4;cursor:not-allowed}.status{font-size:11px;color:#8d8e96;line-height:1.45;margin-top:12px;min-height:34px}.range{width:100%}@media(max-width:900px){.app{grid-template-columns:1fr}.panel{position:absolute;z-index:5;right:0;top:0;width:min(88vw,380px);background:rgba(17,17,19,.96);backdrop-filter:blur(16px)}.prompt{right:min(92vw,400px)}}
</style></head><body><div class=app><main class="stage mirror" id=stage><video id=preview autoplay muted playsinline></video><div class=countdown id=countdown></div><div class=recording id=recording><span class=dot></span><span id=timer>00:00</span></div><div class=prompt><div class=prompt-inner id=prompt></div></div></main><aside class=panel><div class=brand>Podcast Studio Capture</div><div class=sub id=project>Local camera + teleprompter</div><div class=field><label>Camera</label><select id=camera></select></div><div class=field><label>Microphone</label><select id=mic></select></div><div class=row><label class=toggle><input type=checkbox id=mirror checked> Mirror preview</label><label class=toggle><input type=checkbox id=count checked> 3-second count</label></div><div class=field><label><span>Teleprompter</span><span id=wordcount></span></label><textarea id=script placeholder="Paste or generate a script…"></textarea></div><div class=field><label><span>Scroll speed</span><span id=speedout>28</span></label><input class=range id=speed type=range min=8 max=90 value=28></div><div class=field><label><span>Text size</span><span id=sizeout>42</span></label><input class=range id=size type=range min=24 max=80 value=42></div><div class=field><label>Recording name</label><input id=name type=text placeholder="take-01"></div><div class=controls><button id=start class=primary>Start</button><button id=stop class=danger disabled>Stop & save</button><button id=promptctl>Play prompt</button><button id=reset>Reset prompt</button></div><div class=status id=status>Camera access stays in this browser. Recordings upload only to this local workspace.</div></aside></div><script>
const $=s=>document.querySelector(s);let stream=null,recorder=null,chunks=[],startedAt=0,timer=null,raf=null,promptY=0,promptLast=0,promptPlaying=false;const supported=['video/mp4;codecs=h264,aac','video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'];
async function boot(){const cfg=await fetch('/api/config').then(r=>r.json());$('#project').textContent=cfg.project+' · local capture';$('#script').value=cfg.script||'';words();await permission();await devices();bind();}
async function permission(){stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1920},height:{ideal:1080}},audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});$('#preview').srcObject=stream}
async function devices(){const ds=await navigator.mediaDevices.enumerateDevices(),cam=$('#camera'),mic=$('#mic');cam.innerHTML=ds.filter(d=>d.kind==='videoinput').map((d,i)=>`<option value="${d.deviceId}">${d.label||'Camera '+(i+1)}</option>`).join('');mic.innerHTML=ds.filter(d=>d.kind==='audioinput').map((d,i)=>`<option value="${d.deviceId}">${d.label||'Microphone '+(i+1)}</option>`).join('')}
async function switchDevices(){if(stream)stream.getTracks().forEach(t=>t.stop());stream=await navigator.mediaDevices.getUserMedia({video:{deviceId:{exact:$('#camera').value},width:{ideal:1920},height:{ideal:1080}},audio:{deviceId:{exact:$('#mic').value},echoCancellation:false,noiseSuppression:false,autoGainControl:false}});$('#preview').srcObject=stream}
function bind(){$('#camera').onchange=switchDevices;$('#mic').onchange=switchDevices;$('#mirror').onchange=()=>$('#stage').classList.toggle('mirror',$('#mirror').checked);$('#script').oninput=()=>{words();resetPrompt()};$('#speed').oninput=()=>$('#speedout').textContent=$('#speed').value;$('#size').oninput=()=>{$('#sizeout').textContent=$('#size').value;$('#prompt').style.fontSize=$('#size').value+'px'};$('#start').onclick=start;$('#stop').onclick=stop;$('#promptctl').onclick=togglePrompt;$('#reset').onclick=resetPrompt;$('#prompt').textContent=$('#script').value;$('#prompt').style.fontSize=$('#size').value+'px'}
function words(){$('#wordcount').textContent=$('#script').value.trim()?$('#script').value.trim().split(/\s+/).length+' words':'';$('#prompt').textContent=$('#script').value}
async function start(){if(!stream)return;$('#start').disabled=true;if($('#count').checked)await countdown();chunks=[];const mime=supported.find(MediaRecorder.isTypeSupported)||'';recorder=new MediaRecorder(stream,mime?{mimeType:mime,videoBitsPerSecond:12000000,audioBitsPerSecond:256000}:undefined);recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};recorder.onstop=upload;recorder.start(1000);startedAt=Date.now();$('#recording').classList.add('show');$('#stop').disabled=false;timer=setInterval(tick,250);if($('#script').value.trim()&&!promptPlaying)togglePrompt();status('Recording…')}
function stop(){if(recorder&&recorder.state!=='inactive')recorder.stop();clearInterval(timer);$('#recording').classList.remove('show');$('#stop').disabled=true;if(promptPlaying)togglePrompt();status('Saving recording locally…')}
async function upload(){const type=recorder.mimeType||chunks[0]?.type||'video/webm',blob=new Blob(chunks,{type}),name=$('#name').value||'capture';const response=await fetch('/api/upload?name='+encodeURIComponent(name),{method:'POST',headers:{'Content-Type':type},body:blob});const result=await response.json();if(!response.ok){status(result.error||'Upload failed');$('#start').disabled=false;return}status('Saved: '+result.path+(result.warning?' · '+result.warning:''));$('#start').disabled=false;chunks=[]}
function tick(){const s=Math.floor((Date.now()-startedAt)/1000);$('#timer').textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}
function countdown(){return new Promise(async resolve=>{const el=$('#countdown');el.classList.add('show');for(const n of [3,2,1]){el.textContent=n;await new Promise(r=>setTimeout(r,700))}el.classList.remove('show');resolve()})}
function togglePrompt(){promptPlaying=!promptPlaying;$('#promptctl').textContent=promptPlaying?'Pause prompt':'Play prompt';promptLast=performance.now();if(promptPlaying)raf=requestAnimationFrame(step);else cancelAnimationFrame(raf)}
function step(now){const dt=Math.min(.05,(now-promptLast)/1000);promptLast=now;promptY-=(+$('#speed').value)*dt;$('#prompt').style.transform=`translateY(${promptY}px)`;const limit=-$('#prompt').scrollHeight-200;if(promptY<limit){promptPlaying=false;$('#promptctl').textContent='Play prompt';return}raf=requestAnimationFrame(step)}
function resetPrompt(){promptY=$('.prompt').clientHeight;$('#prompt').style.transform=`translateY(${promptY}px)`;$('#prompt').textContent=$('#script').value}
function status(t){$('#status').textContent=t}boot().then(resetPrompt).catch(e=>status('Camera error: '+e.message));
</script></body></html>'''

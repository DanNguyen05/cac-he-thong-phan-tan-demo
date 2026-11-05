"""Always-on local gateway and OS-process supervisor (not a protocol participant)."""
import asyncio
import json
import os
import subprocess
import sys
import secrets
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import BASE, COORDINATOR_URL, NODES, SCENARIOS
from backend.storage import DATA, event, initialize_journal, read_journal
from backend import http_local

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = os.environ.get("LAB_PUBLIC", "false").lower() == "true"
GATEWAY_TOKEN = os.environ.get("LAB_GATEWAY_TOKEN", "")
INTERNAL_TOKEN = os.environ.get("LAB_INTERNAL_TOKEN") or secrets.token_urlsafe(32)
DEFAULT_ORIGINS = "" if PUBLIC else "http://127.0.0.1:5173,http://localhost:5173"
ORIGINS = [value.strip() for value in os.environ.get("LAB_ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if value.strip()]
if PUBLIC and len(GATEWAY_TOKEN) < 32:
    raise RuntimeError("LAB_PUBLIC requires LAB_GATEWAY_TOKEN with at least 32 characters")
if "*" in ORIGINS:
    raise RuntimeError("Use explicit LAB_ALLOWED_ORIGINS, never wildcard origins")
os.environ["LAB_INTERNAL_TOKEN"] = INTERNAL_TOKEN
processes = {}
handles = {}
lifecycle_lock = asyncio.Lock()
targets = {"coordinator": (BASE + 1, "backend.coordinator:app"),
           **{name: (BASE + 101 + i, "backend.node:app") for i, name in enumerate("ABC")}}


def address(target):
    return COORDINATOR_URL if target == "coordinator" else NODES[target]


async def stop_process(target):
    proc = processes.get(target)
    if proc and proc.poll() is None:
        proc.kill()
        await asyncio.to_thread(proc.wait, timeout=5)
    handle = handles.pop(target, None)
    if handle:
        handle.close()


async def start_process(target):
    proc = processes.get(target)
    if proc and proc.poll() is None:
        return
    if target in handles:
        handles.pop(target).close()
    port, module = targets[target]
    env = {**os.environ, "LAB_NODE": target, "LAB_DATA": str(DATA), "PYTHONUNBUFFERED": "1"}
    log_dir = DATA / "process-logs"
    log_dir.mkdir(exist_ok=True)
    handles[target] = open(log_dir / f"{target}.log", "a", encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    processes[target] = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=handles[target], stderr=subprocess.STDOUT, creationflags=flags)
    for _ in range(100):
        if processes[target].poll() is not None:
            raise RuntimeError(f"{target} exited; see {log_dir / (target + '.log')}")
        try:
            response = await http_local.client().get(address(target) + "/health", timeout=0.5)
            response.raise_for_status()
            # Do not mistake an unrelated server on the port for our child.
            if response.json().get("pid") != processes[target].pid:
                raise RuntimeError(f"Port for {target} is already in use")
            return
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
    raise RuntimeError(f"Timed out starting {target}")


@asynccontextmanager
async def lifespan(app):
    initialize_journal()
    http_local.start()
    try:
        for target in targets:
            await start_process(target)
        yield
    finally:
        for target in targets:
            await stop_process(target)
        await http_local.stop()


app = FastAPI(title="Distributed Systems · Fault Tolerance Lab", lifespan=lifespan)


@app.middleware("http")
async def access_control(request: Request, call_next):
    path = request.url.path
    if path.startswith("/internal/") and PUBLIC:
        if not secrets.compare_digest(request.headers.get("X-Lab-Internal-Token", ""), INTERNAL_TOKEN):
            return JSONResponse({"detail": "Private supervisor callback"}, status_code=403)
    elif PUBLIC and path not in ("/healthz", "/readyz"):
        if not secrets.compare_digest(request.headers.get("X-Lab-Gateway-Token", ""), GATEWAY_TOKEN):
            return JSONResponse({"detail": "Authenticated gateway required"}, status_code=401)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/") and origin not in ORIGINS:
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


# CORS wraps authentication so preflight works and denied requests remain readable.
if ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/healthz")
async def liveness():
    return {"status": "ok"}


@app.get("/readyz")
async def readiness():
    ready = all(processes.get(name) and processes[name].poll() is None for name in targets)
    return JSONResponse({"status": "ready" if ready else "degraded"}, status_code=200 if ready else 503)


@app.get("/api/health")
async def health():
    return {"service": "supervisor", "pid": os.getpid(), "processes": {
        target: {"alive": bool(processes.get(target) and processes[target].poll() is None),
                 "pid": processes[target].pid if processes.get(target) else None,
                 "port": targets[target][0]} for target in targets}}


@app.get("/api/catalog")
async def catalog():
    return SCENARIOS


async def snapshot():
    result = read_journal()
    result["services"] = (await health())["processes"]
    async def get_node(name):
        try:
            response = await http_local.client().get(NODES[name] + "/state", timeout=0.4)
            response.raise_for_status()
            return name, response.json()
        except httpx.HTTPError:
            proc = processes.get(name)
            return name, {"node": name, "available": False, "unreachable": True,
                          "crashed": not bool(proc and proc.poll() is None)}
    result["nodes"] = dict(await asyncio.gather(*(get_node(name) for name in NODES)))
    return result


@app.get("/api/state")
async def state():
    return await snapshot()


@app.get("/api/events")
async def events(request: Request):
    async def stream():
        while not await request.is_disconnected():
            yield "event: snapshot\ndata: " + json.dumps(await snapshot(), ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.45)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def proxy(path, body=None):
    try:
        response = await http_local.client().post(COORDINATOR_URL + path, json=body or {}, timeout=20)
        if response.is_error:
            raise HTTPException(response.status_code, response.json().get("detail", response.text))
        return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Coordinator chưa hoạt động. Hãy khởi động lại và phục hồi.") from exc


@app.post("/api/runs")
async def run(body: dict):
    async with lifecycle_lock:
        # Refuse to mutate nodes while a scenario is executing or a decision is uncertain.
        journal = read_journal()
        if journal["run"] and journal["run"]["status"] in ("RUNNING", "WAITING", "BLOCKED", "DECISION_PENDING", "INTERRUPTED"):
            raise HTTPException(409, "Kịch bản chưa kết thúc. Tiếp tục/phục hồi hoặc reset phòng lab.")
        for target in targets:
            await start_process(target)
        return await proxy("/runs", body)


@app.post("/api/control")
async def runtime_control(body: dict):
    return await proxy("/control", body)


@app.post("/api/step")
async def step():
    return await proxy("/step")


@app.post("/api/reset")
async def reset():
    async with lifecycle_lock:
        for target in targets:
            await start_process(target)
        return await proxy("/reset")


@app.post("/api/resolve")
async def resolve():
    async with lifecycle_lock:
        for target in targets:
            await start_process(target)
        return await proxy("/resolve")


async def action(target, operation, record=True, expected_run=None):
    if target not in targets or operation not in ("crash", "restart", "unavailable", "available"):
        raise HTTPException(422, "Unknown process/action")
    async with lifecycle_lock:
        journal = read_journal()
        if expected_run is not None and (not journal["run"] or journal["run"]["id"] != expected_run
                                         or journal["run"]["status"] not in ("RUNNING", "WAITING")):
            raise HTTPException(409, "Stale scenario callback rejected after reset or completion")
        rid = journal["run"]["id"] if journal["run"] else "manual"
        if record:
            event(rid, "Supervisor", target, "PROCESS_" + operation.upper(), f"Lệnh người dùng: {operation} {target}")
        if operation == "crash":
            await stop_process(target)
            if target == "coordinator" and journal["run"] and journal["run"]["status"] in ("RUNNING", "WAITING"):
                from backend.storage import set_run
                set_run(rid, "INTERRUPTED", {"explanation": "Coordinator bị dừng thủ công. Giao dịch PREPARED cần phục hồi; các kịch bản khác cần reset."})
        elif operation == "restart":
            await stop_process(target)
            await start_process(target)
        else:
            if target == "coordinator":
                raise HTTPException(422, "Use crash/restart for coordinator")
            try:
                response = await http_local.client().post(address(target) + "/availability", json={"available": operation == "available"}, timeout=2)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise HTTPException(503, "Node đã crash; cần restart trước") from exc
    return {"target": target, "action": operation}


@app.post("/api/process/{target}/{operation}")
async def process_control(target: str, operation: str):
    if PUBLIC and os.environ.get("LAB_ALLOW_PROCESS_CONTROL", "false").lower() != "true":
        raise HTTPException(403, "Manual process controls are disabled for this deployment")
    return await action(target, operation)


@app.post("/internal/process/{target}/{operation}")
async def internal_process_control(target: str, operation: str, body: dict):
    if not body.get("run_id"):
        raise HTTPException(422, "Internal lifecycle callback requires run_id")
    return await action(target, operation, record=False, expected_run=body["run_id"])


DIST = ROOT / "frontend" / "dist"
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse(DIST / "index.html")


    @app.get("/{path:path}")
    async def spa(path: str):
        if path.split("/")[0] in ("api", "internal", "assets") or Path(path).suffix:
            raise HTTPException(404, "Not found")
        return FileResponse(DIST / "index.html")

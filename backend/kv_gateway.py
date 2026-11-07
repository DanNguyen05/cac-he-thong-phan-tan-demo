"""Independent web gateway, HTTP scenario client and durable event collector.

Does not spawn/stop containers or read any other service's SQLite database.
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.kv_common import COORDINATOR, PEERS, RPC_SERVER, db, emit, events, health, init_events, record

URLS = {"coordinator": COORDINATOR, "rpc": RPC_SERVER, **PEERS}
CATALOG = {
    "rpc": [("normal", "RPC bình thường", "HTTP INCREMENT counter +1"), ("lost_request", "Mất yêu cầu", "Ứng dụng loại request trước HTTP"), ("lost_response", "Mất phản hồi + retry", "Server ghi bền vững; client bỏ response và retry cùng ID"), ("server_down", "RPC Server crash thật", "Run chờ bạn dừng container rpc bằng CLI"), ("duplicate", "Gửi trùng request", "Hai HTTP request cùng ID")],
    "group": [("normal", "Multicast #1, #2, #3", "FIFO delivery tại ba receiver"), ("lost_message", "B mất #2 → NACK → truyền lại", "B giữ #3 tới khi nhận #2"), ("node_down", "Receiver B dừng thật", "Dừng B trước khi chạy; dùng Catch-up sau restart"), ("duplicate", "Gửi lặp #2", "Nhận lại không deliver trùng")],
    "commit": [("normal", "Chuyển 10: A → B", "C lưu transaction ID"), ("vote_no", "B bỏ phiếu NO", "ABORT không thay đổi KV"), ("coordinator_crash", "Dừng sau PREPARED", "Chưa có durable decision; Docker stop coordinator"), ("coordinator_after_commit", "Dừng sau durable COMMIT", "A COMMIT, B/C chờ; replay COMMIT sau restart"), ("participant_prepared", "Participant dừng khi PREPARED", "Dừng B rồi Bước tiếp, restart B để nhận quyết định")],
    "recovery": [("normal", "Checkpoint 100 → ghi log → 95", "Đọc KV trực tiếp"), ("checkpoint", "Tạo checkpoint 100", "Snapshot cục bộ"), ("crash_recover", "Crash container → recovery 95", "Run chờ Docker kill/start participant-a"), ("idempotent", "Crash + replay nhiều lần", "Replay từ checkpoint; kết quả vẫn 95")],
}
client = None
task = None
collector = None
gate = asyncio.Event()
run_lock = asyncio.Lock()
poll_lock = asyncio.Lock()
latest = {}
live = {}
active_control = {"mode": "auto", "paused": False, "pace_ms": 100}


def current_run():
    with db() as conn:
        row = conn.execute("SELECT * FROM lab_runs ORDER BY created DESC LIMIT 1").fetchone()
        return {**dict(row), "config": json.loads(row["config"]), "result": json.loads(row["result"]) if row["result"] else None} if row else None


def set_run(rid, status, result=None):
    with db() as conn:
        if result is None:
            conn.execute("UPDATE lab_runs SET status=? WHERE id=?", (status, rid))
        else:
            conn.execute("UPDATE lab_runs SET status=?,result=? WHERE id=?", (status, json.dumps(result), rid))


async def call(target, path, body=None, method="POST", timeout=2):
    try:
        response = await client.request(method, URLS[target] + path, json=body if method != "GET" else None, timeout=timeout)
        if response.is_error:
            raise HTTPException(response.status_code, response.json().get("detail", response.text))
        return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"HTTP unavailable: {target}") from exc


async def poll():
    async with poll_lock:
        async def fetch(name):
            try:
                data = await call(name, "/state", method="GET", timeout=.5)
                old = latest.get(name)
                previous = live.get(name)
                latest[name] = data
                live[name] = {"alive": True, "pid": data["pid"], "boot_id": data["boot_id"], "port": int(URLS[name].rsplit(":", 1)[1]), "observed_at": time.time(), "runtime": data["runtime"]}
                if previous and (not previous["alive"] or old and old["boot_id"] != data["boot_id"]):
                    record((current_run() or {}).get("id", "manual"), "RESTART", name, detail="New boot ID observed via HTTP", boot_id=data["boot_id"])
                with db() as conn:
                    for event in data["events"]:
                        cursor = conn.execute("INSERT OR IGNORE INTO ingested VALUES(?,?)", (name, event["seq"]))
                        if cursor.rowcount:
                            conn.execute("INSERT INTO journal(time,run_id,source,target,kind,detail,data) VALUES(?,?,?,?,?,?,?)", (event["time"], event["run_id"], event["source"], event["target"], event["kind"], event["detail"], json.dumps({**event["data"], "service": name, "service_seq": event["seq"]})))
            except HTTPException:
                previous = live.get(name)
                live[name] = {"alive": False, "pid": None, "port": int(URLS[name].rsplit(":", 1)[1]), "observed_at": time.time(), "runtime": os.environ.get("KV_RUNTIME", "process")}
                if previous and previous["alive"]:
                    record((current_run() or {}).get("id", "manual"), "HEALTH_DOWN", name, detail="HTTP unreachable; use Docker CLI to confirm container status")
        await asyncio.gather(*(fetch(name) for name in URLS))


def verify_tx(tx):
    checks = {}
    for node in PEERS:
        observed = latest.get(node, {}).get("kv", {}) if live.get(node, {}).get("alive") else {}
        expected = tx["writes"][node] if tx["decision"] == "COMMIT" else {key: tx["before_values"][node].get(key) for key in tx["writes"][node]}
        checks[node] = {"expected": expected, "actual": {key: observed.get(key) for key in expected}, "ok": all(observed.get(key) == val for key, val in expected.items()) and bool(live.get(node, {}).get("alive"))}
    return {"verified": all(check["ok"] for check in checks.values()), "checks": checks}


async def snapshot():
    await poll()
    run = current_run()
    txs = latest.get("coordinator", {}).get("transactions", [])
    tx = next((t for t in txs if run and t["run_id"] == run["id"]), None)
    if run and run["module"] == "commit":
        if not live.get("coordinator", {}).get("alive"):
            prepared = any(any(t["run_id"] == run["id"] and t["state"] == "PREPARED" for t in latest.get(n, {}).get("transactions", [])) for n in PEERS if live.get(n, {}).get("alive"))
            set_run(run["id"], "BLOCKED" if prepared else "INTERRUPTED")
        elif tx:
            if tx["phase"] == "COMPLETE":
                verification = verify_tx(tx)
                set_run(run["id"], "COMPLETED" if verification["verified"] else "DECISION_PENDING", {"transaction_id": tx["id"], "decision": tx["decision"], "before": tx["before_values"], **verification})
            else:
                waiting = latest["coordinator"].get("waiting", False)
                set_run(run["id"], "WAITING" if waiting else "DECISION_PENDING" if tx["phase"] == "DECISION_PENDING" else "RUNNING", {"transaction_id": tx["id"], "phase": tx["phase"], "decision": tx["decision"], "verified": False})
            if latest["coordinator"].get("control"):
                run["config"].update(latest["coordinator"]["control"])
        updated = current_run()
        if updated:
            updated["config"].update(run["config"])
            run = updated
    nodes = {}
    for name in [*PEERS, "rpc"]:
        if live.get(name, {}).get("alive"):
            nodes[name] = {key: val for key, val in latest[name].items() if key != "events"}
        else:
            nodes[name] = {"node": name, "available": False, "unreachable": True, "last_known": {key: val for key, val in latest.get(name, {}).items() if key != "events"}}
    # Existing React components consume these fields; KV specifics are additive.
    if run and run["module"] == "group":
        for name in PEERS:
            nodes[name]["multicast"] = [row for row in nodes[name].get("group", []) if row["stream"] == run["id"] and row["delivered"]]
    normalized = [{**tx, "state": tx["decision"] or "PREPARING", "acknowledgments": tx["acks"], "last_known": not live.get("coordinator", {}).get("alive")} ] if tx else []
    journal = [e for e in events() if run and e["run_id"] == run["id"]]
    return {"run": run, "events": journal[-1200:], "nodes": nodes, "services": live, "transactions": normalized,
            "runtime": {"mode": "kv", "containerized": os.environ.get("KV_RUNTIME") == "docker", "services": len(URLS), "gateway": health(), "name": "Distributed KV Transaction Lab", "fault_layer": "application transport / external Docker CLI"}}


async def collect():
    while True:
        try:
            await poll()
        except Exception as exc:
            record("system", "COLLECTOR_ERROR", detail=str(exc))
        await asyncio.sleep(.5)


@asynccontextmanager
async def lifespan(app):
    global client, collector
    init_events()
    with db() as conn:
        conn.executescript("CREATE TABLE IF NOT EXISTS lab_runs(id TEXT PRIMARY KEY,module TEXT,scenario TEXT,status TEXT,config TEXT,result TEXT,created REAL); CREATE TABLE IF NOT EXISTS ingested(service TEXT,seq INTEGER,PRIMARY KEY(service,seq)); CREATE TABLE IF NOT EXISTS history(stream TEXT,seq INTEGER,payload TEXT,PRIMARY KEY(stream,seq));")
        conn.execute("UPDATE lab_runs SET status='INTERRUPTED' WHERE module!='commit' AND status IN ('RUNNING','WAITING')")
    client = httpx.AsyncClient(trust_env=False, limits=httpx.Limits(max_connections=40))
    collector = asyncio.create_task(collect())
    yield
    for job in [collector, task]:
        if job and not job.done():
            job.cancel()
            try:
                await job
            except asyncio.CancelledError:
                pass
    await client.aclose()


app = FastAPI(title="Distributed KV Transaction Lab", lifespan=lifespan)
ORIGINS = [origin.strip() for origin in os.environ.get("KV_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if origin.strip()]
if "*" in ORIGINS:
    raise RuntimeError("Use explicit KV_ALLOWED_ORIGINS")
app.get("/health")(health)
app.get("/healthz")(health)


@app.middleware("http")
async def local_access(request: Request, call_next):
    # Compose publishes loopback only. No Docker socket or executable command API.
    origin = request.headers.get("origin")
    if request.method not in ["GET", "HEAD", "OPTIONS"] and origin and origin != str(request.base_url).rstrip("/") and origin not in ORIGINS:
        return JSONResponse({"detail": "Cross-origin mutation denied"}, status_code=403)
    return await call_next(request)


if ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.get("/api/health")
async def api_health():
    await poll()
    return {**health(), "processes": live}


@app.get("/api/catalog")
def catalog():
    return CATALOG


app.get("/api/state")(snapshot)


@app.get("/api/events")
async def sse(request: Request):
    async def stream():
        while not await request.is_disconnected():
            yield "event: snapshot\ndata: " + json.dumps(await snapshot()) + "\n\n"
            await asyncio.sleep(.45)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class RunConfig(BaseModel):
    module: Literal["rpc", "group", "commit", "recovery"]
    scenario: str = "normal"
    mode: Literal["auto", "step"] = "auto"
    pace_ms: int = Field(100, ge=0, le=3000)
    target: Literal["A", "B", "C"] = "B"
    deduplicate: bool = True
    retry: bool = True
    max_attempts: int = Field(3, ge=1, le=5)
    delay_ms: int = Field(0, ge=0, le=1500)
    paused: bool = False


async def boundary(rid, description):
    await asyncio.sleep(active_control["pace_ms"] / 1000)
    if active_control["mode"] == "step" or active_control["paused"]:
        gate.clear()
        set_run(rid, "WAITING")
        record(rid, "STEP_READY", detail=description)
        await gate.wait()
    set_run(rid, "RUNNING")


async def rpc_request(rid, body, cfg):
    try:
        before = await call("rpc", "/kv/" + body["key"], method="GET") if body["operation"] == "INCREMENT" else None
    except HTTPException:
        record(rid, "TIMEOUT", "rpc", source="Client", request_id=body["id"], detail="RPC server unavailable on initial HTTP GET")
        raise
    started = time.monotonic()
    attempts = cfg.max_attempts if cfg.retry else 1
    for attempt in range(1, attempts + 1):
        await boundary(rid, "RPC attempt " + str(attempt))
        record(rid, "SEND", "rpc", source="Client", path="/kv", operation_id=body["id"], attempt=attempt, request=body)
        try:
            async with asyncio.timeout(.8):
                if attempt == 1 and cfg.scenario == "lost_request":
                    record(rid, "REQUEST_LOST", "rpc", source="Client", request_id=body["id"], detail="Application transport dropped request before HTTP")
                    await asyncio.sleep(2)
                result = await call("rpc", "/kv", {**body, "run_id": rid, "deduplicate": cfg.deduplicate}, timeout=.7)
                if attempt == 1 and cfg.scenario == "duplicate":
                    result = await call("rpc", "/kv", {**body, "run_id": rid, "deduplicate": cfg.deduplicate})
                if attempt == 1 and cfg.scenario == "lost_response":
                    record(rid, "RESPONSE_LOST", "Client", source="rpc", request_id=body["id"], detail="HTTP response discarded by application fault layer after server durable execution")
                    await asyncio.sleep(2)
                record(rid, "ACK", "Client", source="rpc", path="/kv", operation_id=body["id"], attempt=attempt, response=result)
                after = await call("rpc", "/kv/" + body["key"], method="GET")
                await poll()
                executions = len([e for e in latest["rpc"]["events"] if e["kind"] == "RPC_EXECUTED" and e["data"].get("request_id") == body["id"]])
                return {"request_id": body["id"], "attempts": attempt, "actual_executions": executions, "before": before["value"] if before else result["before"], "after": after["value"], "result": result, "elapsed_ms": round((time.monotonic() - started) * 1000), "verified": after["value"] == result["value"]}
        except (TimeoutError, HTTPException) as exc:
            record(rid, "TIMEOUT", "rpc", source="Client", request_id=body["id"], attempt=attempt, detail=str(exc))
            if attempt < attempts:
                record(rid, "RETRY", "rpc", source="Client", request_id=body["id"], attempt=attempt + 1)
    raise HTTPException(503, "RPC failed after retry budget")


async def send_group(rid, node, seq, cfg, retransmit=False, scheduled=True):
    with db() as conn:
        payload = conn.execute("SELECT payload FROM history WHERE stream=? AND seq=?", (rid, seq)).fetchone()
    if not payload:
        raise HTTPException(409, "Message no longer in history")
    if scheduled:
        await boundary(rid, f"Multicast #{seq} -> {node}")
    record(rid, "RETRANSMIT" if retransmit else "SEND", node, source="Sender", path="/multicast", stream=rid, sequence=seq, operation_id=f"{rid}:{seq}")
    result = await call(node, "/multicast", {"stream": rid, "run_id": rid, "seq": seq, "payload": payload[0]}, timeout=1)
    if result["missing"]:
        record(rid, "NACK", "Sender", source=node, stream=rid, missing=result["missing"])
        for missing in result["missing"]:
            await send_group(rid, node, missing, cfg, retransmit=True, scheduled=scheduled)
    else:
        record(rid, "ACK", "Sender", source=node, stream=rid, sequence=seq)
    return result


async def group_demo(rid, cfg):
    with db() as conn:
        conn.executemany("INSERT INTO history VALUES(?,?,?)", [(rid, seq, f"Message #{seq}") for seq in [1, 2, 3]])
    for seq in [1, 2, 3]:
        for node in PEERS:
            if cfg.scenario == "lost_message" and seq == 2 and node == cfg.target:
                record(rid, "REQUEST_LOST", node, source="Sender", stream=rid, sequence=seq, detail="Application fault drops only message #2; #3 will expose sequence gap")
                continue
            try:
                await send_group(rid, node, seq, cfg)
                if cfg.scenario == "duplicate" and seq == 2 and node == cfg.target:
                    await send_group(rid, node, seq, cfg)
            except HTTPException:
                record(rid, "TIMEOUT", node, stream=rid, sequence=seq)
    return await group_verify(rid)


async def group_verify(rid):
    await poll()
    delivered = {name: [row["seq"] for row in latest.get(name, {}).get("group", []) if row["stream"] == rid and row["delivered"]] if live.get(name, {}).get("alive") else [] for name in PEERS}
    return {"stream": rid, "delivered": delivered, "verified": all(seqs == [1, 2, 3] for seqs in delivered.values()), "missing_nodes": [name for name, seqs in delivered.items() if seqs != [1, 2, 3]]}


async def recovery_demo(rid, cfg):
    await boundary(rid, "Initialize inventory=100")
    await call("A", "/recovery/setup", {"run_id": rid})
    await boundary(rid, "Checkpoint inventory=100")
    cp = await call("A", "/checkpoint", {"run_id": rid})
    if cfg.scenario == "checkpoint":
        return {"before": 100, "after": 100, "checkpoint": cp, "verified": (await call("A", "/kv/inventory", method="GET"))["value"] == 100}
    for index, delta in [(1, -3), (2, -2)]:
        await boundary(rid, f"Write redo {delta}")
        await call("A", "/operations", {"id": rid + str(index), "run_id": rid, "delta": delta})
    before = await call("A", "/state", method="GET")
    if cfg.scenario in ["crash_recover", "idempotent"]:
        set_run(rid, "WAITING", {"stage": "AWAIT_CONTAINER_RESTART", "before": 95, "before_boot": before["boot_id"], "command": "docker compose -p kv-transaction-lab kill -s SIGKILL participant-a; docker compose -p kv-transaction-lab start participant-a"})
        record(rid, "STEP_READY", "A", detail="Await real container/process restart; no simulated crash")
        while True:
            await asyncio.sleep(.3)
            try:
                after = await call("A", "/state", method="GET", timeout=.4)
                if after["boot_id"] != before["boot_id"]:
                    break
            except HTTPException:
                pass
        report = after["recovery"]
        record(rid, "RECOVERY", "A", detail="Recovered state read by HTTP after different boot ID", **report)
    if cfg.scenario == "idempotent":
        await call("A", "/recover", {"run_id": rid})
        duplicate = await call("A", "/operations", {"id": rid + "2", "run_id": rid, "delta": -2})
        record(rid, "IDEMPOTENCE", "A", response=duplicate)
    actual = await call("A", "/kv/inventory", method="GET")
    return {"before": 100, "after": actual["value"], "checkpoint": cp, "verified": actual["value"] == 95}


async def execute(rid, cfg):
    try:
        if cfg.module == "rpc":
            if cfg.scenario == "server_down":
                set_run(rid, "WAITING", {"stage": "AWAIT_RPC_STOP", "command": "docker compose -p kv-transaction-lab stop rpc"})
                while True:
                    try:
                        await call("rpc", "/health", method="GET", timeout=.3)
                    except HTTPException:
                        break
                    await asyncio.sleep(.3)
            result = await rpc_request(rid, {"id": "req-" + rid, "operation": "INCREMENT", "key": "counter", "value": 1}, cfg)
        elif cfg.module == "group":
            if cfg.scenario == "node_down":
                set_run(rid, "WAITING", {"stage": "AWAIT_RECEIVER_STOP", "target": cfg.target, "command": f"docker compose -p kv-transaction-lab stop participant-{cfg.target.lower()}"})
                while True:
                    try:
                        await call(cfg.target, "/health", method="GET", timeout=.3)
                    except HTTPException:
                        break
                    await asyncio.sleep(.3)
                set_run(rid, "RUNNING", {"stage": "MULTICAST", "target": cfg.target, "verified": False})
            result = await group_demo(rid, cfg)
        else:
            result = await recovery_demo(rid, cfg)
        set_run(rid, "COMPLETED" if result["verified"] else "PARTIAL", result)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        record(rid, "ERROR", detail=str(exc))
        set_run(rid, "FAILED", {"error": str(exc), "verified": False})


@app.post("/api/runs")
async def run(cfg: RunConfig):
    global task, active_control
    async with run_lock:
        current = (await snapshot())["run"]
        if current and current["status"] in ["RUNNING", "WAITING", "BLOCKED", "DECISION_PENDING"]:
            raise HTTPException(409, "Finish or recover current experiment first")
        if cfg.scenario not in [entry[0] for entry in CATALOG[cfg.module]]:
            raise HTTPException(422, "Unknown scenario")
        rid = uuid4().hex
        with db() as conn:
            conn.execute("INSERT INTO lab_runs VALUES(?,?,?,'RUNNING',?,NULL,?)", (rid, cfg.module, cfg.scenario, cfg.model_dump_json(), time.time()))
        active_control = {"mode": cfg.mode, "paused": False, "pace_ms": cfg.pace_ms}
        record(rid, "START", module=cfg.module, scenario=cfg.scenario)
        if cfg.module == "commit":
            try:
                await call("coordinator", "/transactions", {"id": "tx-" + rid, "run_id": rid, "scenario": cfg.scenario, "target": cfg.target, "mode": cfg.mode, "pace_ms": cfg.pace_ms})
            except HTTPException:
                set_run(rid, "FAILED", {"verified": False})
                raise
        else:
            task = asyncio.create_task(execute(rid, cfg))
        return {"id": rid}


@app.post("/api/step")
async def step():
    run = current_run()
    if not run or run["status"] != "WAITING":
        raise HTTPException(409, "No waiting operation")
    if run["module"] == "commit":
        return await call("coordinator", "/step")
    gate.set()
    return {"step": True}


@app.post("/api/control")
async def control(body: dict):
    run = current_run()
    if not run:
        raise HTTPException(409, "No run")
    if run["module"] == "commit":
        return await call("coordinator", "/control", body)
    for key in ["paused", "pace_ms"]:
        if key in body:
            if key == "pace_ms" and (not isinstance(body[key], int) or not 0 <= body[key] <= 3000):
                raise HTTPException(422, "Invalid pace")
            active_control[key] = body[key]
    if not active_control["paused"]:
        gate.set()
    with db() as conn:
        conn.execute("UPDATE lab_runs SET config=? WHERE id=?", (json.dumps({**run["config"], **active_control}), run["id"]))
    return active_control


@app.post("/api/group/catchup")
async def catchup(body: dict):
    rid = body.get("stream") or (current_run() or {}).get("id")
    node = body.get("target", "B")
    if node not in PEERS:
        raise HTTPException(422, "Unknown recipient")
    with db() as conn:
        seqs = [row[0] for row in conn.execute("SELECT seq FROM history WHERE stream=? ORDER BY seq", (rid,))]
    if not seqs:
        raise HTTPException(404, "No retained sender history")
    cfg = RunConfig(module="group", pace_ms=0)
    for seq in seqs:
        await send_group(rid, node, seq, cfg, retransmit=True, scheduled=False)
    result = await group_verify(rid)
    set_run(rid, "COMPLETED" if result["verified"] else "PARTIAL", result)
    return result


@app.post("/api/reset")
async def reset():
    global task
    async with run_lock:
        # No implicit restart, no deletion of Docker volumes, no reset of in-doubt tx.
        await poll()
        if not all(live.get(name, {}).get("alive") for name in URLS):
            raise HTTPException(503, "Start all services before resetting; no data was erased")
        if any(latest.get(name, {}).get("locks") for name in PEERS):
            raise HTTPException(409, "Prepared locks exist; recover the coordinator first")
        await call("coordinator", "/reset")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for name in [*PEERS, "rpc"]:
            await call(name, "/reset")
        with db() as conn:
            conn.execute("DELETE FROM lab_runs")
            conn.execute("DELETE FROM history")
        return {"reset": True, "volumes_deleted": False}


@app.post("/api/resolve")
async def resolve():
    data = await call("coordinator", "/state", method="GET")
    return {"message": "Coordinator startup automatically recovers durable transactions; use Docker CLI if it is stopped", "transactions": data["transactions"]}


@app.get("/api/kv/{node}/{key}")
async def kv_get(node: str, key: str):
    if node not in URLS or node == "coordinator":
        raise HTTPException(422, "Unknown KV worker")
    return await call(node, "/kv/" + key, method="GET")


@app.post("/api/kv/{node}")
async def kv_put(node: str, body: dict):
    if node not in URLS or node == "coordinator":
        raise HTTPException(422, "Unknown KV worker")
    run = current_run()
    if run and run["status"] in ["RUNNING", "WAITING", "BLOCKED", "DECISION_PENDING"]:
        raise HTTPException(409, "Finish current scenario before manual writes")
    return await call(node, "/kv", {"id": uuid4().hex, **body})


@app.post("/api/transactions")
async def transaction(body: dict):
    async with run_lock:
        existing = (await snapshot())["run"]
        if existing and existing["status"] in ["RUNNING", "WAITING", "BLOCKED", "DECISION_PENDING"]:
            raise HTTPException(409, "Finish current experiment first")
        rid = uuid4().hex
        cfg = RunConfig(module="commit", scenario=body.get("scenario", "normal"), mode=body.get("mode", "auto"), pace_ms=body.get("pace_ms", 100), target=body.get("target", "B"))
        with db() as conn:
            conn.execute("INSERT INTO lab_runs VALUES(?,?,?,'RUNNING',?,NULL,?)", (rid, "commit", cfg.scenario, cfg.model_dump_json(), time.time()))
        try:
            result = await call("coordinator", "/transactions", {**body, "run_id": rid})
        except HTTPException:
            set_run(rid, "FAILED", {"verified": False})
            raise
        # A retried existing transaction retains its original run correlation.
        if result["run_id"] != rid:
            with db() as conn:
                conn.execute("DELETE FROM lab_runs WHERE id=?", (rid,))
        return result


@app.get("/api/transactions/{tid}")
async def transaction_status(tid: str):
    return await call("coordinator", "/transactions/" + tid, method="GET")


@app.post("/api/process/{target}/{operation}")
def no_container_control(target: str, operation: str):
    raise HTTPException(403, "Docker lifecycle is local CLI only; dashboard has no Docker socket")


DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.split("/")[0] in ["api", "assets"] or Path(path).suffix:
            raise HTTPException(404, "Not found")
        return FileResponse(DIST / "index.html")

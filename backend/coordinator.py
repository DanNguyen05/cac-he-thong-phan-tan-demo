"""Protocol engine, separately killable from the gateway and participants."""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.config import MANAGER_URL, NODES, PACE, SCENARIOS
from backend.storage import connect, event, initialize_journal, read_journal, set_run
from backend.transport import DeliveryError, Transport
from backend import http_local

active_config = None
task = None
gate = asyncio.Semaphore(0)
active_id = None
control_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app):
    initialize_journal()
    http_local.start()
    with connect("coordinator") as db:
        db.execute("UPDATE runs SET status='INTERRUPTED' WHERE status IN ('RUNNING','WAITING')")
    yield
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await http_local.stop()


app = FastAPI(title="Fault Tolerance · Coordinator", lifespan=lifespan)


class RunConfig(BaseModel):
    module: Literal["rpc", "group", "commit", "recovery"]
    scenario: str = "normal"
    mode: Literal["auto", "step"] = "auto"
    deduplicate: bool = True
    retry: bool = True
    max_attempts: int = Field(3, ge=1, le=5)
    target: Literal["A", "B", "C"] = "B"
    delay_ms: int = Field(0, ge=0, le=1500)
    pace_ms: int = Field(int(PACE * 1000), ge=0, le=3000)
    paused: bool = False


async def checkpoint_step(run_id, config, description):
    # Scheduling only: pause at an action boundary, never in the middle of a write.
    if config.mode != "step" and not config.paused:
        await asyncio.sleep(config.pace_ms / 1000)
    if config.mode == "step" or config.paused:
        set_run(run_id, "WAITING")
        event(run_id, "Coordinator", "", "STEP_READY", description)
        await gate.acquire()
    set_run(run_id, "RUNNING")
    event(run_id, "Coordinator", "", "STEP", description)


async def administrative(target, path, body=None):
    response = await http_local.client().post(NODES[target] + path, json=body or {}, timeout=10)
    response.raise_for_status()
    return response.json()


async def process_action(run_id, target, action):
    # Manager supervises real OS processes. The protocol process cannot restart itself.
    event(run_id, "Supervisor", target, "PROCESS_" + action.upper(), f"{action.upper()} tiến trình {target}")
    response = await http_local.client().post(MANAGER_URL + f"/internal/process/{target}/{action}",
                                              json={"run_id": run_id}, headers={"X-Lab-Internal-Token": os.environ.get("LAB_INTERNAL_TOKEN", "")}, timeout=15)
    response.raise_for_status()
    return response.json()


async def rpc_demo(rid, config):
    transport = Transport(rid)
    request_id = "rpc-" + rid[:8]
    if config.scenario == "server_down":
        await administrative("A", "/availability", {"available": False})
        event(rid, "Supervisor", "A", "UNAVAILABLE", "Node A vẫn sống nhưng từ chối các yêu cầu giao thức")
    attempts = config.max_attempts if config.retry else 1
    for attempt in range(1, attempts + 1):
        await checkpoint_step(rid, config, f"Gửi RPC {request_id} · lần {attempt}")
        fault = {"lost_request": "drop_request", "lost_response": "drop_response", "duplicate": "duplicate"}.get(config.scenario) if attempt == 1 else None
        delay = (max(1000, config.delay_ms) if config.scenario == "delay" else config.delay_ms) if attempt == 1 else 0
        try:
            result = await transport.send("A", "/rpc", {"id": request_id, "deduplicate": config.deduplicate},
                                          attempt, fault, source="Client", delay_ms=delay)
            if result["duplicate"]:
                event(rid, "A", "Client", "DUPLICATE_SUPPRESSED", "Trả kết quả đã lưu, không thực thi lại", request_id=request_id)
            set_run(rid, "COMPLETED", {"request_id": request_id, "attempts": attempt, "result": result,
                                     "semantics": "at-most-once" if config.deduplicate else "at-least-once (nếu cuối cùng giao được)",
                                     "explanation": "Thử lại không bảo đảm exactly-once. Kết quả khử trùng lặp được lưu cùng thay đổi trong một giao dịch SQLite."})
            return
        except DeliveryError:
            if attempt < attempts:
                event(rid, "Client", "A", "RETRY", "Thử lại với cùng request ID", request_id=request_id, attempt=attempt + 1)
    set_run(rid, "FAILED", {"request_id": request_id, "attempts": attempts,
                            "explanation": "Đã hết lượt thử. Client không biết chắc thao tác có được thực thi hay không nếu phản hồi bị mất."})


async def group_demo(rid, config):
    transport = Transport(rid)
    mid = "multicast-" + rid[:8]
    acknowledgments = {}
    if config.scenario == "node_down":
        await administrative(config.target, "/availability", {"available": False})
    for attempt in range(1, config.max_attempts + 1):
        missing = [n for n in NODES if n not in acknowledgments]
        if not missing:
            break
        for node in missing:
            await checkpoint_step(rid, config, f"{'Multicast' if attempt == 1 else 'Truyền lại'} → Node {node} · lần {attempt}")
            fault = None
            if node == config.target and attempt == 1:
                fault = {"lost_message": "drop_request", "duplicate": "duplicate"}.get(config.scenario)
            if attempt > 1:
                event(rid, "Sender", node, "RETRANSMIT", "Chỉ gửi lại tới node chưa ACK", message_id=mid, attempt=attempt)
            try:
                acknowledgments[node] = await transport.send(node, "/multicast", {"id": mid}, attempt, fault, source="Sender", delay_ms=config.delay_ms if attempt == 1 else 0)
            except DeliveryError:
                pass
    missing = [n for n in NODES if n not in acknowledgments]
    set_run(rid, "PARTIAL" if missing else "COMPLETED", {"message_id": mid, "acknowledgments": acknowledgments,
            "missing": missing, "explanation": "Reliable multicast theo ACK + truyền lại hữu hạn, khử trùng lặp bền vững. Không có total order, view membership hay bảo đảm atomic agreement; node đã nhận không rollback khi node khác lỗi."})


def save_transaction(tid, rid, state, votes, acknowledgments=None):
    with connect("coordinator") as db:
        db.execute("INSERT INTO transactions VALUES(?,?,?,?,?,10) ON CONFLICT(id) DO UPDATE SET state=excluded.state,votes=excluded.votes,acknowledgments=excluded.acknowledgments",
                   (tid, rid, state, json.dumps(votes), json.dumps(acknowledgments or {})))


async def distribute_decision(rid, config, tid, decision, votes):
    transport = Transport(rid)
    acknowledgments = {}
    # Save the global decision BEFORE sending it to any participant.
    save_transaction(tid, rid, decision, votes)
    event(rid, "Coordinator", "Disk", "DURABLE_DECISION", f"{decision} đã ghi bền vững", transaction_id=tid, decision=decision)
    for node in NODES:
        for attempt in range(1, config.max_attempts + 1):
            await checkpoint_step(rid, config, f"{decision} → Participant {node}")
            try:
                acknowledgments[node] = await transport.send(node, "/decision", {"id": tid, "decision": decision}, attempt)
                save_transaction(tid, rid, decision, votes, acknowledgments)
                break
            except DeliveryError:
                if attempt < config.max_attempts:
                    event(rid, "Coordinator", node, "RETRY", "Gửi lại quyết định bền vững", transaction_id=tid, attempt=attempt + 1)
    pending = [n for n in NODES if n not in acknowledgments]
    set_run(rid, "DECISION_PENDING" if pending else "COMPLETED", {"transaction_id": tid, "decision": decision,
            "votes": votes, "acknowledgments": acknowledgments, "pending": pending,
            "explanation": "Quyết định đã bền vững. Node lỗi sẽ nhận cùng quyết định khi khởi động lại và gửi lại; áp dụng COMMIT là idempotent."})


async def commit_demo(rid, config):
    tid = "tx-" + rid[:8]
    votes = {}
    save_transaction(tid, rid, "PREPARING", votes)
    if config.scenario == "participant_crash":
        await checkpoint_step(rid, config, f"Dừng Participant {config.target} trước khi bỏ phiếu")
        await process_action(rid, config.target, "crash")
    transport = Transport(rid)
    for node in NODES:
        await checkpoint_step(rid, config, f"PREPARE → Participant {node}")
        try:
            response = await transport.send(node, "/prepare", {"id": tid, "amount": 10,
                                            "vote_no": config.scenario == "vote_no" and node == config.target}, delay_ms=config.delay_ms)
            votes[node] = response["vote"]
            event(rid, node, "Coordinator", "VOTE", f"VOTE {response['vote']} · trạng thái {response['state']}", transaction_id=tid, vote=response["vote"])
        except DeliveryError:
            votes[node] = "MISSING"
        save_transaction(tid, rid, "PREPARING", votes)
    if config.scenario == "coordinator_crash" and all(v == "YES" for v in votes.values()):
        await checkpoint_step(rid, config, "Crash Coordinator sau khi tất cả đã PREPARED, trước quyết định bền vững")
        set_run(rid, "BLOCKED", {"transaction_id": tid, "votes": votes,
                "explanation": "Coordinator đã chết. Participant PREPARED giữ tài nguyên và chờ; timeout không cho phép tự ABORT. Khởi động lại Coordinator rồi phục hồi quyết định."})
        event(rid, "Coordinator", "", "PROCESS_CRASH", "os._exit(86): Coordinator chết thật; các participant giữ PREPARED", transaction_id=tid)
        os._exit(86)
    decision = "COMMIT" if len(votes) == 3 and all(v == "YES" for v in votes.values()) else "ABORT"
    await distribute_decision(rid, config, tid, decision, votes)


async def recovery_demo(rid, config):
    transport = Transport(rid)
    for index in range(1, 3):
        await checkpoint_step(rid, config, f"Ghi operation {index}: +5 vào nhật ký Node A")
        operation = await transport.send("A", "/operation", {"id": f"{rid}-op-{index}", "delta": 5})
    if config.scenario == "normal":
        set_run(rid, "COMPLETED", {"value": operation["value"], "explanation": "Hai operation đã được ghi bền vững vào SQLite trước phản hồi."})
        return
    await checkpoint_step(rid, config, "Tạo checkpoint tại giá trị 10")
    cp = await transport.send("A", "/checkpoint", {})
    event(rid, "A", "Disk", "CHECKPOINT", f"Snapshot bền vững: value={cp['value']}, last sequence={cp['seq']}", checkpoint=cp)
    if config.scenario == "checkpoint":
        set_run(rid, "COMPLETED", {"checkpoint": cp, "explanation": "Snapshot chứa giá trị và sequence cuối, tạo nguyên tử cùng đọc trạng thái trong SQLite."})
        return
    for index, delta in [(3, 7), (4, 3)]:
        await checkpoint_step(rid, config, f"Sau checkpoint: operation {index}, +{delta}")
        await transport.send("A", "/operation", {"id": f"{rid}-op-{index}", "delta": delta})
    response = await http_local.client().get(NODES["A"] + "/state")
    response.raise_for_status()
    before = response.json()
    event(rid, "A", "", "BEFORE_CRASH", "Trạng thái trước crash lấy từ node", value=before["memory_value"], pid=before["pid"])
    await checkpoint_step(rid, config, "Crash tiến trình Node A, giữ nguyên ổ đĩa")
    await process_action(rid, "A", "crash")
    await checkpoint_step(rid, config, "Khởi động Node A: nạp checkpoint và redo các operation sau checkpoint")
    await process_action(rid, "A", "restart")
    response = await http_local.client().get(NODES["A"] + "/state")
    response.raise_for_status()
    after = response.json()
    report = after["recovery"]
    event(rid, "A", "", "RECOVERY", "Đã nạp snapshot và replay nhật ký theo sequence", **report)
    if config.scenario == "idempotent":
        await checkpoint_step(rid, config, "Replay lại và gửi trùng operation 4 để kiểm chứng idempotence")
        again = await transport.send("A", "/recover", {})
        duplicate = await transport.send("A", "/operation", {"id": f"{rid}-op-4", "delta": 3})
        event(rid, "A", "", "IDEMPOTENCE", "Khôi phục lần nữa từ snapshot; operation ID cũ bị bỏ qua", replay=again, duplicate=duplicate)
        response = await http_local.client().get(NODES["A"] + "/state")
        response.raise_for_status()
        after = response.json()
    verified = before["memory_value"] == after["memory_value"] == 20 and before["pid"] != after["pid"]
    set_run(rid, "COMPLETED" if verified else "FAILED", {"before": before["memory_value"], "after": after["memory_value"],
            "before_pid": before["pid"], "after_pid": after["pid"], "recovery": report,
            "explanation": "Logical redo logging cục bộ: snapshot (value, seq), nhật ký operation bền vững, replay phần seq lớn hơn checkpoint. Replay luôn bắt đầu từ snapshot; UNIQUE operation ID chống áp dụng lặp."})


async def execute(rid, config, resume=None):
    try:
        if resume:
            tid, decision, votes = resume
            await distribute_decision(rid, config, tid, decision, votes)
        else:
            await {"rpc": rpc_demo, "group": group_demo, "commit": commit_demo, "recovery": recovery_demo}[config.module](rid, config)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        event(rid, "Coordinator", "", "ERROR", f"{type(exc).__name__}: {exc}")
        set_run(rid, "FAILED", {"error": str(exc), "explanation": "Lỗi thực thi; kiểm tra timeline và trạng thái participant trước khi reset."})


@app.get("/health")
async def health():
    return {"pid": os.getpid(), "service": "coordinator"}


@app.post("/runs")
async def start(config: RunConfig):
    global task, gate, active_id, active_config
    async with control_lock:
        if config.scenario not in [s[0] for s in SCENARIOS[config.module]]:
            raise HTTPException(422, "Unknown scenario for this module")
        if task and not task.done():
            raise HTTPException(409, "Scenario already running")
        with connect("coordinator") as db:
            uncertain = db.execute("SELECT 1 FROM transactions WHERE state='PREPARING'").fetchone()
        journal = read_journal()
        if uncertain or (journal["run"] and journal["run"]["status"] == "DECISION_PENDING"):
            raise HTTPException(409, "Resolve transaction or explicitly reset the lab first")
        # The manager ensures crashed processes are restarted before this endpoint.
        for node in NODES:
            await administrative(node, "/reset")
        active_config = config
        active_id = uuid4().hex
        gate = asyncio.Semaphore(0)
        with connect("coordinator") as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (active_id, config.module, config.scenario,
                       "RUNNING", config.model_dump_json(), None, time.time()))
        event(active_id, "Coordinator", "", "START", "Bắt đầu kịch bản với trạng thái node đã làm mới", config=config.model_dump())
        task = asyncio.create_task(execute(active_id, config))
        return {"id": active_id}


class RuntimeControl(BaseModel):
    paused: bool | None = None
    pace_ms: int | None = Field(None, ge=0, le=3000)


@app.post("/control")
async def runtime_control(body: RuntimeControl):
    async with control_lock:
        if not task or task.done() or not active_config:
            raise HTTPException(409, "No active scenario")
        if body.paused is not None:
            if active_config.mode == "step":
                raise HTTPException(409, "Step mode uses Next, not Pause/Resume")
            active_config.paused = body.paused
            if not body.paused and read_journal()["run"]["status"] == "WAITING" and gate._value == 0:
                gate.release()
            event(active_id, "Coordinator", "", "PAUSE" if body.paused else "RESUME",
                  "Tạm dừng tại ranh giới hành động" if body.paused else "Tiếp tục thực thi")
        if body.pace_ms is not None:
            active_config.pace_ms = body.pace_ms
        with connect("coordinator") as db:
            db.execute("UPDATE runs SET config=? WHERE id=?", (active_config.model_dump_json(), active_id))
        return {"paused": active_config.paused, "pace_ms": active_config.pace_ms}


@app.post("/step")
async def next_step():
    if not task or task.done():
        raise HTTPException(409, "No active scenario")
    # At most one queued step: rapid clicks cannot skip an arbitrary number of gates.
    if gate._value == 0:
        gate.release()
    return {"step": True}


@app.post("/reset")
async def reset():
    global task, active_id, gate
    async with control_lock:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for node in NODES:
            await administrative(node, "/reset")
        with connect("coordinator") as db:
            db.execute("DELETE FROM transactions")
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM runs")
        task = None
        active_id = None
        gate = asyncio.Semaphore(0)
        return {"reset": True}


@app.post("/resolve")
async def resolve():
    global task, gate, active_id, active_config
    async with control_lock:
        if task and not task.done():
            raise HTTPException(409, "Scenario already running")
        journal = read_journal()
        if not journal["transactions"]:
            raise HTTPException(409, "No transaction to recover")
        tx = journal["transactions"][0]
        decision = tx["state"]
        if decision == "PREPARING":
            # Only the restarted authoritative coordinator can decide, from its durable votes.
            decision = "COMMIT" if len(tx["votes"]) == 3 and all(v == "YES" for v in tx["votes"].values()) else "ABORT"
        config = RunConfig(**{**journal["run"]["config"], "mode": "auto", "paused": False})
        active_config = config
        gate = asyncio.Semaphore(0)
        active_id = tx["run_id"]
        set_run(active_id, "RUNNING")
        event(active_id, "Coordinator", "Disk", "COORDINATOR_RECOVERY", "Đọc nhật ký bền vững và tiếp tục quyết định", transaction_id=tx["id"])
        task = asyncio.create_task(execute(active_id, config, (tx["id"], decision, tx["votes"])))
        return {"resolving": tx["id"], "decision": decision}

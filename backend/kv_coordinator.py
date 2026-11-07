"""Authoritative single-coordinator 2PC, durable decisions and presumed-abort recovery."""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.kv_common import PEERS, db, emit, events, health, init_events, record

client = None
task = None
gate = asyncio.Event()
control = {"mode": "auto", "paused": False, "pace_ms": 100}
lock = asyncio.Lock()
current_id = None
waiting = False


def transactions():
    with db() as conn:
        return [{**dict(row), **{key: json.loads(row[key]) for key in ["writes", "votes", "acks", "before_values", "config"]}} for row in conn.execute("SELECT * FROM distributed_tx ORDER BY created DESC")]


def update(tid, **fields):
    with db() as conn:
        for key, val in fields.items():
            if key not in ["decision", "phase", "votes", "acks"]:
                raise ValueError(key)
            conn.execute(f"UPDATE distributed_tx SET {key}=? WHERE id=?", (json.dumps(val) if isinstance(val, dict) else val, tid))


async def send(tx, node, path, body):
    record(tx["run_id"], "SEND", node, transaction_id=tx["id"], path=path, operation_id=tx["id"])
    try:
        response = await client.post(PEERS[node] + path, json={**body, "run_id": tx["run_id"]}, timeout=.9)
        response.raise_for_status()
        result = response.json()
        record(tx["run_id"], "ACK", node, transaction_id=tx["id"], path=path, response=result, source=node)
        return result
    except httpx.HTTPError:
        record(tx["run_id"], "TIMEOUT", node, transaction_id=tx["id"], path=path, detail="HTTP failed; no decision inferred at participant")
        return None


async def step(tx, description, forced=False):
    global waiting
    if not forced:
        await asyncio.sleep(control["pace_ms"] / 1000)
    if forced or control["mode"] == "step" or control["paused"]:
        gate.clear()
        waiting = True
        record(tx["run_id"], "STEP_READY", detail=description, transaction_id=tx["id"])
        try:
            await gate.wait()
        finally:
            waiting = False
    record(tx["run_id"], "STEP", detail=description, transaction_id=tx["id"])


def persist_decision(tx, decision, recovering=False):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT decision FROM distributed_tx WHERE id=?", (tx["id"],)).fetchone()[0]
        if old and old != decision:
            raise RuntimeError("Attempted conflicting durable decision")
        conn.execute("UPDATE distributed_tx SET decision=?,phase='DECISION_DURABLE' WHERE id=?", (decision, tx["id"]))
        emit(conn, tx["run_id"], "DURABLE_DECISION", transaction_id=tx["id"], decision=decision, recovery=recovering)
    tx["decision"] = decision


async def distribute(tx, first_only=False):
    acks = dict(tx["acks"])
    for node in PEERS:
        if node in acks:
            continue
        result = await send(tx, node, "/decision", {"id": tx["id"], "decision": tx["decision"]})
        if result and result["state"] == tx["decision"]:
            acks[node] = result
            update(tx["id"], acks=acks)
            tx["acks"] = acks
        if first_only:
            return
    if len(acks) == len(PEERS):
        update(tx["id"], phase="COMPLETE")
        record(tx["run_id"], "TRANSACTION_COMPLETE", transaction_id=tx["id"], decision=tx["decision"])


async def engine(tx, recovering=False):
    global current_id
    current_id = tx["id"]
    try:
        if recovering:
            # The only decision authority has restarted, with an exclusive persistent
            # volume. No durable decision => ABORT; a durable COMMIT is never lost.
            record(tx["run_id"], "COORDINATOR_RECOVERY", transaction_id=tx["id"], previous_decision=tx["decision"])
            persist_decision(tx, tx["decision"] or "ABORT", recovering=True)
        else:
            votes = {}
            for node in PEERS:
                await step(tx, "PREPARE " + node)
                result = await send(tx, node, "/prepare", {"id": tx["id"], "writes": tx["writes"][node], "expected": {key: tx["before_values"][node].get(key) for key in tx["writes"][node]}, "vote_no": tx["config"]["scenario"] == "vote_no" and node == tx["config"]["target"]})
                votes[node] = result["vote"] if result else "MISSING"
                update(tx["id"], votes=votes)
                record(tx["run_id"], "VOTE", transaction_id=tx["id"], vote=votes[node], source=node, target="coordinator")
            tx["votes"] = votes
            ready = len(votes) == len(PEERS) and all(v == "YES" for v in votes.values())
            update(tx["id"], phase="READY" if ready else "PREPARING")
            if ready and tx["config"]["scenario"] in ["coordinator_crash", "participant_prepared"]:
                update(tx["id"], phase="PAUSED_AFTER_PREPARE")
                await step(tx, "All PREPARED; use Docker CLI to stop coordinator/participant. No durable decision yet.", forced=True)
            persist_decision(tx, "COMMIT" if ready else "ABORT")
            if tx["config"]["scenario"] == "coordinator_after_commit" and ready:
                await distribute(tx, first_only=True)
                update(tx["id"], phase="PAUSED_AFTER_COMMIT")
                await step(tx, "COMMIT durable; A notified, B/C still PREPARED. Stop coordinator with Docker CLI.", forced=True)
        while True:
            await distribute(tx)
            if len(tx["acks"]) == len(PEERS):
                break
            update(tx["id"], phase="DECISION_PENDING")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Shutdown is not a protocol decision. In-doubt state stays on disk.
        raise
    except Exception as exc:
        record(tx["run_id"], "ERROR", detail=str(exc), transaction_id=tx["id"])
        update(tx["id"], phase="INTERRUPTED")


@asynccontextmanager
async def lifespan(app):
    global client, task
    init_events()
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS distributed_tx(id TEXT PRIMARY KEY,run_id TEXT,created REAL,phase TEXT,decision TEXT,writes TEXT,votes TEXT,acks TEXT,before_values TEXT,config TEXT)")
    client = httpx.AsyncClient(trust_env=False)
    pending = [tx for tx in transactions() if tx["phase"] != "COMPLETE"]
    if pending:
        async def recover_all():
            for tx in reversed(pending):
                await engine(tx, recovering=True)
        task = asyncio.create_task(recover_all())
    yield
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await client.aclose()


app = FastAPI(title="Distributed KV 2PC coordinator", lifespan=lifespan)
app.get("/health")(health)


class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: "tx-" + uuid4().hex)
    run_id: str = ""
    writes: dict[str, dict[str, int | str]] | None = None
    scenario: Literal["normal", "vote_no", "coordinator_crash", "coordinator_after_commit", "participant_prepared"] = "normal"
    target: Literal["A", "B", "C"] = "B"
    mode: Literal["auto", "step"] = "auto"
    pace_ms: int = Field(100, ge=0, le=3000)


@app.post("/transactions")
async def start(body: Transaction):
    global task, control
    async with lock:
        previous = next((tx for tx in transactions() if tx["id"] == body.id), None)
        if previous:
            if body.writes is not None and body.writes != previous["writes"]:
                raise HTTPException(409, "Transaction ID reused with different writes")
            return previous
        if task and not task.done() or any(tx["phase"] != "COMPLETE" for tx in transactions()):
            raise HTTPException(409, "An in-doubt transaction must finish first")
        before = {}
        for node in PEERS:
            try:
                response = await client.get(PEERS[node] + "/state", timeout=1)
                response.raise_for_status()
                before[node] = response.json()["kv"]
            except httpx.HTTPError:
                raise HTTPException(503, "Participant unavailable before transaction")
        writes = body.writes or {"A": {"balance": before["A"]["balance"] - 10}, "B": {"balance": before["B"]["balance"] + 10}, "C": {"last_transaction": body.id}}
        if set(writes) != set(PEERS) or any(not values or "inventory" in values for values in writes.values()):
            raise HTTPException(422, "Provide nonempty writes for exactly A, B, C; inventory reserved for redo")
        config = body.model_dump(exclude={"writes"})
        with db() as conn:
            conn.execute("INSERT INTO distributed_tx VALUES(?,?,?,'PREPARING',NULL,?,'{}','{}',?,?)", (body.id, body.run_id or body.id, time.time(), json.dumps(writes), json.dumps(before), json.dumps(config)))
        tx = next(tx for tx in transactions() if tx["id"] == body.id)
        control = {"mode": body.mode, "paused": False, "pace_ms": body.pace_ms}
        task = asyncio.create_task(engine(tx))
        return tx


@app.get("/state")
def state():
    return {**health(), "transactions": transactions(), "events": events(), "waiting": waiting, "control": control}


@app.get("/transactions/{tid}")
def get_transaction(tid: str):
    tx = next((tx for tx in transactions() if tx["id"] == tid), None)
    if not tx:
        raise HTTPException(404, "Unknown transaction")
    return tx


@app.post("/step")
def next_step():
    if not task or task.done():
        raise HTTPException(409, "No active transaction")
    gate.set()
    return {"step": True}


@app.post("/control")
def change_control(body: dict):
    if "paused" in body:
        control["paused"] = bool(body["paused"])
        if not control["paused"]:
            gate.set()
    if "pace_ms" in body:
        if not isinstance(body["pace_ms"], int) or not 0 <= body["pace_ms"] <= 3000:
            raise HTTPException(422, "Invalid pace")
        control["pace_ms"] = body["pace_ms"]
    return control


@app.post("/reset")
async def reset():
    async with lock:
        if task and not task.done() or any(tx["phase"] != "COMPLETE" for tx in transactions()):
            raise HTTPException(409, "Resolve transaction before reset; no forced heuristic abort")
        with db() as conn:
            conn.execute("DELETE FROM distributed_tx")
        return {"reset": True}

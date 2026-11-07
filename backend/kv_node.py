"""Durable KV worker: RPC dedup, FIFO multicast, 2PC and local redo recovery.

No Docker control, peer database access, or heuristic participant decision.
"""
import json
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.kv_common import SERVICE, db, emit, events, health, init_events


def unlocked(conn, key):
    if conn.execute("SELECT 1 FROM locks WHERE key=?", (key,)).fetchone():
        raise HTTPException(409, "Key locked by a PREPARED transaction")


def value(conn, key):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def put(conn, key, val):
    conn.execute("INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(val)))


def redo(conn, run_id="boot"):
    cp = conn.execute("SELECT * FROM checkpoints WHERE singleton=1").fetchone()
    current = cp["value"]
    replayed = []
    for row in conn.execute("SELECT * FROM redo WHERE lsn>? ORDER BY lsn", (cp["lsn"],)):
        current += row["delta"]
        replayed.append({"id": row["id"], "lsn": row["lsn"], "delta": row["delta"]})
        emit(conn, run_id, "REPLAY", operation_id=row["id"], lsn=row["lsn"], value=current)
    put(conn, "inventory", current)
    report = {"checkpoint_seq": cp["lsn"], "checkpoint_value": cp["value"], "replayed": [r["id"] for r in replayed], "entries": replayed, "value": current}
    conn.execute("INSERT OR REPLACE INTO metadata VALUES('recovery',?)", (json.dumps(report),))
    emit(conn, run_id, "RECOVERED", detail="Local checkpoint + ordered redo; prepared locks retained", **report)
    return report


def initialize():
    init_events()
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dedup(id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS tx(id TEXT PRIMARY KEY,run_id TEXT,state TEXT,writes TEXT);
        CREATE TABLE IF NOT EXISTS locks(key TEXT PRIMARY KEY,tx_id TEXT);
        CREATE TABLE IF NOT EXISTS received(stream TEXT,seq INTEGER,payload TEXT,delivered INTEGER DEFAULT 0, PRIMARY KEY(stream,seq));
        CREATE TABLE IF NOT EXISTS redo(lsn INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,delta INTEGER);
        CREATE TABLE IF NOT EXISTS checkpoints(singleton INTEGER PRIMARY KEY CHECK(singleton=1),lsn INTEGER,value INTEGER);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
        INSERT OR IGNORE INTO checkpoints VALUES(1,0,100);
        """)
        conn.execute("BEGIN IMMEDIATE")
        for key, val in {"counter": 0, "balance": 100, "last_transaction": "none"}.items():
            conn.execute("INSERT OR IGNORE INTO kv VALUES(?,?)", (key, json.dumps(val)))
        redo(conn)


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="Distributed KV worker " + SERVICE, lifespan=lifespan)
app.get("/health")(health)


class Write(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    run_id: str = "manual"
    key: str = Field(min_length=1, max_length=80)
    operation: Literal["PUT", "INCREMENT"] = "PUT"
    value: int | str = 0
    deduplicate: bool = True


@app.get("/kv/{key}")
def get_key(key: str):
    with db() as conn:
        val = value(conn, key)
        if val is None:
            raise HTTPException(404, "Key not found")
        return {"node": SERVICE, "key": key, "value": val, "locked": bool(conn.execute("SELECT 1 FROM locks WHERE key=?", (key,)).fetchone())}


@app.post("/kv")
def write(body: Write):
    if body.key == "inventory":
        raise HTTPException(409, "Inventory must use /operations so redo remains authoritative")
    fingerprint = json.dumps([body.key, body.operation, body.value])
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute("SELECT * FROM dedup WHERE id=?", (body.id,)).fetchone()
        if previous and previous["fingerprint"] != fingerprint:
            raise HTTPException(409, "Request ID reused with a different operation")
        if previous and body.deduplicate:
            result = {**json.loads(previous["result"]), "duplicate": True}
            emit(conn, body.run_id, "DUPLICATE_SUPPRESSED", request_id=body.id, response=result)
            return result
        unlocked(conn, body.key)
        before = value(conn, body.key)
        if body.operation == "INCREMENT":
            if not isinstance(body.value, int) or (before is not None and not isinstance(before, int)):
                raise HTTPException(422, "INCREMENT requires integer values")
            after = (before or 0) + body.value
        else:
            after = body.value
        put(conn, body.key, after)
        result = {"id": body.id, "key": body.key, "before": before, "value": after, "duplicate": False}
        conn.execute("INSERT OR REPLACE INTO dedup VALUES(?,?,?)", (body.id, fingerprint, json.dumps(result)))
        emit(conn, body.run_id, "RPC_EXECUTED", request_id=body.id, response=result)
        return result


class Prepare(BaseModel):
    id: str
    run_id: str = "manual"
    writes: dict[str, int | str] = Field(min_length=1, max_length=20)
    vote_no: bool = False
    expected: dict[str, int | str | None] | None = None


@app.post("/prepare")
def prepare(body: Prepare):
    if "inventory" in body.writes:
        raise HTTPException(422, "Recovery inventory is outside the transaction demo")
    encoded = json.dumps(body.writes, sort_keys=True)
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT * FROM tx WHERE id=?", (body.id,)).fetchone()
        if prior:
            if prior["writes"] != encoded:
                raise HTTPException(409, "Transaction ID content mismatch")
            return {"id": body.id, "state": prior["state"], "vote": "NO" if prior["state"] == "ABORT" else "YES"}
        conflict = any(conn.execute("SELECT 1 FROM locks WHERE key=?", (key,)).fetchone() for key in body.writes)
        invalid = any(key == "balance" and (not isinstance(val, int) or val < 0) for key, val in body.writes.items())
        invalid = invalid or body.expected is not None and any(value(conn, key) != val for key, val in body.expected.items())
        state = "ABORT" if body.vote_no or conflict or invalid else "PREPARED"
        conn.execute("INSERT INTO tx VALUES(?,?,?,?)", (body.id, body.run_id, state, encoded))
        if state == "PREPARED":
            conn.executemany("INSERT INTO locks VALUES(?,?)", [(key, body.id) for key in body.writes])
        vote = "YES" if state == "PREPARED" else "NO"
        emit(conn, body.run_id, state, target="coordinator", transaction_id=body.id, vote=vote, writes=body.writes)
        return {"id": body.id, "state": state, "vote": vote}


class Decision(BaseModel):
    id: str
    run_id: str = "manual"
    decision: Literal["COMMIT", "ABORT"]


@app.post("/decision")
def decision(body: Decision):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT * FROM tx WHERE id=?", (body.id,)).fetchone()
        if prior and prior["state"] in ("COMMIT", "ABORT"):
            if prior["state"] != body.decision:
                raise HTTPException(409, "Conflicting durable decision")
            return {"id": body.id, "state": prior["state"], "duplicate": True}
        if body.decision == "COMMIT":
            if not prior or prior["state"] != "PREPARED":
                raise HTTPException(409, "COMMIT requires durable PREPARED")
            for key, val in json.loads(prior["writes"]).items():
                put(conn, key, val)
        if prior:
            conn.execute("UPDATE tx SET state=? WHERE id=?", (body.decision, body.id))
        else:
            conn.execute("INSERT INTO tx VALUES(?,?,?,'{}')", (body.id, body.run_id, "ABORT"))
        conn.execute("DELETE FROM locks WHERE tx_id=?", (body.id,))
        emit(conn, body.run_id, body.decision, transaction_id=body.id)
        return {"id": body.id, "state": body.decision, "duplicate": False}


class Message(BaseModel):
    stream: str = Field(min_length=1, max_length=160)
    run_id: str = "manual"
    seq: int = Field(ge=1, le=10000)
    payload: str = Field(max_length=2000)


@app.post("/multicast")
def multicast(body: Message):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT payload FROM received WHERE stream=? AND seq=?", (body.stream, body.seq)).fetchone()
        if prior and prior[0] != body.payload:
            raise HTTPException(409, "Sequence reused with different payload")
        conn.execute("INSERT OR IGNORE INTO received(stream,seq,payload) VALUES(?,?,?)", (body.stream, body.seq, body.payload))
        emit(conn, body.run_id, "RECEIVED", stream=body.stream, sequence=body.seq, duplicate=bool(prior))
        delivered = conn.execute("SELECT COALESCE(MAX(seq),0) FROM received WHERE stream=? AND delivered=1", (body.stream,)).fetchone()[0]
        while conn.execute("SELECT 1 FROM received WHERE stream=? AND seq=?", (body.stream, delivered + 1)).fetchone():
            delivered += 1
            conn.execute("UPDATE received SET delivered=1 WHERE stream=? AND seq=?", (body.stream, delivered))
            emit(conn, body.run_id, "DELIVERED", stream=body.stream, sequence=delivered)
        rows = conn.execute("SELECT seq FROM received WHERE stream=? ORDER BY seq", (body.stream,)).fetchall()
        received = [row[0] for row in rows]
        missing = [seq for seq in range(1, max(received) + 1) if seq not in received]
        result = {"ack": body.seq, "received": received, "delivered": list(range(1, delivered + 1)), "missing": missing, "stream": body.stream}
        emit(conn, body.run_id, "NACK" if missing else "ACK", target="Sender", **result)
        return result


class Operation(BaseModel):
    id: str
    run_id: str = "manual"
    delta: int = Field(ge=-1000, le=1000)


@app.post("/operations")
def operation(body: Operation):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT * FROM redo WHERE id=?", (body.id,)).fetchone()
        if prior and prior["delta"] != body.delta:
            raise HTTPException(409, "Event ID content mismatch")
        if not prior:
            # Log entry and materialized value are one local atomic SQLite commit.
            conn.execute("INSERT INTO redo(id,delta) VALUES(?,?)", (body.id, body.delta))
            put(conn, "inventory", value(conn, "inventory") + body.delta)
        result = {"id": body.id, "value": value(conn, "inventory"), "duplicate": bool(prior)}
        emit(conn, body.run_id, "OP_DUPLICATE" if prior else "OPERATION", operation_id=body.id, **result)
        return result


@app.post("/checkpoint")
def checkpoint(body: dict | None = None):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        lsn = conn.execute("SELECT COALESCE(MAX(lsn),0) FROM redo").fetchone()[0]
        val = value(conn, "inventory")
        conn.execute("UPDATE checkpoints SET lsn=?,value=?", (lsn, val))
        emit(conn, (body or {}).get("run_id", "manual"), "CHECKPOINT", lsn=lsn, value=val)
        return {"seq": lsn, "value": val}


@app.post("/recover")
def recover(body: dict | None = None):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return redo(conn, (body or {}).get("run_id", "manual"))


@app.post("/recovery/setup")
def recovery_setup(body: dict):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM locks").fetchone():
            raise HTTPException(409, "Resolve prepared transaction first")
        conn.execute("DELETE FROM redo")
        conn.execute("UPDATE checkpoints SET lsn=0,value=100")
        put(conn, "inventory", 100)
        emit(conn, body.get("run_id", "manual"), "RECOVERY_BASELINE", value=100)
        return {"inventory": 100}


@app.get("/state")
def state():
    with db() as conn:
        kv = {row["key"]: json.loads(row["value"]) for row in conn.execute("SELECT * FROM kv")}
        cp = dict(conn.execute("SELECT lsn AS seq,value FROM checkpoints").fetchone())
        txs = [{**dict(row), "writes": json.loads(row["writes"])} for row in conn.execute("SELECT * FROM tx ORDER BY rowid DESC")]
        group = [dict(row) for row in conn.execute("SELECT * FROM received ORDER BY stream,seq")]
        metadata = conn.execute("SELECT value FROM metadata WHERE key='recovery'").fetchone()
        return {**health(), "kv": kv, "counters": {"rpc": kv.get("counter", 0), "commit": kv.get("balance", 0)}, "memory_value": kv["inventory"],
                "transactions": txs, "locks": [dict(row) for row in conn.execute("SELECT * FROM locks")], "checkpoint": cp,
                "operations": [dict(row) for row in conn.execute("SELECT lsn AS seq,id,delta FROM redo ORDER BY lsn")],
                "multicast": [r for r in group if r["delivered"]], "group": group,
                "recovery": json.loads(metadata[0]) if metadata else {}, "events": events()}


@app.post("/reset")
def reset(body: dict | None = None):
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM locks").fetchone() and not (body or {}).get("force"):
            raise HTTPException(409, "Resolve prepared transactions before reset (force is destructive)")
        for table in ["kv", "dedup", "tx", "locks", "received", "redo", "metadata"]:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("UPDATE checkpoints SET lsn=0,value=100")
        for key, val in {"counter": 0, "balance": 100, "last_transaction": "none", "inventory": 100}.items():
            put(conn, key, val)
        emit(conn, "manual", "RESET", detail="Explicit local demo data reset; volume retained")
    return {"reset": SERVICE}

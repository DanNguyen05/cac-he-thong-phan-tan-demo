"""Independent participant service. Run one process per LAB_NODE."""
import json
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.storage import connect

NAME = os.environ.get("LAB_NODE", "A")
unavailable = False
memory_value = 0
recovery_report = {}


def db_connect():
    return connect(f"node-{NAME}")


def log(db, kind, ident, data):
    db.execute("INSERT INTO logs(time,kind,id,data) VALUES(?,?,?,?)",
               (time.time(), kind, ident, json.dumps(data)))


def recover():
    global memory_value, recovery_report
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cp = db.execute("SELECT * FROM checkpoint WHERE singleton=1").fetchone()
        memory_value = cp["value"]
        replayed = []
        for op in db.execute("SELECT * FROM operations WHERE seq>? ORDER BY seq", (cp["seq"],)):
            memory_value += op["delta"]
            replayed.append(op["id"])
        db.execute("UPDATE counters SET value=? WHERE key='recovery'", (memory_value,))
        recovery_report = {"checkpoint_seq": cp["seq"], "checkpoint_value": cp["value"],
                           "replayed": replayed, "value": memory_value, "pid": os.getpid()}
        log(db, "RECOVERY", "boot", recovery_report)


@asynccontextmanager
async def lifespan(app):
    with db_connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS counters(key TEXT PRIMARY KEY, value INTEGER);
        INSERT OR IGNORE INTO counters VALUES('rpc',0),('commit',0),('recovery',0);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, result TEXT);
        CREATE TABLE IF NOT EXISTS multicast(id TEXT PRIMARY KEY, payload TEXT);
        CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY, state TEXT, amount INTEGER);
        CREATE TABLE IF NOT EXISTS operations(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, delta INTEGER);
        CREATE TABLE IF NOT EXISTS checkpoint(singleton INTEGER PRIMARY KEY CHECK(singleton=1), seq INTEGER, value INTEGER);
        INSERT OR IGNORE INTO checkpoint VALUES(1,0,0);
        CREATE TABLE IF NOT EXISTS logs(seq INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, kind TEXT, id TEXT, data TEXT);
        """)
    recover()
    yield


app = FastAPI(title=f"Fault Tolerance · Node {NAME}", lifespan=lifespan)


def available():
    if unavailable:
        raise HTTPException(503, "Node administratively unavailable")


class RPC(BaseModel):
    id: str
    deduplicate: bool = True
    delta: int = 1


class Message(BaseModel):
    id: str
    payload: str = "Xin chào nhóm!"


class Prepare(BaseModel):
    id: str
    amount: int = Field(10, ge=1, le=1000)
    vote_no: bool = False


class Decision(BaseModel):
    id: str
    decision: str


class Operation(BaseModel):
    id: str
    delta: int = Field(5, ge=-1000, le=1000)


@app.get("/health")
def health():
    return {"node": NAME, "pid": os.getpid(), "available": not unavailable}


@app.get("/state")
async def state():
    with db_connect() as db:
        counters = {r["key"]: r["value"] for r in db.execute("SELECT * FROM counters")}
        return {"node": NAME, "pid": os.getpid(), "available": not unavailable,
                "counters": counters, "memory_value": memory_value,
                "multicast": [dict(r) for r in db.execute("SELECT * FROM multicast")],
                "transactions": [dict(r) for r in db.execute("SELECT * FROM transactions")],
                "checkpoint": dict(db.execute("SELECT * FROM checkpoint").fetchone()),
                "operations": [dict(r) for r in db.execute("SELECT * FROM operations ORDER BY seq")],
                "recovery": recovery_report,
                "logs": [dict(r) for r in db.execute("SELECT * FROM logs ORDER BY seq DESC LIMIT 60")]}


@app.post("/availability")
async def availability(body: dict):
    global unavailable
    unavailable = not bool(body.get("available", True))
    return health()


@app.post("/rpc")
async def rpc(body: RPC):
    available()
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT result FROM requests WHERE id=?", (body.id,)).fetchone()
        if body.deduplicate and previous:
            result = json.loads(previous["result"])
            result["duplicate"] = True
            log(db, "DUPLICATE_SUPPRESSED", body.id, result)
            return result
        db.execute("UPDATE counters SET value=value+? WHERE key='rpc'", (body.delta,))
        count = db.execute("SELECT value FROM counters WHERE key='rpc'").fetchone()[0]
        result = {"id": body.id, "value": count, "execution_count": count, "duplicate": False}
        db.execute("INSERT OR REPLACE INTO requests VALUES(?,?)", (body.id, json.dumps(result)))
        log(db, "RPC_EXECUTED", body.id, result)
        return result


@app.post("/multicast")
async def multicast(body: Message):
    available()
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute("INSERT OR IGNORE INTO multicast VALUES(?,?)", (body.id, body.payload))
        duplicate = cursor.rowcount == 0
        result = {"id": body.id, "ack": NAME, "duplicate": duplicate,
                  "delivery_count": db.execute("SELECT COUNT(*) FROM multicast").fetchone()[0]}
        log(db, "DUPLICATE_SUPPRESSED" if duplicate else "MULTICAST_DELIVERED", body.id, result)
        return result


@app.post("/prepare")
async def prepare(body: Prepare):
    available()
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM transactions WHERE id=?", (body.id,)).fetchone()
        if prior:
            return {"id": body.id, "vote": "NO" if prior["state"] == "ABORT" else "YES", "state": prior["state"]}
        # A participant rejects overlapping prepared updates to the same demo resource.
        locked = db.execute("SELECT 1 FROM transactions WHERE state='PREPARED'").fetchone()
        vote = "NO" if body.vote_no or locked else "YES"
        state = "ABORT" if vote == "NO" else "PREPARED"
        db.execute("INSERT INTO transactions VALUES(?,?,?)", (body.id, state, body.amount))
        log(db, state, body.id, {"vote": vote, "amount": body.amount})
        return {"id": body.id, "vote": vote, "state": state}


@app.post("/decision")
async def decision(body: Decision):
    available()
    if body.decision not in ("COMMIT", "ABORT"):
        raise HTTPException(422, "Invalid decision")
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT * FROM transactions WHERE id=?", (body.id,)).fetchone()
        if prior and prior["state"] in ("COMMIT", "ABORT"):
            if prior["state"] != body.decision:
                raise HTTPException(409, "Conflicting durable decision")
            return {"id": body.id, "state": body.decision, "duplicate": True}
        if body.decision == "COMMIT" and not prior:
            raise HTTPException(409, "Cannot commit without prepare")
        if body.decision == "COMMIT":
            db.execute("UPDATE counters SET value=value+? WHERE key='commit'", (prior["amount"],))
        db.execute("INSERT INTO transactions VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                   (body.id, body.decision))
        log(db, body.decision, body.id, {})
        return {"id": body.id, "state": body.decision, "duplicate": False}


@app.post("/operation")
async def operation(body: Operation):
    global memory_value
    available()
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute("INSERT OR IGNORE INTO operations(id,delta) VALUES(?,?)", (body.id, body.delta))
        duplicate = cursor.rowcount == 0
        if not duplicate:
            db.execute("UPDATE counters SET value=value+? WHERE key='recovery'", (body.delta,))
        value = db.execute("SELECT value FROM counters WHERE key='recovery'").fetchone()[0]
        log(db, "OP_DUPLICATE" if duplicate else "OPERATION", body.id, {"delta": body.delta, "value": value})
    memory_value = value
    return {"id": body.id, "value": value, "duplicate": duplicate}


@app.post("/checkpoint")
async def checkpoint():
    available()
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        seq = db.execute("SELECT COALESCE(MAX(seq),0) FROM operations").fetchone()[0]
        value = db.execute("SELECT value FROM counters WHERE key='recovery'").fetchone()[0]
        db.execute("UPDATE checkpoint SET seq=?,value=?", (seq, value))
        log(db, "CHECKPOINT", str(seq), {"value": value})
        return {"seq": seq, "value": value}


@app.post("/recover")
async def replay():
    available()
    recover()
    return recovery_report


@app.post("/reset")
async def reset():
    global unavailable, memory_value, recovery_report
    with db_connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for table in ("requests", "multicast", "transactions", "operations", "logs"):
            db.execute(f"DELETE FROM {table}")
        db.execute("DELETE FROM sqlite_sequence WHERE name='operations'")
        db.execute("UPDATE counters SET value=0")
        db.execute("UPDATE checkpoint SET seq=0,value=0")
    unavailable = False
    memory_value = 0
    recovery_report = {}
    return {"reset": NAME}

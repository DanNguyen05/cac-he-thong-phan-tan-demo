"""Shared durable primitives; each KV service owns its own database/volume."""
import json
import os
import time
from contextlib import contextmanager
from uuid import uuid4

from backend.storage import connect

SERVICE = os.environ.get("KV_SERVICE", "A")
BOOT_ID = uuid4().hex
PEERS = json.loads(os.environ.get("KV_PEERS", '{"A":"http://127.0.0.1:19103","B":"http://127.0.0.1:19104","C":"http://127.0.0.1:19105"}'))
COORDINATOR = os.environ.get("KV_COORDINATOR", "http://127.0.0.1:19101")
RPC_SERVER = os.environ.get("KV_RPC_SERVER", "http://127.0.0.1:19102")


@contextmanager
def db():
    connection = connect("kv-" + SERVICE)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_events():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY AUTOINCREMENT, time REAL, run_id TEXT, source TEXT, target TEXT, kind TEXT, detail TEXT, data TEXT)")


def emit(conn, run_id, kind, target="", detail="", source=None, **data):
    conn.execute("INSERT INTO journal(time,run_id,source,target,kind,detail,data) VALUES(?,?,?,?,?,?,?)",
                 (time.time(), run_id, source or SERVICE, target, kind, detail, json.dumps(data)))


def record(run_id, kind, target="", detail="", **data):
    with db() as conn:
        emit(conn, run_id, kind, target, detail, **data)


def events():
    with db() as conn:
        return [{**dict(row), "data": json.loads(row["data"])} for row in conn.execute("SELECT * FROM journal ORDER BY seq")]


def health():
    return {"service": SERVICE, "node": SERVICE, "pid": os.getpid(), "boot_id": BOOT_ID, "available": True, "runtime": os.environ.get("KV_RUNTIME", "process")}

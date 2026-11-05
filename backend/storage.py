"""SQLite stores: short, atomic transactions; no shared node database."""
import json
import os
import sqlite3
import time
from pathlib import Path


DATA = Path(os.environ.get("LAB_DATA", "data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)


def connect(name):
    db = sqlite3.connect(DATA / f"{name}.sqlite", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def initialize_journal():
    with connect("coordinator") as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, module TEXT, scenario TEXT,
          status TEXT, config TEXT, result TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT, time REAL, source TEXT, target TEXT, kind TEXT, detail TEXT, data TEXT);
        CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY, run_id TEXT,
          state TEXT, votes TEXT, acknowledgments TEXT, amount INTEGER);
        """)


def event(run_id, source, target, kind, detail, **data):
    with connect("coordinator") as db:
        db.execute("INSERT INTO events(run_id,time,source,target,kind,detail,data) VALUES(?,?,?,?,?,?,?)",
                   (run_id, time.time(), source, target, kind, detail, json.dumps(data)))


def set_run(run_id, status, result=None):
    with connect("coordinator") as db:
        if result is None:
            db.execute("UPDATE runs SET status=? WHERE id=?", (status, run_id))
        else:
            db.execute("UPDATE runs SET status=?, result=? WHERE id=?", (status, json.dumps(result), run_id))


def read_journal():
    with connect("coordinator") as db:
        row = db.execute("SELECT * FROM runs ORDER BY created DESC LIMIT 1").fetchone()
        run = dict(row) if row else None
        if run:
            run["config"] = json.loads(run["config"])
            run["result"] = json.loads(run["result"]) if run["result"] else None
        rows = db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq DESC LIMIT 600",
                          (run["id"] if run else "",)).fetchall()
        events = []
        for row in reversed(rows):
            item = dict(row)
            item["data"] = json.loads(item["data"])
            events.append(item)
        transactions = []
        for row in db.execute("SELECT * FROM transactions WHERE run_id=?", (run["id"] if run else "",)):
            item = dict(row)
            item["votes"] = json.loads(item["votes"])
            item["acknowledgments"] = json.loads(item["acknowledgments"])
            transactions.append(item)
    return {"run": run, "events": events, "transactions": transactions}

"""Same acceptance tests against six real processes or opt-in Docker Compose.

KV_TEST_MODE=docker uses the named Compose project; no down -v, no Docker socket.
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["gateway", "coordinator", "rpc", "A", "B", "C"]
DOCKER_NAMES = {"gateway": "dashboard", "A": "participant-a", "B": "participant-b", "C": "participant-c", "rpc": "rpc", "coordinator": "coordinator"}


def wait(predicate, timeout=15):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            last = predicate()
            if last:
                return last
        except (httpx.HTTPError, KeyError, TypeError):
            pass
        time.sleep(.08)
    raise AssertionError(f"Condition did not become true; last={last}")


class Cluster:
    def __init__(self, folder, docker=False):
        self.folder, self.docker, self.procs, self.outputs = folder, docker, {}, {}
        if docker:
            self.base = 19000
        else:
            for base in range(21000, 21900, 10):
                sockets = []
                try:
                    for port in range(base, base + 6):
                        s = socket.socket(); sockets.append(s); s.bind(("127.0.0.1", port))
                    self.base = base
                    break
                except OSError:
                    continue
                finally:
                    for s in sockets:
                        s.close()
            else:
                raise RuntimeError("No free test ports")
        self.urls = {name: f"http://127.0.0.1:{self.base + i}" for i, name in enumerate(SERVICES)}
        self.http = httpx.Client(timeout=8, trust_env=False)

    def compose(self, *args):
        return subprocess.run(["docker", "compose", "-p", "kv-transaction-lab", "-f", str(ROOT / "compose.yaml"), *args], cwd=ROOT, check=True, capture_output=True, text=True)

    def start(self, name, recreate=False):
        if self.docker:
            self.compose(*(["up", "-d", "--no-deps", "--force-recreate", DOCKER_NAMES[name]] if recreate else ["start", DOCKER_NAMES[name]]))
        else:
            if self.procs.get(name) and self.procs[name].poll() is None:
                return
            directory = self.folder / name; directory.mkdir(exist_ok=True)
            env = {**os.environ, "LAB_DATA": str(directory), "KV_SERVICE": name, "KV_RUNTIME": "process", "KV_COORDINATOR": self.urls["coordinator"], "KV_RPC_SERVER": self.urls["rpc"], "KV_PEERS": json.dumps({n: self.urls[n] for n in "ABC"})}
            module = "kv_gateway" if name == "gateway" else "kv_coordinator" if name == "coordinator" else "kv_node"
            output = open(directory / "service.log", "a", encoding="utf-8"); self.outputs[name] = output
            self.procs[name] = subprocess.Popen([sys.executable, "-m", "uvicorn", f"backend.{module}:app", "--host", "127.0.0.1", "--port", str(self.base + SERVICES.index(name)), "--log-level", "warning"], cwd=ROOT, env=env, stdout=output, stderr=output)
        wait(lambda: self.http.get(self.urls[name] + "/health").status_code == 200)

    def stop(self, name):
        if self.docker:
            self.compose("kill", "-s", "SIGKILL", DOCKER_NAMES[name])
        elif self.procs.get(name) and self.procs[name].poll() is None:
            self.procs[name].kill(); self.procs[name].wait(timeout=5); self.outputs[name].close()

    def get(self, path, service="gateway"):
        response = self.http.get(self.urls[service] + path); response.raise_for_status(); return response.json()

    def post(self, path, body=None, service="gateway"):
        response = self.http.post(self.urls[service] + path, json=body or {}); response.raise_for_status(); return response.json()

    def run(self, module, scenario="normal", **config):
        return self.post("/api/runs", {"module": module, "scenario": scenario, "pace_ms": 0, **config})["id"]

    def status(self, status="COMPLETED"):
        return wait(lambda: (state if (state := self.get("/api/state"))["run"] and state["run"]["status"] == status else None))


@pytest.fixture(scope="session")
def kv_cluster(tmp_path_factory):
    docker = os.environ.get("KV_TEST_MODE") == "docker"
    lab = Cluster(tmp_path_factory.mktemp("kv-services"), docker)
    if docker:
        result = subprocess.run(["docker", "info"], capture_output=True)
        if result.returncode:
            pytest.skip("Docker Engine unavailable: Docker acceptance has NOT run")
        lab.compose("up", "-d", "--build", "--wait", "--wait-timeout", "180")
    try:
        for name in SERVICES:
            lab.start(name)
        yield lab
    finally:
        if not docker:
            for name in SERVICES:
                lab.stop(name)
        lab.http.close()


@pytest.fixture
def kv(kv_cluster):
    lab = kv_cluster
    for name in SERVICES:
        try:
            lab.get('/health', name)
        except httpx.HTTPError:
            lab.start(name)
    lab.post("/api/reset")
    yield lab
    # Recover any assertion-interrupted tx through the real coordinator restart.
    for name in SERVICES:
        try:
            lab.get('/health', name)
        except httpx.HTTPError:
            lab.start(name)
    data = lab.get("/state", "coordinator")
    if any(tx["phase"] != "COMPLETE" for tx in data["transactions"]):
        lab.stop("coordinator"); lab.start("coordinator")
        wait(lambda: all(tx["phase"] == "COMPLETE" for tx in lab.get("/state", "coordinator")["transactions"]))


def test_kv_real_get_put_and_rpc(kv):
    kv.post("/api/kv/rpc", {"id": "put-hello", "key": "hello", "value": "world"})
    assert kv.get("/api/kv/rpc/hello")["value"] == "world"
    kv.run("rpc")
    result = kv.status()["run"]["result"]
    assert result["before"] == 0 and result["after"] == 1
    assert result["attempts"] == result["actual_executions"] == 1
    assert result["elapsed_ms"] >= 0


def test_lost_response_durable_dedup(kv):
    kv.run("rpc", "lost_response")
    result = kv.status()["run"]["result"]
    assert (result["attempts"], result["actual_executions"], result["after"]) == (2, 1, 1)
    old = kv.get("/health", "rpc")["boot_id"]
    kv.stop("rpc"); kv.start("rpc")
    assert kv.get("/health", "rpc")["boot_id"] != old
    duplicate = kv.post("/kv", {"id": result["request_id"], "key": "counter", "operation": "INCREMENT", "value": 1}, "rpc")
    assert duplicate["duplicate"] and kv.get("/kv/counter", "rpc")["value"] == 1


def test_request_id_content_conflict(kv):
    body = {"id": "fixed", "key": "counter", "operation": "INCREMENT", "value": 1}
    kv.post("/kv", body, "rpc")
    response = kv.http.post(kv.urls["rpc"] + "/kv", json={**body, "value": 2})
    assert response.status_code == 409
    assert kv.get("/kv/counter", "rpc")["value"] == 1


def test_rpc_server_crash_real_health_and_persistence(kv):
    kv.post("/kv", {"id": "durable", "key": "counter", "operation": "INCREMENT", "value": 7}, "rpc")
    kv.stop("rpc")
    wait(lambda: not kv.get("/api/health")["processes"]["rpc"]["alive"])
    assert kv.http.get(kv.urls["gateway"] + "/api/kv/rpc/counter").status_code == 503
    assert kv.get("/health")["available"]
    kv.start("rpc")
    assert kv.get("/kv/counter", "rpc")["value"] == 7


def test_multicast_three_messages(kv):
    kv.run("group")
    result = kv.status()["run"]["result"]
    assert result["verified"] and result["delivered"] == {n: [1, 2, 3] for n in "ABC"}


def test_gap_nack_retransmit_fifo(kv):
    rid = kv.run("group", "lost_message")
    state = kv.status()
    assert state["run"]["result"]["verified"]
    assert any(e["kind"] == "NACK" and e["source"] == "B" for e in state["events"])
    assert any(e["kind"] == "RETRANSMIT" and e["target"] == "B" and e["data"]["sequence"] == 2 for e in state["events"])
    delivered = [e["data"]["sequence"] for e in kv.get("/state", "B")["events"] if e["run_id"] == rid and e["kind"] == "DELIVERED"]
    assert delivered == [1, 2, 3]


def test_receiver_crash_history_catchup(kv):
    kv.stop("B")
    rid = kv.run("group", "node_down")
    result = kv.status("PARTIAL")["run"]["result"]
    assert result["missing_nodes"] == ["B"]
    kv.start("B")
    result = kv.post("/api/group/catchup", {"target": "B", "stream": rid})
    assert result["verified"] and result["delivered"]["B"] == [1, 2, 3]


def test_2pc_commit_verifies_data(kv):
    kv.run("commit")
    state = kv.status()
    assert state["run"]["result"]["verified"]
    assert state["run"]["result"]["decision"] == "COMMIT"
    assert kv.get("/kv/balance", "A")["value"] == 90
    assert kv.get("/kv/balance", "B")["value"] == 110
    assert kv.get("/kv/last_transaction", "C")["value"].startswith("tx-")
    assert all(not kv.get("/state", n)["locks"] for n in "ABC")


def test_2pc_vote_no_no_partial_writes(kv):
    kv.run("commit", "vote_no")
    state = kv.status()
    assert state["run"]["result"]["decision"] == "ABORT"
    assert state["run"]["result"]["verified"]
    assert [kv.get("/kv/balance", n)["value"] for n in "AB"] == [100, 100]
    assert kv.get("/kv/last_transaction", "C")["value"] == "none"


def test_coordinator_crash_before_decision_presumed_abort(kv):
    kv.run("commit", "coordinator_crash")
    kv.status("WAITING")
    tx = kv.get("/state", "coordinator")["transactions"][0]
    assert tx["decision"] is None and all(kv.get("/state", n)["transactions"][-1]["state"] == "PREPARED" for n in "ABC")
    kv.stop("coordinator")
    kv.status("BLOCKED")
    assert kv.get("/health")["available"]
    assert kv.http.post(kv.urls["A"] + "/kv", json={"id": "locked", "key": "balance", "value": 0}).status_code == 409
    assert all(kv.get("/kv/balance", n)["value"] == 100 for n in "AB")
    kv.start("coordinator")
    result = kv.status()["run"]["result"]
    assert result["decision"] == "ABORT" and result["verified"]


def test_coordinator_crash_after_durable_commit_replays_commit(kv):
    kv.run("commit", "coordinator_after_commit")
    kv.status("WAITING")
    tx = kv.get("/state", "coordinator")["transactions"][0]
    assert tx["decision"] == "COMMIT" and set(tx["acks"]) == {"A"}
    assert kv.get("/kv/balance", "A")["value"] == 90
    assert kv.get("/kv/balance", "B")["value"] == 100
    kv.stop("coordinator"); kv.status("BLOCKED"); kv.start("coordinator")
    result = kv.status()["run"]["result"]
    assert result["decision"] == "COMMIT" and result["verified"]
    assert kv.get("/kv/balance", "B")["value"] == 110


def test_participant_prepared_crash_retains_locks(kv):
    kv.run("commit", "participant_prepared")
    kv.status("WAITING")
    old = kv.get("/health", "B")["boot_id"]
    kv.stop("B")
    kv.post("/api/step")
    kv.status("DECISION_PENDING")
    kv.start("B")
    assert kv.get("/health", "B")["boot_id"] != old
    result = kv.status()["run"]["result"]
    assert result["decision"] == "COMMIT" and result["verified"]


def test_checkpoint_crash_recovery_direct_http_95(kv):
    kv.run("recovery", "crash_recover")
    wait(lambda: (run if (run := kv.get("/api/state")["run"])["result"] and run["result"].get("stage") == "AWAIT_CONTAINER_RESTART" else None))
    before = kv.get("/state", "A")
    assert before["checkpoint"]["value"] == 100 and before["kv"]["inventory"] == 95
    kv.stop("A"); kv.start("A")
    assert kv.status()["run"]["result"]["verified"]
    after = kv.get("/state", "A")
    assert after["boot_id"] != before["boot_id"]
    assert kv.get("/kv/inventory", "A")["value"] == 95
    assert len(after["recovery"]["replayed"]) == 2


def test_idempotent_replay_uses_checkpoint_baseline(kv):
    kv.run("recovery")
    kv.status()
    first = kv.post("/recover", service="A")
    second = kv.post("/recover", service="A")
    assert first["value"] == second["value"] == 95
    assert first["replayed"] == second["replayed"] and len(first["replayed"]) == 2
    assert kv.get("/kv/inventory", "A")["value"] == 95


def test_recreate_preserves_durable_storage(kv):
    kv.post("/kv", {"id": "persistent", "key": "proof", "value": "survives"}, "A")
    old = kv.get("/health", "A")["boot_id"]
    kv.stop("A"); kv.start("A", recreate=True)
    assert kv.get("/health", "A")["boot_id"] != old
    assert kv.get("/kv/proof", "A")["value"] == "survives"
    # In process mode this proves the same durable directory, not a Docker volume.


def test_dashboard_real_health_and_no_docker_control(kv):
    kv.stop("C")
    state = wait(lambda: (s if not (s := kv.get("/api/state"))["services"]["C"]["alive"] else None))
    assert state["nodes"]["C"]["unreachable"]
    assert kv.http.get(kv.urls["gateway"] + "/").status_code == 200
    assert kv.http.post(kv.urls["gateway"] + "/api/process/C/restart").status_code == 403
    kv.start("C")


def test_prepared_participant_never_decides_alone(kv):
    kv.run("commit", "coordinator_crash"); kv.status("WAITING")
    kv.stop("coordinator"); kv.stop("B"); kv.start("B")
    state = kv.get("/state", "B")
    assert state["transactions"][-1]["state"] == "PREPARED" and state["locks"]
    assert state["kv"]["balance"] == 100
    kv.start("coordinator")
    assert kv.status()["run"]["result"]["decision"] == "ABORT"


def test_offline_reset_preserves_live_node_data(kv):
    kv.post("/kv", {"id": "keep", "key": "proof", "value": 42}, "A")
    kv.stop("rpc")
    assert kv.http.post(kv.urls["gateway"] + "/api/reset").status_code == 503
    assert kv.get("/kv/proof", "A")["value"] == 42
    kv.start("rpc")


def test_reset_cannot_erase_prepared_state(kv):
    kv.run("commit", "coordinator_crash"); kv.status("WAITING")
    assert kv.http.post(kv.urls["gateway"] + "/api/reset").status_code == 409
    assert all(kv.get("/state", node)["locks"] for node in "ABC")
    kv.stop("coordinator"); kv.start("coordinator")
    kv.status()


def test_custom_transaction_is_visible_and_id_conflicts_rejected(kv):
    body = {"id": "custom", "pace_ms": 0, "writes": {"A": {"balance": 80}, "B": {"balance": 120}, "C": {"last_transaction": "custom"}}}
    kv.post("/api/transactions", body)
    assert kv.status()["run"]["result"]["verified"]
    assert kv.get("/kv/balance", "A")["value"] == 80
    assert kv.http.post(kv.urls["coordinator"] + "/transactions", json={**body, "writes": {"A": {"balance": 0}, "B": {"balance": 200}, "C": {"last_transaction": "changed"}}}).status_code == 409


def test_stale_prepare_and_redo_id_conflicts(kv):
    kv.post("/kv", {"id": "changed", "key": "balance", "value": 99}, "A")
    vote = kv.post("/prepare", {"id": "stale", "writes": {"balance": 90}, "expected": {"balance": 100}}, "A")
    assert vote["vote"] == "NO" and not kv.get("/state", "A")["locks"]
    kv.post("/operations", {"id": "event", "delta": -5}, "A")
    assert kv.http.post(kv.urls["A"] + "/operations", json={"id": "event", "delta": -6}).status_code == 409
    assert kv.http.post(kv.urls["A"] + "/kv", json={"id": "unsafe", "key": "inventory", "value": 0}).status_code == 409
    assert kv.get("/kv/inventory", "A")["value"] == 95


def test_gateway_development_origin_and_foreign_origin(kv):
    response = kv.http.options(kv.urls["gateway"] + "/api/runs", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200 and response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert kv.http.post(kv.urls["gateway"] + "/api/reset", headers={"Origin": "https://unrelated.invalid"}).status_code == 403


def test_receiver_crash_scenario_waits_for_real_external_stop(kv):
    rid = kv.run("group", "node_down")
    wait(lambda: kv.get('/api/state')['run']['result'] and kv.get('/api/state')['run']['result'].get('stage') == 'AWAIT_RECEIVER_STOP')
    assert not kv.get('/state', 'B')['group']
    kv.stop('B')
    assert kv.status('PARTIAL')['run']['result']['missing_nodes'] == ['B']
    kv.start('B')
    assert kv.post('/api/group/catchup', {'target':'B','stream':rid})['verified']


def test_catchup_after_step_run_does_not_wait_on_finished_gate(kv):
    rid = kv.run('group', 'node_down', mode='step')
    wait(lambda: kv.get('/api/state')['run']['result'] and kv.get('/api/state')['run']['result'].get('stage') == 'AWAIT_RECEIVER_STOP')
    kv.stop('B')
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = kv.get('/api/state')['run']
        if run['status'] == 'PARTIAL':
            break
        if run['status'] == 'WAITING':
            kv.post('/api/step')
        time.sleep(.1)
    else:
        raise AssertionError('Step multicast did not finish')
    kv.start('B')
    assert kv.post('/api/group/catchup', {'target':'B','stream':rid})['verified']

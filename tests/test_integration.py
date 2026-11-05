"""End-to-end HTTP tests: real supervisor, coordinator and three node processes."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"COMPLETED", "FAILED", "PARTIAL", "BLOCKED", "DECISION_PENDING", "INTERRUPTED"}


def free_base():
    for base in range(9200, 9800, 7):
        sockets = []
        try:
            for port in (base, base + 1, base + 101, base + 102, base + 103):
                sock = socket.socket()
                sockets.append(sock)
                sock.bind(("127.0.0.1", port))
            return base
        except OSError:
            pass
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No free test port range")


@pytest.fixture(scope="session")
def lab(tmp_path_factory):
    data = tmp_path_factory.mktemp("fault-lab")
    base = free_base()
    env = {**os.environ, "LAB_DATA": str(data), "LAB_PORT": str(base), "LAB_PACE": "0.01", "LAB_TIMEOUT": "0.45"}
    with open(data / "supervisor.log", "w") as output:
        proc = subprocess.Popen([sys.executable, "-m", "backend"], cwd=ROOT, env=env, stdout=output, stderr=output)
        client = httpx.Client(base_url=f"http://127.0.0.1:{base}", timeout=20, trust_env=False)
        try:
            for _ in range(160):
                if proc.poll() is not None:
                    pytest.fail((data / "supervisor.log").read_text())
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Supervisor startup timed out")
            yield client, base
        finally:
            # Terminate children explicitly: Windows terminate() does not deliver Ctrl+C.
            for target in ("A", "B", "C", "coordinator"):
                try:
                    client.post(f"/api/process/{target}/crash")
                except httpx.HTTPError:
                    pass
            client.close()
            proc.terminate()
            proc.wait(timeout=10)


@pytest.fixture(autouse=True)
def isolate(lab):
    client, _ = lab
    response = client.post("/api/reset")
    assert response.status_code == 200, response.text


def wait_state(client, predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        state = client.get("/api/state").json()
        if predicate(state):
            return state
        time.sleep(0.08)
    pytest.fail(f"Condition timed out: {state}")


def run(lab, module, scenario="normal", **kwargs):
    client, _ = lab
    response = client.post("/api/runs", json={"module": module, "scenario": scenario, **kwargs})
    assert response.status_code == 200, response.text
    state = wait_state(client, lambda s: s["run"] and s["run"]["status"] in TERMINAL)
    assert not any(e["kind"] == "ERROR" for e in state["events"]), state
    return state


def kinds(state):
    return [event["kind"] for event in state["events"]]


def test_independent_processes(lab):
    client, _ = lab
    health = client.get("/api/health").json()
    pids = [p["pid"] for p in health["processes"].values()]
    assert len(set(pids + [health["pid"]])) == 5
    assert all(p["alive"] for p in health["processes"].values())


def test_successful_rpc(lab):
    state = run(lab, "rpc")
    assert state["run"]["status"] == "COMPLETED"
    assert state["nodes"]["A"]["counters"]["rpc"] == 1
    assert state["run"]["result"]["attempts"] == 1


def test_lost_request_retry(lab):
    state = run(lab, "rpc", "lost_request")
    assert state["run"]["result"]["attempts"] == 2
    assert state["nodes"]["A"]["counters"]["rpc"] == 1
    assert {"REQUEST_LOST", "TIMEOUT", "RETRY"}.issubset(kinds(state))


@pytest.mark.parametrize("deduplicate,count", [(True, 1), (False, 2)])
def test_lost_response_duplicate_handling(lab, deduplicate, count):
    state = run(lab, "rpc", "lost_response", deduplicate=deduplicate)
    assert state["run"]["result"]["attempts"] == 2
    assert state["nodes"]["A"]["counters"]["rpc"] == count
    assert "RESPONSE_LOST" in kinds(state)
    if deduplicate:
        assert "DUPLICATE_SUPPRESSED" in kinds(state)


def test_rpc_no_retry_unknown_outcome(lab):
    state = run(lab, "rpc", "lost_response", retry=False)
    assert state["run"]["status"] == "FAILED"
    assert state["nodes"]["A"]["counters"]["rpc"] == 1


def test_rpc_unavailable_bounded(lab):
    state = run(lab, "rpc", "server_down", max_attempts=2)
    assert state["run"]["status"] == "FAILED"
    assert state["run"]["result"]["attempts"] == 2
    assert state["nodes"]["A"]["counters"]["rpc"] == 0


def test_delay_timeout_and_duplicate_transport(lab):
    state = run(lab, "rpc", "delay")
    assert "DELAY" in kinds(state) and "TIMEOUT" in kinds(state)
    assert state["nodes"]["A"]["counters"]["rpc"] == 1
    state = run(lab, "rpc", "duplicate")
    assert "DUPLICATE_SUPPRESSED" in kinds(state)
    assert state["nodes"]["A"]["counters"]["rpc"] == 1


def test_multicast_retransmission(lab):
    state = run(lab, "group", "lost_message", target="B")
    assert state["run"]["status"] == "COMPLETED"
    assert "RETRANSMIT" in kinds(state)
    assert all(len(n["multicast"]) == 1 for n in state["nodes"].values())
    sends = [e["target"] for e in state["events"] if e["kind"] == "RETRANSMIT"]
    assert sends == ["B"]


def test_multicast_duplicate_suppression(lab):
    state = run(lab, "group", "duplicate")
    assert all(len(n["multicast"]) == 1 for n in state["nodes"].values())
    assert "DUPLICATE_SUPPRESSED" in kinds(state)


def test_multicast_unavailable(lab):
    state = run(lab, "group", "node_down", target="C")
    assert state["run"]["status"] == "PARTIAL"
    assert state["run"]["result"]["missing"] == ["C"]
    assert len(state["nodes"]["A"]["multicast"]) == 1


def test_two_phase_commit(lab):
    client, base = lab
    state = run(lab, "commit")
    assert state["run"]["result"]["decision"] == "COMMIT"
    assert all(n["counters"]["commit"] == 10 for n in state["nodes"].values())
    assert all(n["transactions"][0]["state"] == "COMMIT" for n in state["nodes"].values())
    # An acknowledged COMMIT can be delivered repeatedly without changing business state.
    tx = state["transactions"][0]["id"]
    response = httpx.post(f"http://127.0.0.1:{base + 101}/decision", json={"id": tx, "decision": "COMMIT"}, trust_env=False)
    assert response.json()["duplicate"]
    assert client.get("/api/state").json()["nodes"]["A"]["counters"]["commit"] == 10
    durable = next(e["seq"] for e in state["events"] if e["kind"] == "DURABLE_DECISION")
    decisions = [e["seq"] for e in state["events"] if e["kind"] == "SEND" and e["data"]["path"] == "/decision"]
    assert all(seq > durable for seq in decisions)


def test_two_phase_abort(lab):
    state = run(lab, "commit", "vote_no")
    assert state["run"]["result"]["decision"] == "ABORT"
    assert all(n["transactions"][0]["state"] == "ABORT" for n in state["nodes"].values())
    assert all(n["counters"]["commit"] == 0 for n in state["nodes"].values())


def test_participant_failure_and_redelivery(lab):
    client, _ = lab
    state = run(lab, "commit", "participant_crash")
    assert state["run"]["status"] == "DECISION_PENDING"
    assert state["run"]["result"]["decision"] == "ABORT"
    assert not state["services"]["B"]["alive"]
    assert client.post("/api/resolve").status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")
    assert all(n["transactions"][0]["state"] == "ABORT" for n in state["nodes"].values())


def test_coordinator_crash_blocks_prepared_nodes(lab):
    client, _ = lab
    state = run(lab, "commit", "coordinator_crash")
    assert state["run"]["status"] == "BLOCKED"
    state = wait_state(client, lambda s: not s["services"]["coordinator"]["alive"])
    time.sleep(1)
    state = client.get("/api/state").json()
    assert all(n["transactions"][0]["state"] == "PREPARED" for n in state["nodes"].values())
    assert all(n["counters"]["commit"] == 0 for n in state["nodes"].values())
    assert client.post("/api/runs", json={"module": "rpc"}).status_code == 409
    assert client.post("/api/resolve").status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")
    assert all(n["transactions"][0]["state"] == "COMMIT" for n in state["nodes"].values())
    assert "COORDINATOR_RECOVERY" in kinds(state)


def test_checkpoint_creation(lab):
    state = run(lab, "recovery", "checkpoint")
    assert state["nodes"]["A"]["checkpoint"]["value"] == 10
    assert state["nodes"]["A"]["checkpoint"]["seq"] == 2


def test_process_crash_and_recovery(lab):
    state = run(lab, "recovery", "crash_recover")
    result = state["run"]["result"]
    assert result["before"] == result["after"] == 20
    assert result["before_pid"] != result["after_pid"]
    assert len(result["recovery"]["replayed"]) == 2


def test_log_replay_without_duplicate_application(lab):
    state = run(lab, "recovery", "idempotent")
    assert state["nodes"]["A"]["memory_value"] == 20
    assert state["nodes"]["A"]["counters"]["recovery"] == 20
    assert len(state["nodes"]["A"]["operations"]) == 4
    proof = next(e for e in state["events"] if e["kind"] == "IDEMPOTENCE")
    assert proof["data"]["duplicate"]["duplicate"]
    assert proof["data"]["replay"]["value"] == 20


def test_step_mode_gates_real_execution(lab):
    client, _ = lab
    response = client.post("/api/runs", json={"module": "rpc", "mode": "step"})
    assert response.status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "WAITING")
    assert state["nodes"]["A"]["counters"]["rpc"] == 0
    assert client.post("/api/step").status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")
    assert state["nodes"]["A"]["counters"]["rpc"] == 1


def test_sse_stream_and_validation(lab):
    client, _ = lab
    with client.stream("GET", "/api/events") as response:
        assert response.status_code == 200
        lines = response.iter_lines()
        assert next(lines) == "event: snapshot"
        assert next(lines).startswith("data: ")
    assert client.post("/api/runs", json={"module": "rpc", "scenario": "invalid"}).status_code == 422
    assert client.post("/api/runs", json={"module": "rpc", "max_attempts": 99}).status_code == 422


def test_reset_and_sequential_scenarios(lab):
    client, _ = lab
    run(lab, "commit", "coordinator_crash")
    assert client.post("/api/reset").status_code == 200
    state = client.get("/api/state").json()
    assert state["run"] is None and state["events"] == []
    assert all(not n["transactions"] for n in state["nodes"].values())
    state = run(lab, "rpc")
    assert state["nodes"]["A"]["counters"]["rpc"] == 1


def test_commit_decision_survives_crash_before_distribution(lab):
    client, _ = lab
    assert client.post("/api/runs", json={"module": "commit", "mode": "step"}).status_code == 200
    wait_state(client, lambda s: s["run"]["status"] == "WAITING")
    for node in ("A", "B", "C"):
        assert client.post("/api/step").status_code == 200
        wait_state(client, lambda s: s["run"]["status"] == "WAITING" and node in s["transactions"][0]["votes"])
    state = client.get("/api/state").json()
    assert state["transactions"][0]["state"] == "COMMIT"
    assert all(n["transactions"][0]["state"] == "PREPARED" for n in state["nodes"].values())
    assert client.post("/api/process/coordinator/crash").status_code == 200
    assert client.post("/api/resolve").status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")
    assert state["transactions"][0]["state"] == "COMMIT"
    assert all(n["counters"]["commit"] == 10 for n in state["nodes"].values())


def test_rpc_and_multicast_dedup_survive_node_restart(lab):
    client, base = lab
    state = run(lab, "rpc")
    rid = state["run"]["result"]["request_id"]
    assert client.post("/api/process/A/restart").status_code == 200
    with httpx.Client(base_url=f"http://127.0.0.1:{base + 101}", trust_env=False) as node:
        response = node.post("/rpc", json={"id": rid, "deduplicate": True})
        assert response.json()["duplicate"]
        assert node.get("/state").json()["counters"]["rpc"] == 1
        assert not node.post("/multicast", json={"id": "durable-message"}).json()["duplicate"]
    assert client.post("/api/process/A/restart").status_code == 200
    with httpx.Client(base_url=f"http://127.0.0.1:{base + 101}", trust_env=False) as node:
        response = node.post("/multicast", json={"id": "durable-message"})
        assert response.json()["duplicate"]
        assert response.json()["delivery_count"] == 1


def test_reset_cancels_waiting_worker_and_prevents_old_writes(lab):
    client, _ = lab
    assert client.post("/api/runs", json={"module": "recovery", "scenario": "idempotent", "mode": "step"}).status_code == 200
    wait_state(client, lambda s: s["run"]["status"] == "WAITING")
    assert client.post("/api/step").status_code == 200
    wait_state(client, lambda s: s["run"]["status"] == "WAITING" and s["nodes"]["A"]["memory_value"] == 5)
    assert client.post("/api/reset").status_code == 200
    state = run(lab, "rpc")
    assert state["nodes"]["A"]["memory_value"] == 0
    assert not state["nodes"]["A"]["operations"]


def test_reset_rejects_late_lifecycle_callback_from_old_scenario(lab):
    client, _ = lab
    state = run(lab, "rpc")
    old_run = state["run"]["id"]
    assert client.post("/api/reset").status_code == 200
    # A callback may have been queued on the manager lock when reset cancelled its worker.
    response = client.post("/internal/process/A/crash", json={"run_id": old_run})
    assert response.status_code == 409
    assert client.get("/api/health").json()["processes"]["A"]["alive"]
    state = run(lab, "rpc")
    assert state["nodes"]["A"]["counters"]["rpc"] == 1


def test_runtime_pause_step_resume_and_speed(lab):
    client, _ = lab
    response = client.post("/api/runs", json={"module": "recovery", "scenario": "idempotent",
                                             "paused": True, "pace_ms": 1200})
    assert response.status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "WAITING")
    assert state["nodes"]["A"]["memory_value"] == 0
    time.sleep(0.2)
    assert client.get("/api/state").json()["nodes"]["A"]["memory_value"] == 0
    assert client.post("/api/step").status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "WAITING" and s["nodes"]["A"]["memory_value"] == 5)
    assert state["run"]["config"]["paused"]
    assert client.post("/api/control", json={"pace_ms": 0, "paused": False}).status_code == 200
    state = wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")
    assert state["nodes"]["A"]["memory_value"] == 20
    assert state["run"]["config"]["pace_ms"] == 0
    assert "RESUME" in kinds(state)


def test_runtime_control_validation(lab):
    client, _ = lab
    assert client.post("/api/control", json={"paused": True}).status_code == 409
    assert client.post("/api/runs", json={"module": "rpc", "pace_ms": -1}).status_code == 422
    assert client.post("/api/runs", json={"module": "rpc", "mode": "step"}).status_code == 200
    wait_state(client, lambda s: s["run"]["status"] == "WAITING")
    assert client.post("/api/control", json={"paused": False}).status_code == 409
    assert client.post("/api/control", json={"pace_ms": 3001}).status_code == 422


def test_health_spa_fallback_and_unknown_api(lab):
    client, _ = lab
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    assert client.get("/commit").status_code == 200
    assert "text/html" in client.get("/recovery").headers["content-type"]
    assert client.get("/api/not-found").status_code == 404
    assert client.get("/assets/not-found.js").status_code == 404
    assert client.get("/missing.js").status_code == 404


def test_cross_origin_mutations_are_rejected(lab):
    client, _ = lab
    response = client.post("/api/runs", json={"module": "rpc"}, headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
    assert client.get("/api/state").json()["run"] is None
    assert client.post("/api/runs", json={"module": "rpc"}, headers={"Origin": str(client.base_url).rstrip("/")}).status_code == 200
    wait_state(client, lambda s: s["run"]["status"] == "COMPLETED")


def test_public_gateway_restricts_access(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import manager
    token = "test-only-gateway-token-with-32-characters"
    monkeypatch.setattr(manager, "PUBLIC", True)
    monkeypatch.setattr(manager, "GATEWAY_TOKEN", token)
    monkeypatch.delenv("LAB_ALLOW_PROCESS_CONTROL", raising=False)
    client = TestClient(manager.app)
    assert client.get("/healthz").status_code == 200
    for path in ("/api/health", "/api/state", "/api/events", "/docs", "/openapi.json", "/commit"):
        assert client.get(path).status_code == 401
    headers = {"X-Lab-Gateway-Token": token}
    assert client.get("/api/health", headers=headers).status_code == 200
    assert client.post("/api/process/A/crash", headers=headers).status_code == 403
    assert client.post("/internal/process/A/crash", json={"run_id": "forged"}).status_code == 403
    client.close()


def test_public_mode_refuses_missing_secret(tmp_path):
    env = {**os.environ, "LAB_PUBLIC": "true", "LAB_DATA": str(tmp_path)}
    env.pop("LAB_GATEWAY_TOKEN", None)
    result = subprocess.run([sys.executable, "-c", "import backend.manager"], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "LAB_PUBLIC requires LAB_GATEWAY_TOKEN" in result.stderr


def test_explicit_cors_origin_and_preflight(tmp_path):
    script = """
from fastapi.testclient import TestClient
from backend.manager import app
client = TestClient(app)
origin = 'https://classroom.example'
response = client.options('/api/runs', headers={
    'Origin': origin, 'Access-Control-Request-Method': 'POST',
    'Access-Control-Request-Headers': 'content-type'})
assert response.status_code == 200
assert response.headers['access-control-allow-origin'] == origin
assert response.headers['access-control-allow-credentials'] == 'true'
response = client.get('/api/health', headers={'Origin': origin})
assert response.status_code == 200
assert response.headers['access-control-allow-origin'] == origin
response = client.options('/api/runs', headers={
    'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
assert response.status_code == 400
client.close()
"""
    env = {**os.environ, "LAB_ALLOWED_ORIGINS": "https://classroom.example",
           "LAB_PUBLIC": "false", "LAB_DATA": str(tmp_path)}
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr

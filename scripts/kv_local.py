"""Optional six-process host runner, explicitly NOT Docker. Ctrl+C stops children."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19100)
    parser.add_argument("--data", default=str(ROOT / "data" / "kv-local"))
    args = parser.parse_args()
    services = ["gateway", "coordinator", "rpc", "A", "B", "C"]
    urls = {name: f"http://127.0.0.1:{args.port + i}" for i, name in enumerate(services)}
    for port in range(args.port, args.port + 6):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    data = Path(args.data).resolve(); data.mkdir(parents=True, exist_ok=True)
    children, handles = {}, []
    try:
        for name in services:
            folder = data / name; folder.mkdir(exist_ok=True)
            env = {**os.environ, "KV_RUNTIME": "process", "LAB_DATA": str(folder), "KV_SERVICE": name, "KV_COORDINATOR": urls["coordinator"], "KV_RPC_SERVER": urls["rpc"], "KV_PEERS": json.dumps({node: urls[node] for node in "ABC"})}
            module = "kv_gateway" if name == "gateway" else "kv_coordinator" if name == "coordinator" else "kv_node"
            handle = open(folder / "service.log", "a", encoding="utf-8"); handles.append(handle)
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            children[name] = subprocess.Popen([sys.executable, "-m", "uvicorn", f"backend.{module}:app", "--host", "127.0.0.1", "--port", str(args.port + services.index(name)), "--log-level", "warning"], env=env, cwd=ROOT, stdout=handle, stderr=handle, creationflags=flags)
            for _ in range(100):
                try:
                    with urlopen(urls[name] + "/health", timeout=.5) as response:
                        if json.load(response)["pid"] == children[name].pid:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError(f"{name} did not start; see {folder / 'service.log'}")
        (data / "processes.json").write_text(json.dumps({name: {"pid": proc.pid, "url": urls[name]} for name, proc in children.items()}, indent=2), encoding="utf-8")
        print(f"REAL PROCESSES (NOT DOCKER): {urls['gateway']}/rpc", flush=True)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in children.values():
            if proc.poll() is None:
                proc.terminate(); proc.wait(timeout=10)
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    main()

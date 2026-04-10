"""
Smoke test da API HTTP interna do agente.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(url: str, timeout: float = 20.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("status") == "ok":
                    return payload
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("HTTP service nao ficou pronto a tempo")


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    port = free_port()
    env = os.environ.copy()
    proc = subprocess.Popen(
        ["python3", "agent/http_service.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        health = wait_health(f"http://127.0.0.1:{port}/healthz")
        if health.get("status") != "ok":
            raise RuntimeError(f"Healthcheck invalido: {health}")

        response = post_json(
            f"http://127.0.0.1:{port}/v1/ask",
            {"question": "Qual foi o ultimo workflow que falhou em produção?"},
        )
        answer = str(response.get("answer") or "").strip()
        if not answer:
            raise RuntimeError(f"Resposta vazia: {response}")

        print("OK: API HTTP respondeu com healthcheck e resposta de negocio.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

        stderr = (proc.stderr.read() or "").strip() if proc.stderr else ""
        if proc.returncode not in (0, -15) and stderr:
            print(stderr, file=sys.stderr)
            raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()

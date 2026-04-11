"""
Valida a API HTTP com autenticacao bearer.
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


def post(url: str, payload: dict, headers: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main():
    port = free_port()
    env = os.environ.copy()
    env["AGENT_HTTP_AUTH_ENABLED"] = "true"
    env["AGENT_HTTP_BEARER_TOKEN"] = "test-token"
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
        if "checks" not in health:
            raise RuntimeError(f"Healthcheck sem checks: {health}")

        status, payload = post(
            f"http://127.0.0.1:{port}/v1/ask",
            {"question": "Qual foi o ultimo workflow que falhou em produção?"},
        )
        if status != 401:
            raise RuntimeError(f"Esperava 401 sem token, recebi {status}: {payload}")

        status, payload = post(
            f"http://127.0.0.1:{port}/v1/ask",
            {"question": "Qual foi o ultimo workflow que falhou em produção?"},
            headers={"Authorization": "Bearer test-token"},
        )
        if status != 200 or not str(payload.get("answer") or "").strip():
            raise RuntimeError(f"Resposta invalida com token: {status} {payload}")

        print("OK: API HTTP protegeu o endpoint e respondeu com bearer token.")
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

"""
Valida semântica operacional de healthcheck quando dependências estão degradadas.
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


def get_json(url: str, timeout: float = 20.0) -> tuple[int, dict]:
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"HTTP service nao respondeu a tempo: {last_error}")


def post_large_payload(url: str) -> tuple[int, dict]:
    body = json.dumps({"question": "x" * 256}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main():
    port = free_port()
    env = os.environ.copy()
    env["AGENT_PROVIDER"] = "groq"
    env["GROQ_API_KEY"] = ""
    env["ELASTICSEARCH_URL"] = "http://127.0.0.1:1"
    env["ELASTICSEARCH_TIMEOUT"] = "1"
    env["AGENT_HTTP_MAX_BODY_BYTES"] = "128"
    proc = subprocess.Popen(
        ["python3", "agent/http_service.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        status, health = get_json(f"http://127.0.0.1:{port}/healthz")
        if status != 200 or health.get("status") != "ok" or health.get("ready") is not False:
            raise RuntimeError(f"healthz deveria responder vivo e degradado: {status} {health}")
        checks = health.get("checks") or {}
        if checks.get("provider", {}).get("ready") is not False:
            raise RuntimeError(f"Provider deveria estar indisponivel: {health}")
        if checks.get("elasticsearch", {}).get("ready") is not False:
            raise RuntimeError(f"Elasticsearch deveria estar indisponivel: {health}")

        status, ready = get_json(f"http://127.0.0.1:{port}/readyz")
        if status != 503 or ready.get("status") != "not_ready" or ready.get("ready") is not False:
            raise RuntimeError(f"readyz deveria responder 503 quando degradado: {status} {ready}")

        status, payload = post_large_payload(f"http://127.0.0.1:{port}/v1/ask")
        if status != 413 or payload.get("error") != "payload_too_large":
            raise RuntimeError(f"Payload grande deveria retornar 413: {status} {payload}")

        print("OK: healthz/readyz degradados e limite de payload validados.")
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

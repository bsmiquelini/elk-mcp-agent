"""
Valida o endpoint HTTP de relatorio executivo.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
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
        wait_health(f"http://127.0.0.1:{port}/healthz")
        response = post_json(
            f"http://127.0.0.1:{port}/v1/report",
            {
                "prompt": "Quero um resumo executivo de CI/CD com foco em risco operacional e PRD",
                "time_range": "30d",
                "include": "overview,risk,prd",
                "title": "Resumo Executivo de Teste",
            },
        )
        output_path = Path(str(response.get("output_path") or ""))
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        if response.get("section_count", 0) <= 0:
            raise RuntimeError(f"Relatorio sem secoes: {response}")
        if not output_path.exists():
            raise RuntimeError(f"Arquivo HTML nao foi gerado: {output_path}")
        html = output_path.read_text(encoding="utf-8")
        if "Resumo Executivo de Teste" not in html:
            raise RuntimeError("Titulo esperado nao encontrado no HTML do relatorio")
        print("OK: endpoint /v1/report gerou relatorio executivo real.")
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

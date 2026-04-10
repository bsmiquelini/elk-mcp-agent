"""
API HTTP simples para consumo interno do agente.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from config_loader import load_config
from provider_health import check_provider
from runtime import CONFIG_PATH, open_agent_runtime


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _build_handler(config_path: str):
    config = load_config(config_path)
    domain_name = config.get("domain", {}).get("name", "ELK MCP Agent")

    class AgentHandler(BaseHTTPRequestHandler):
        server_version = "ELKMCPAgentHTTP/1.0"

        def _send_json(self, status: int, payload: dict):
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args):
            return

        def do_GET(self):
            route = urlparse(self.path).path
            if route not in ("/healthz", "/readyz"):
                self._send_json(404, {"error": "not_found"})
                return
            provider_ok = check_provider(config, fatal=False)
            self._send_json(
                200,
                {
                    "status": "ok",
                    "ready": provider_ok,
                    "service": domain_name,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        def do_POST(self):
            route = urlparse(self.path).path
            if route != "/v1/ask":
                self._send_json(404, {"error": "not_found"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "invalid_json"})
                return

            question = str(payload.get("question") or "").strip()
            if not question:
                self._send_json(400, {"error": "question_required"})
                return

            try:
                answer = asyncio.run(self._answer(question))
            except Exception as exc:
                self._send_json(
                    500,
                    {
                        "error": "agent_error",
                        "message": str(exc),
                    },
                )
                return

            self._send_json(
                200,
                {
                    "question": question,
                    "answer": answer,
                    "service": domain_name,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        async def _answer(self, question: str) -> str:
            async with open_agent_runtime(config_path) as runtime:
                return await runtime.ask(question)

    return AgentHandler


def main():
    default_config = load_config(str(CONFIG_PATH))
    service_cfg = default_config.get("agent", {}).get("service", {})

    parser = argparse.ArgumentParser(description="ELK MCP Agent HTTP service")
    parser.add_argument("--host", default=service_cfg.get("host", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(service_cfg.get("port", 8787)))
    parser.add_argument("--config", default=str(CONFIG_PATH))
    args = parser.parse_args()

    handler = _build_handler(args.config)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"ELK MCP Agent HTTP listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

"""
API HTTP simples para consumo interno do agente.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
import uuid
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from config_loader import load_config
from logging_utils import get_logger, log_event
from provider_health import check_provider
from runtime import CONFIG_PATH, open_agent_runtime


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class RuntimeWorker:
    def __init__(self, config_path: str, *, request_timeout_seconds: int, logger):
        self.config_path = config_path
        self.request_timeout_seconds = request_timeout_seconds
        self.logger = logger
        self.loop = None
        self.thread = None
        self.runtime = None
        self.context = None
        self.ready = threading.Event()
        self.failed = None
        self.ask_lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self._run, name="agent-runtime", daemon=True)
        self.thread.start()
        self.ready.wait(timeout=30)
        if self.failed:
            raise self.failed
        if not self.runtime:
            raise RuntimeError("Runtime do agente não ficou pronto.")

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._startup())
        except Exception as exc:
            self.failed = exc
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()
        self.loop.run_until_complete(self._shutdown())
        self.loop.close()

    async def _startup(self):
        self.context = open_agent_runtime(self.config_path)
        self.runtime = await self.context.__aenter__()
        log_event(self.logger, "info", "runtime_started")

    async def _shutdown(self):
        if self.context is not None:
            await self.context.__aexit__(None, None, None)
            log_event(self.logger, "info", "runtime_stopped")

    def ask(self, question: str) -> str:
        if not self.loop or not self.runtime:
            raise RuntimeError("Runtime do agente indisponível.")
        with self.ask_lock:
            future = asyncio.run_coroutine_threadsafe(self.runtime.ask(question), self.loop)
            return future.result(timeout=self.request_timeout_seconds)

    def stop(self):
        if not self.loop:
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(timeout=10)


def _extract_token(header_value: str | None) -> str:
    if not header_value:
        return ""
    value = str(header_value).strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


def _is_authorized(headers, auth_cfg: dict) -> bool:
    if not auth_cfg.get("enabled", False):
        return True

    expected = str(auth_cfg.get("bearer_token") or "").strip()
    if not expected:
        return False

    header_name = str(auth_cfg.get("header_name", "Authorization"))
    incoming = _extract_token(headers.get(header_name))
    return bool(incoming) and incoming == expected


def _build_handler(config_path: str):
    config = load_config(config_path)
    domain_name = config.get("domain", {}).get("name", "ELK MCP Agent")
    service_cfg = config.get("agent", {}).get("service", {})
    request_timeout_seconds = int(service_cfg.get("request_timeout_seconds", 180))
    logger = get_logger(
        "agent.http",
        json_output=bool(service_cfg.get("json_logs", True)),
        level=str(service_cfg.get("log_level", "INFO")),
    )
    runtime_worker = RuntimeWorker(
        config_path,
        request_timeout_seconds=request_timeout_seconds,
        logger=logger,
    )
    runtime_worker.start()

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

        def _request_id(self) -> str:
            return self.headers.get("X-Request-Id") or str(uuid.uuid4())

        def _send_unauthorized(self, request_id: str):
            self._send_json(
                401,
                {
                    "error": "unauthorized",
                    "request_id": request_id,
                },
            )

        def do_GET(self):
            route = urlparse(self.path).path
            request_id = self._request_id()
            if route not in ("/healthz", "/readyz"):
                self._send_json(404, {"error": "not_found"})
                return
            provider_ok = check_provider(config, fatal=False)
            log_event(
                logger,
                "info",
                "healthcheck",
                route=route,
                request_id=request_id,
                provider_ready=provider_ok,
            )
            self._send_json(
                200,
                {
                    "status": "ok",
                    "ready": provider_ok,
                    "service": domain_name,
                    "request_id": request_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        def do_POST(self):
            route = urlparse(self.path).path
            request_id = self._request_id()
            if route != "/v1/ask":
                self._send_json(404, {"error": "not_found"})
                return
            auth_cfg = service_cfg.get("auth", {})
            if not _is_authorized(self.headers, auth_cfg):
                log_event(logger, "warning", "request_denied", route=route, request_id=request_id)
                self._send_unauthorized(request_id)
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

            started = time.perf_counter()
            try:
                answer = runtime_worker.ask(question)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                log_event(
                    logger,
                    "error",
                    "request_failed",
                    route=route,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    error=str(exc),
                )
                self._send_json(
                    500,
                    {
                        "error": "agent_error",
                        "message": str(exc),
                        "request_id": request_id,
                    },
                )
                return

            latency_ms = int((time.perf_counter() - started) * 1000)
            log_event(
                logger,
                "info",
                "request_completed",
                route=route,
                request_id=request_id,
                latency_ms=latency_ms,
                question_length=len(question),
            )
            self._send_json(
                200,
                {
                    "question": question,
                    "answer": answer,
                    "service": domain_name,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    AgentHandler.runtime_worker = runtime_worker
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
        runtime_worker = getattr(handler, "runtime_worker", None)
        if runtime_worker:
            runtime_worker.stop()
        server.server_close()


if __name__ == "__main__":
    main()

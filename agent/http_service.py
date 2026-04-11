"""
API HTTP simples para consumo interno do agente.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from config_loader import load_config
from executive_report import generate_sections, parse_include_sections, render_report, slugify
from logging_utils import get_logger, log_event
from runtime import AgentRuntimeWorker, CONFIG_PATH
from service_health import get_elasticsearch_status, get_provider_status


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _resolve_report_output(root: Path, prompt: str, output: str | None) -> Path:
    reports_dir = root / "artifacts" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(output) if output else reports_dir / f"{slugify(prompt)}.html"
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


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
    max_body_bytes = int(service_cfg.get("max_body_bytes", 1_048_576))
    logger = get_logger(
        "agent.http",
        json_output=bool(service_cfg.get("json_logs", True)),
        level=str(service_cfg.get("log_level", "INFO")),
    )
    provider_status = get_provider_status(config)
    elasticsearch_status = get_elasticsearch_status(config)
    log_event(
        logger,
        "info",
        "http_service_bootstrap",
        provider=provider_status.get("provider"),
        provider_ready=provider_status.get("ready"),
        provider_model=provider_status.get("model"),
        provider_endpoint=provider_status.get("endpoint"),
        elasticsearch_ready=elasticsearch_status.get("ready"),
        elasticsearch_url=elasticsearch_status.get("url"),
        elasticsearch_auth_mode=elasticsearch_status.get("auth_mode"),
    )
    runtime_worker = AgentRuntimeWorker(config_path)
    runtime_started = runtime_worker.start(raise_on_failure=False)
    if runtime_started:
        log_event(
            logger,
            "info",
            "runtime_started",
            schema_cache_ttl_seconds=config.get("agent", {}).get("runtime", {}).get("schema_cache_ttl_seconds", 0),
        )
    else:
        log_event(
            logger,
            "warning",
            "runtime_start_degraded",
            detail=runtime_worker.status().get("message"),
        )

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
            provider_ok = get_provider_status(config)
            elastic_ok = get_elasticsearch_status(config)
            if route == "/readyz" and provider_ok.get("ready") and elastic_ok.get("ready") and not runtime_worker.status().get("ready"):
                runtime_worker.start(raise_on_failure=False)
            runtime_ok = runtime_worker.status()
            ready = bool(provider_ok.get("ready") and elastic_ok.get("ready") and runtime_ok.get("ready"))
            status_code = 200 if route == "/healthz" or ready else 503
            log_event(
                logger,
                "info",
                "healthcheck",
                route=route,
                request_id=request_id,
                provider_ready=provider_ok.get("ready"),
                elasticsearch_ready=elastic_ok.get("ready"),
                runtime_ready=runtime_ok.get("ready"),
            )
            self._send_json(
                status_code,
                {
                    "status": "ok" if status_code == 200 else "not_ready",
                    "ready": ready,
                    "service": domain_name,
                    "request_id": request_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "checks": {
                        "provider": provider_ok,
                        "elasticsearch": elastic_ok,
                        "runtime": runtime_ok,
                    },
                },
            )

        def do_POST(self):
            route = urlparse(self.path).path
            request_id = self._request_id()
            if route not in ("/v1/ask", "/v1/report"):
                self._send_json(404, {"error": "not_found"})
                return
            auth_cfg = service_cfg.get("auth", {})
            if not _is_authorized(self.headers, auth_cfg):
                log_event(logger, "warning", "request_denied", route=route, request_id=request_id)
                self._send_unauthorized(request_id)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > max_body_bytes:
                    log_event(
                        logger,
                        "warning",
                        "request_rejected_payload_too_large",
                        route=route,
                        request_id=request_id,
                        content_length=length,
                        max_body_bytes=max_body_bytes,
                    )
                    self._send_json(
                        413,
                        {
                            "error": "payload_too_large",
                            "request_id": request_id,
                            "max_body_bytes": max_body_bytes,
                        },
                    )
                    return
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                self._send_json(400, {"error": "invalid_json"})
                return

            question = str(payload.get("question") or "").strip()
            prompt = str(payload.get("prompt") or "").strip()
            log_event(
                logger,
                "info",
                "request_received",
                route=route,
                request_id=request_id,
                question_length=len(question),
                prompt_length=len(prompt),
            )

            if route == "/v1/ask" and not question:
                self._send_json(400, {"error": "question_required"})
                return
            if route == "/v1/report" and not prompt:
                self._send_json(400, {"error": "prompt_required"})
                return
            if not runtime_worker.status().get("ready") and not runtime_worker.start(raise_on_failure=False):
                runtime_status = runtime_worker.status()
                log_event(
                    logger,
                    "error",
                    "runtime_unavailable",
                    route=route,
                    request_id=request_id,
                    detail=runtime_status.get("message"),
                )
                self._send_json(
                    503,
                    {
                        "error": "runtime_unavailable",
                        "message": runtime_status.get("message"),
                        "request_id": request_id,
                    },
                )
                return

            started = time.perf_counter()
            try:
                if route == "/v1/ask":
                    result_payload = {"question": question, "answer": runtime_worker.ask(question, timeout=request_timeout_seconds)}
                else:
                    config = runtime_worker.runtime.config
                    time_range = str(payload.get("time_range") or config.get("ui", {}).get("reports", {}).get("default_time_range", "7d"))
                    include_sections = parse_include_sections(payload.get("include"), config)
                    title = str(payload.get("title") or prompt)
                    output_path = _resolve_report_output(Path(__file__).resolve().parents[1], prompt, payload.get("output"))
                    sections = runtime_worker.run(
                        generate_sections(
                            runtime_worker.runtime,
                            prompt=prompt,
                            time_range=time_range,
                            include_sections=include_sections,
                        ),
                        timeout=request_timeout_seconds,
                    )
                    html = render_report(runtime_worker.runtime.config, title, sections)
                    output_path.write_text(html, encoding="utf-8")
                    result_payload = {
                        "prompt": prompt,
                        "title": title,
                        "time_range": time_range,
                        "include_sections": include_sections,
                        "output_path": str(output_path),
                        "section_count": len(sections),
                    }
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
                    **result_payload,
                    "service": domain_name,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    AgentHandler.runtime_worker = runtime_worker
    AgentHandler.service_logger = logger
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
    logger = getattr(handler, "service_logger", get_logger("agent.http.bootstrap"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    log_event(logger, "info", "http_service_listening", host=args.host, port=args.port, config=args.config)
    print(f"ELK MCP Agent HTTP listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime_worker = getattr(handler, "runtime_worker", None)
        if runtime_worker:
            runtime_worker.stop()
            log_event(logger, "info", "runtime_stopped")
        server.server_close()


if __name__ == "__main__":
    main()

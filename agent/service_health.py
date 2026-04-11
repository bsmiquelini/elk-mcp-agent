"""
Healthchecks leves para provider de inferência e Elasticsearch.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from elastic_client import get_client


def get_provider_status(config: dict) -> dict[str, Any]:
    agent_cfg = config.get("agent", {})
    provider = str(agent_cfg.get("provider", "ollama")).lower()

    if provider == "groq":
        api_key = agent_cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
        return {
            "provider": provider,
            "ready": bool(api_key),
            "model": agent_cfg.get("model", ""),
            "endpoint": "groq",
            "message": "GROQ_API_KEY configurada." if api_key else "GROQ_API_KEY ausente.",
        }

    if provider == "openai_compatible":
        gateway_cfg = agent_cfg.get("openai_compatible", {})
        api_base = gateway_cfg.get("api_base") or agent_cfg.get("api_base") or ""
        model = gateway_cfg.get("model") or agent_cfg.get("model", "")
        if not api_base:
            return {
                "provider": provider,
                "ready": False,
                "model": model,
                "endpoint": "",
                "message": "api_base do gateway OpenAI-compatible nao configurada.",
            }
        try:
            with urllib.request.urlopen(f"{api_base.rstrip('/')}/models", timeout=5) as resp:
                if resp.status >= 400:
                    raise RuntimeError("healthcheck inválido")
            return {
                "provider": provider,
                "ready": True,
                "model": model,
                "endpoint": api_base,
                "message": "Gateway OpenAI-compatible acessivel.",
            }
        except Exception as exc:
            return {
                "provider": provider,
                "ready": False,
                "model": model,
                "endpoint": api_base,
                "message": f"Gateway OpenAI-compatible indisponivel: {exc}",
            }

    api_base = agent_cfg.get("api_base", "http://localhost:11434")
    model = agent_cfg.get("ollama_model", agent_cfg.get("model", "qwen2.5:7b"))
    try:
        with urllib.request.urlopen(f"{api_base.rstrip('/')}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        models = [str(item.get("name", "")) for item in data.get("models", [])]
        base_names = [name.split(":")[0] for name in models if ":" in name]
        available = set(models + base_names)
        ready = model in available
        return {
            "provider": "ollama",
            "ready": ready,
            "model": model,
            "endpoint": api_base,
            "available_models": models,
            "message": (
                f"Modelo {model} acessivel no Ollama."
                if ready
                else f"Modelo {model} nao encontrado no Ollama."
            ),
        }
    except Exception as exc:
        return {
            "provider": "ollama",
            "ready": False,
            "model": model,
            "endpoint": api_base,
            "available_models": [],
            "message": f"Ollama indisponivel: {exc}",
        }


def get_elasticsearch_status(config: dict) -> dict[str, Any]:
    es_cfg = config.get("elasticsearch", {})
    url = es_cfg.get("url", "")
    configured_auth_mode = str(es_cfg.get("auth_mode") or "auto").lower()
    has_basic_auth = bool(es_cfg.get("username") and es_cfg.get("password"))
    has_api_key = bool(es_cfg.get("api_key"))
    if configured_auth_mode == "auto":
        auth_mode = "basic_auth" if has_basic_auth else "api_key" if has_api_key else "none"
    elif configured_auth_mode in {"basic", "basic_auth"}:
        auth_mode = "basic_auth"
    else:
        auth_mode = configured_auth_mode
    try:
        client = get_client(config)
        info = client.info()
        return {
            "ready": True,
            "url": url,
            "auth_mode": auth_mode,
            "cluster_name": info.get("cluster_name", ""),
            "version": ((info.get("version") or {}).get("number") or ""),
            "message": "Elasticsearch acessivel.",
        }
    except Exception as exc:
        return {
            "ready": False,
            "url": url,
            "auth_mode": auth_mode,
            "cluster_name": "",
            "version": "",
            "message": f"Elasticsearch indisponivel: {exc}",
        }

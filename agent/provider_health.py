"""
Healthcheck dos providers de inferencia.
"""

from __future__ import annotations

import json
import os
import urllib.request

from renderer import console, print_error, print_warning


def check_provider(config: dict, *, fatal: bool = True) -> bool:
    agent_cfg = config.get("agent", {})
    interface_cfg = agent_cfg.get("interface", {})
    provider = agent_cfg.get("provider", "ollama").lower()
    printer = print_error if fatal else print_warning

    if provider == "groq":
        api_key = agent_cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            printer(
                "❌ GROQ_API_KEY não encontrada!\n\n"
                "Para corrigir, escolha uma das opções:\n"
                "  1) Exporte a variável antes de rodar:\n"
                "       export GROQ_API_KEY=gsk_sua_chave_aqui\n\n"
                "  2) Adicione no arquivo .env e carregue:\n"
                "       echo 'GROQ_API_KEY=gsk_sua_chave_aqui' >> .env\n"
                "       source .env\n\n"
                "  3) Defina diretamente no config.yaml:\n"
                "       agent:\n"
                "         api_key: gsk_sua_chave_aqui\n\n"
                "Obtenha sua chave gratuita em: https://console.groq.com/keys"
            )
            return False
        if interface_cfg.get("show_provider_status", False):
            console.print(
                f"[dim green]✅ Provider: Groq · modelo: {agent_cfg.get('model')}[/dim green]"
            )
        return True

    if provider == "openai_compatible":
        gateway_cfg = agent_cfg.get("openai_compatible", {})
        api_base = gateway_cfg.get("api_base") or agent_cfg.get("api_base")
        model = gateway_cfg.get("model") or agent_cfg.get("model", "-")
        if not api_base:
            printer("❌ Gateway OpenAI-compatible sem api_base configurada.")
            return False
        try:
            with urllib.request.urlopen(f"{api_base.rstrip('/')}/models", timeout=5) as resp:
                if resp.status >= 400:
                    raise RuntimeError("healthcheck inválido")
        except Exception:
            printer(
                f"⚠️ Gateway OpenAI-compatible não respondeu em {api_base}.\n"
                "O agente continuará; se a pergunta precisar de LLM e o gateway estiver indisponível, a chamada vai falhar."
            )
            return False
        if interface_cfg.get("show_provider_status", False):
            console.print(
                f"[dim green]✅ Provider: OpenAI-compatible · modelo: {model}[/dim green]"
            )
        return True

    api_base = agent_cfg.get("api_base", "http://localhost:11434")
    model = agent_cfg.get("ollama_model", agent_cfg.get("model", "qwen2.5:7b"))
    try:
        with urllib.request.urlopen(f"{api_base}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"].split(":")[0] for m in data.get("models", [])] + [
                m["name"] for m in data.get("models", [])
            ]
    except Exception:
        printer(
            f"❌ Ollama não está acessível em {api_base}.\n"
            f"Suba o serviço com: ollama serve"
        )
        return False

    if model not in models:
        printer(
            f"❌ Modelo '{model}' não encontrado no Ollama.\n"
            f"Baixe com: ollama pull {model}"
        )
        return False
    if interface_cfg.get("show_provider_status", False):
        console.print(f"[dim green]✅ Provider: Ollama · modelo: {model}[/dim green]")
    return True

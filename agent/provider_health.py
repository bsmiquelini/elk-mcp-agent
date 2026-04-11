"""
Healthcheck dos providers de inferencia.
"""

from __future__ import annotations

from renderer import console, print_error, print_warning
from service_health import get_provider_status


def check_provider(config: dict, *, fatal: bool = True, emit_output: bool = True) -> bool:
    interface_cfg = config.get("agent", {}).get("interface", {})
    printer = print_error if fatal else print_warning
    status = get_provider_status(config)

    if not status.get("ready"):
        if emit_output:
            printer(str(status.get("message") or "Provider indisponivel."))
        return False

    if emit_output and interface_cfg.get("show_provider_status", False):
        provider = status.get("provider", "provider")
        model = status.get("model", "-")
        label = "OpenAI-compatible" if provider == "openai_compatible" else provider.title()
        console.print(f"[dim green]✅ Provider: {label} · modelo: {model}[/dim green]")
    return True

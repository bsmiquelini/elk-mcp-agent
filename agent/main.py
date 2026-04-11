"""
Agente CLI — ELK MCP Agent.
Loop principal com suporte a providers locais e gateway corporativo.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from config_loader import load_config
from provider_health import check_provider
from renderer import (
    console,
    configure_interface,
    get_user_input,
    print_error,
    print_info,
    print_response,
    print_thinking,
    print_welcome,
)
from runtime import open_agent_runtime


def _bye():
    console.print(
        "\n\n[dim yellow]👋 Aplicação encerrada pelo usuário. Até mais![/dim yellow]\n"
    )
    sys.exit(0)


def _setup_signal_handlers():
    def _handler(sig, frame):
        _bye()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _unwrap_exception(exc: BaseException) -> BaseException:
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return _unwrap_exception(sub)
    return exc


async def main():
    _setup_signal_handlers()

    parser = argparse.ArgumentParser(description="ELK MCP Agent — CI/CD Pipeline Intelligence")
    parser.add_argument(
        "--question",
        "-q",
        type=str,
        default=None,
        help="Pergunta única em modo não interativo.",
    )
    args = parser.parse_args()

    config_path = Path(__file__).parent.parent / "config.yaml"
    config = load_config(str(config_path))
    interface_cfg = config.get("agent", {}).get("interface", {})
    configure_interface(interface_cfg, config)

    if interface_cfg.get("show_startup_checks", False):
        console.print("\n[dim cyan]🔍 Verificando pré-requisitos...[/dim cyan]")
    check_provider(
        config,
        fatal=False,
        emit_output=bool(
            interface_cfg.get("show_provider_status", False)
            or interface_cfg.get("show_startup_checks", False)
        ),
    )

    try:
        async with open_agent_runtime(str(config_path)) as runtime:
            schema = runtime.schema
            print_welcome(config)
            if interface_cfg.get("show_schema_status", False):
                print_info(
                    f"✅ {schema.get('total_fields')} campos · {len(runtime.tools_spec)} tools"
                )
                console.print()

            session = runtime.new_session()

            if args.question:
                console.print(
                    f"[bold cyan]❓ Pergunta:[/bold cyan] [white]{args.question}[/white]\n"
                )
                with print_thinking():
                    try:
                        answer = await runtime.ask(args.question, session=session, emit_console=True)
                    except KeyboardInterrupt:
                        _bye()
                    except RuntimeError as exc:
                        print_error(str(exc))
                        sys.exit(1)
                    except Exception as exc:
                        real = _unwrap_exception(exc)
                        print_error(f"Erro: {real}")
                        sys.exit(1)
                print_response(answer)
                return

            turn = 0
            while True:
                try:
                    user_input = get_user_input(turn + 1)
                except KeyboardInterrupt:
                    _bye()

                if not user_input:
                    continue
                if user_input.lower() in ("sair", "exit", "quit"):
                    console.print("\n[dim]👋 Até mais![/dim]\n")
                    break
                if user_input.lower() in ("limpar", "clear", "reset"):
                    session.clear()
                    session.set_system_prompt(runtime.system_prompt)
                    print_info("Contexto limpo.")
                    continue

                turn += 1
                console.print(
                    f"\n[dim cyan]❓ Processando:[/dim cyan] [white]{user_input}[/white]"
                )

                try:
                    with print_thinking():
                        answer = await runtime.ask(user_input, session=session, emit_console=True)
                except KeyboardInterrupt:
                    _bye()
                except RuntimeError as exc:
                    print_error(str(exc))
                    continue
                except Exception as exc:
                    real = _unwrap_exception(exc)
                    print_error(f"Erro inesperado: {real}")
                    continue

                print_response(answer)

    except KeyboardInterrupt:
        _bye()
    except BaseExceptionGroup as exc_group:
        real = _unwrap_exception(exc_group)
        print_error(f"Erro interno: {real}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print(
            "\n\n[dim yellow]👋 Aplicação encerrada pelo usuário. Até mais![/dim yellow]\n"
        )
        sys.exit(0)
    except BaseExceptionGroup as exc_group:
        real = _unwrap_exception(exc_group)
        console.print(f"\n[bold red]❌ Erro fatal: {real}[/bold red]\n")
        sys.exit(1)

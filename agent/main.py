"""
Agente CLI — ELK MCP Agent
Loop principal com suporte a Groq e Ollama via llm_client.
"""

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from mcp              import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config_loader import load_config
from prompts       import build_system_prompt
from session       import Session
from llm_client    import chat as llm_chat
from direct_answers import try_direct_answer
from dashboard import save_dashboard_html
from renderer      import (
    console,
    configure_interface,
    print_welcome,
    print_thinking,
    print_tool_call,
    print_response,
    print_error,
    print_info,
    get_user_input,
)


# ── Normalização de vocabulário ──────────────────────────────────────────────
# Apenas o config.yaml é fonte de verdade para vocabulário.
# _SYNONYMS foi removido para evitar duplicatas com o vocabulary do config.

def normalize_question(question: str, config: dict) -> tuple[str, list[str]]:
    """
    Varre o vocabulary do config.yaml procurando termos na pergunta.
    Retorna a pergunta original e uma lista de hints legíveis.
    """
    vocab = config.get("domain", {}).get("vocabulary", {})
    hints = []
    seen  = set()

    for term, meaning in vocab.items():
        if re.search(rf"\b{re.escape(term)}\b", question, re.IGNORECASE):
            hint = f"'{term}' significa: {meaning}"
            if hint not in seen:
                seen.add(hint)
                hints.append(hint)

    return question, hints


def enrich_user_message(question: str, hints: list[str]) -> str:
    if not hints:
        return question
    context = "\n".join(f"  - {h}" for h in hints)
    return (
        f"{question}\n\n"
        f"[contexto de vocabulário para esta pergunta:\n{context}\n]"
    )


# ── Signal handlers ──────────────────────────────────────────────────────────

def _bye():
    console.print(
        "\n\n[dim yellow]👋 Aplicação encerrada pelo usuário. Até mais![/dim yellow]\n"
    )
    sys.exit(0)


def _setup_signal_handlers():
    def _handler(sig, frame):
        _bye()
    signal.signal(signal.SIGINT,  _handler)
    signal.signal(signal.SIGTERM, _handler)


# ── Health check ─────────────────────────────────────────────────────────────

def check_provider(config: dict) -> bool:
    agent_cfg = config.get("agent", {})
    interface_cfg = agent_cfg.get("interface", {})
    provider  = agent_cfg.get("provider", "ollama").lower()

    if provider == "groq":
        api_key = agent_cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            print_error(
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

    # ollama
    api_base = agent_cfg.get("api_base", "http://localhost:11434")
    model    = agent_cfg.get("ollama_model", agent_cfg.get("model", "qwen2.5:7b"))
    try:
        with urllib.request.urlopen(f"{api_base}/api/tags", timeout=5) as resp:
            data   = json.loads(resp.read())
            models = (
                [m["name"].split(":")[0] for m in data.get("models", [])] +
                [m["name"] for m in data.get("models", [])]
            )
    except Exception:
        print_error(
            f"❌ Ollama não está acessível em {api_base}.\n"
            f"Suba o serviço com: ollama serve"
        )
        return False
    if model not in models:
        print_error(
            f"❌ Modelo '{model}' não encontrado no Ollama.\n"
            f"Baixe com: ollama pull {model}"
        )
        return False
    if interface_cfg.get("show_provider_status", False):
        console.print(
            f"[dim green]✅ Provider: Ollama · modelo: {model}[/dim green]"
        )
    return True


# ── MCP helpers ──────────────────────────────────────────────────────────────

def build_tools_spec(mcp_tools) -> list:
    """
    Constrói a lista de tools no formato OpenAI/Groq:
      {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    """
    return [
        {
            "type": "function",
            "function": {
                "name":        t.name,
                "description": t.description,
                "parameters":  t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


async def call_mcp_tool(mcp_session, name: str, args: dict) -> str:
    try:
        result = await mcp_session.call_tool(name, args)
        # O resultado do MCP é uma lista de Content, pegamos o primeiro texto
        return result.content[0].text if result.content else json.dumps({"error": "vazio"})
    except Exception as e:
        return json.dumps({"error": str(e)})
# ── Turn principal ───────────────────────────────────────────────────────────

async def run_turn(config, session, mcp_session, tools, user_input, schema) -> str:
    question, hints = normalize_question(user_input, config)
    enriched        = enrich_user_message(question, hints)
    interface_cfg   = config.get("agent", {}).get("interface", {})

    if hints and interface_cfg.get("show_vocabulary_hints", False):
        print_info(f"📖 Vocabulário detectado: {', '.join(hints)}")

    direct_result = await try_direct_answer(question, schema, mcp_session, call_mcp_tool, config=config)
    if direct_result:
        direct_answer = direct_result["answer"]
        dashboard = direct_result.get("dashboard")
        if dashboard:
            dashboard_path = save_dashboard_html(config, question, direct_answer, dashboard)
            if dashboard_path:
                print_info(f"Dashboard HTML salvo em {dashboard_path}")
        session.add_user(enriched)
        session.add_assistant(direct_answer)
        return direct_answer

    session.add_user(enriched)

    for _ in range(8): # Limite de 8 iterações para evitar loops infinitos
        try:
            response = await asyncio.to_thread(
                llm_chat,
                config   = config,
                messages = session.get_messages(),
                tools    = tools,
            )
        except RuntimeError as e:
            message = str(e)
            if "Timeout após" in message or "Timeout apos" in message:
                fallback = (
                    "Nao consegui trazer uma resposta util com a velocidade necessaria para essa pergunta. "
                    "Por favor, reformule informando melhor a metrica desejada, o periodo e se voce quer volume, taxa ou duracao."
                )
                session.add_assistant(fallback)
                return fallback
            raise

        tool_calls = response.get("tool_calls", [])
        content    = response.get("content", "")

        if not tool_calls:
            session.add_assistant(content)
            return content

        # Adiciona a resposta do assistente (chamada de tool) ao histórico
        session.messages.append({
            "role":    "assistant",
            "content": f"[usando tool: {tool_calls[0]['name']}]", # Mostra qual tool está sendo usada
        })

        for tc in tool_calls:
            name   = tc["name"]
            args   = tc["arguments"]
            # O Groq não retorna 'id' para tool_calls em alguns casos,
            # mas o Ollama sim. Garantimos um ID para o histórico.
            call_id = tc.get("id", f"call_{name}_{hash(json.dumps(args))}") 

            if interface_cfg.get("show_tool_calls", True):
                print_tool_call(name, args)
            result = await call_mcp_tool(mcp_session, name, args)
            session.messages.append({
                "role":         "tool",
                "tool_call_id": call_id, # Usado para associar a resposta da tool à chamada
                "name":         name,
                "content":      result,
            })

    return "Não consegui completar a análise. Tente reformular a pergunta."


async def startup(mcp_session) -> dict:
    result = await mcp_session.call_tool("discover_schema", {})
    return json.loads(result.content[0].text)


def _unwrap_exception(exc: BaseException) -> BaseException:
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            return _unwrap_exception(sub)
    return exc


# ── Entrada principal ────────────────────────────────────────────────────────

async def main():
    _setup_signal_handlers()

    parser = argparse.ArgumentParser(
        description="ELK MCP Agent — CI/CD Pipeline Intelligence"
    )
    parser.add_argument(
        "--question", "-q",
        type    = str,
        default = None,
        help    = "Pergunta única em modo não interativo.",
    )
    args = parser.parse_args()

    config_path = Path(__file__).parent.parent / "config.yaml"
    config      = load_config(str(config_path))
    interface_cfg = config.get("agent", {}).get("interface", {})
    configure_interface(interface_cfg)

    if interface_cfg.get("show_startup_checks", False):
        console.print("\n[dim cyan]🔍 Verificando pré-requisitos...[/dim cyan]")
    if not check_provider(config):
        sys.exit(1)

    mcp_path = Path(__file__).parent.parent / "mcp_server" / "main.py"

    server_params = StdioServerParameters(
        command = "python3",
        args    = [str(mcp_path)],
        env     = {
            **os.environ,
            "PYTHONPATH":       str(mcp_path.parent),
            "PYTHONUNBUFFERED": "1",
        },
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as mcp_session:
                await mcp_session.initialize()

                mcp_tools  = await mcp_session.list_tools()
                tools_spec = build_tools_spec(mcp_tools.tools)
                schema     = await startup(mcp_session)

                if "error" in schema:
                    print_error(f"Erro ao carregar schema: {schema['error']}")
                    sys.exit(1)

                system_prompt = build_system_prompt(config, schema)
                agent_cfg     = config.get("agent", {})
                session_cfg   = agent_cfg.get("session", {})
                session       = Session(
                    max_history=session_cfg.get("max_history_messages", 20)
                )
                session.set_system_prompt(system_prompt)

                print_welcome(config)
                if interface_cfg.get("show_schema_status", False):
                    print_info(
                        f"✅ {schema.get('total_fields')} campos · "
                        f"{len(tools_spec)} tools"
                    )
                    console.print()

                # ── modo não interativo ──────────────────────────────
                if args.question:
                    console.print(
                        f"[bold cyan]❓ Pergunta:[/bold cyan] [white]{args.question}[/white]\n"
                    )
                    with print_thinking():
                        try:
                            answer = await run_turn(
                                config      = config,
                                session     = session,
                                mcp_session = mcp_session,
                                tools       = tools_spec,
                                user_input  = args.question,
                                schema      = schema,
                            )
                        except KeyboardInterrupt:
                            _bye()
                        except RuntimeError as e:
                            print_error(str(e))
                            sys.exit(1)
                        except Exception as e:
                            real = _unwrap_exception(e)
                            print_error(f"Erro: {real}")
                            sys.exit(1)
                    print_response(answer)
                    return

                # ── modo interativo ──────────────────────────────────
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
                        session.set_system_prompt(system_prompt)
                        print_info("Contexto limpo.")
                        continue

                    turn += 1
                    console.print(
                        f"\n[dim cyan]❓ Processando:[/dim cyan] [white]{user_input}[/white]"
                    )

                    try:
                        with print_thinking():
                            answer = await run_turn(
                                config      = config,
                                session     = session,
                                mcp_session = mcp_session,
                                tools       = tools_spec,
                                user_input  = user_input,
                                schema      = schema,
                            )
                    except KeyboardInterrupt:
                        _bye()
                    except RuntimeError as e:
                        print_error(str(e))
                        continue
                    except Exception as e:
                        real = _unwrap_exception(e)
                        print_error(f"Erro inesperado: {real}")
                        continue

                    print_response(answer)

    except KeyboardInterrupt:
        _bye()
    except BaseExceptionGroup as eg:
        real = _unwrap_exception(eg)
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
    except BaseExceptionGroup as eg:
        real = _unwrap_exception(eg)
        console.print(f"\n[bold red]❌ Erro fatal: {real}[/bold red]\n")
        sys.exit(1)

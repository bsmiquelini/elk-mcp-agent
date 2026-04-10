"""
Nucleo compartilhado do agente: normalizacao, chamada de tools e um turno de resposta.
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata

from dashboard import save_dashboard_html
from direct_answers import try_direct_answer
from llm_client import chat as llm_chat
from renderer import print_info, print_tool_call


def normalize_question(question: str, config: dict) -> tuple[str, list[str]]:
    """
    Varre o vocabulary do config.yaml procurando termos na pergunta.
    Retorna a pergunta original e uma lista de hints legiveis.
    """
    vocab = config.get("domain", {}).get("vocabulary", {})
    hints = []
    seen = set()

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


def build_tools_spec(mcp_tools) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


async def call_mcp_tool(mcp_session, name: str, args: dict) -> str:
    try:
        result = await mcp_session.call_tool(name, args)
        return result.content[0].text if result.content else json.dumps({"error": "vazio"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


async def startup(mcp_session) -> dict:
    result = await mcp_session.call_tool("discover_schema", {})
    return json.loads(result.content[0].text)


async def run_turn(config, session, mcp_session, tools, user_input, schema) -> str:
    question, hints = normalize_question(user_input, config)
    enriched = enrich_user_message(question, hints)
    interface_cfg = config.get("agent", {}).get("interface", {})

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

    for _ in range(8):
        try:
            response = await asyncio.to_thread(
                llm_chat,
                config=config,
                messages=session.get_messages(),
                tools=tools,
            )
        except RuntimeError as exc:
            message = str(exc)
            if "Timeout após" in message or "Timeout apos" in message:
                fallback = (
                    "Nao consegui trazer uma resposta util com a velocidade necessaria para essa pergunta. "
                    "Por favor, reformule informando melhor a metrica desejada, o periodo e se voce quer volume, taxa ou duracao."
                )
                session.add_assistant(fallback)
                return fallback
            raise

        tool_calls = response.get("tool_calls", [])
        content = response.get("content", "")

        if not tool_calls:
            session.add_assistant(content)
            return content

        session.messages.append(
            {
                "role": "assistant",
                "content": f"[usando tool: {tool_calls[0]['name']}]",
            }
        )

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]
            call_id = tc.get("id", f"call_{name}_{hash(json.dumps(args, sort_keys=True))}")
            if interface_cfg.get("show_tool_calls", True):
                print_tool_call(name, args)
            result = await call_mcp_tool(mcp_session, name, args)
            session.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": result,
                }
            )

    return "Não consegui completar a análise. Tente reformular a pergunta."

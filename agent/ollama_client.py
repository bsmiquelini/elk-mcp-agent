"""
Cliente direto para Ollama — substitui LiteLLM.
Suporta tool calling via prompt engineering (Mistral não tem tool calling nativo no Ollama).
"""

import json
import re
import requests


def chat(
    model:       str,
    messages:    list[dict],
    tools:       list[dict],
    api_base:    str  = "http://localhost:11434",
    temperature: float = 0.1,
    max_tokens:  int   = 2048,
    timeout:     int   = 120,
) -> dict:
    """
    Chama o Ollama via /api/chat e retorna um dict no formato OpenAI:
    {
        "content": "...",
        "tool_calls": [{"name": "...", "arguments": {...}}]  # ou []
    }
    """
    # Injeta a lista de tools no system prompt se ainda não estiver lá
    messages = _inject_tools_in_system(messages, tools)

    payload = {
        "model":   model,
        "messages": messages,
        "stream":  False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    try:
        resp = requests.post(
            f"{api_base}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.Timeout:
        raise RuntimeError(
            f"Timeout após {timeout}s. O modelo está processando devagar (CPU only).\n"
            "Tente uma pergunta mais simples."
        )
    except requests.ConnectionError:
        raise RuntimeError(
            f"Ollama inacessível em {api_base}.\n"
            "Verifique: docker compose ps"
        )

    data    = resp.json()
    content = data.get("message", {}).get("content", "")

    # Tenta extrair tool calls do texto (Mistral responde em JSON dentro do texto)
    tool_calls = _extract_tool_calls(content)

    if tool_calls:
        return {"content": "", "tool_calls": tool_calls}

    return {"content": content, "tool_calls": []}


def _inject_tools_in_system(messages: list[dict], tools: list[dict]) -> list[dict]:
    """Adiciona descrição das tools no system prompt se ainda não estiver."""
    if not tools:
        return messages

    tools_text = _format_tools(tools)
    updated    = []

    for msg in messages:
        if msg["role"] == "system":
            content = msg["content"]
            if "## Tools disponíveis" not in content:
                content = content + "\n\n" + tools_text
            updated.append({**msg, "content": content})
        else:
            updated.append(msg)

    return updated


def _format_tools(tools: list[dict]) -> str:
    lines = ["## Tools disponíveis", ""]
    lines.append("Quando precisar usar uma tool, responda EXATAMENTE neste formato JSON e nada mais:")
    lines.append('{"tool": "nome_da_tool", "arguments": {"param": "valor"}}')
    lines.append("")
    lines.append("Tools:")
    for t in tools:
        fn   = t.get("function", t)
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {}).get("properties", {})
        param_list = ", ".join(params.keys())
        lines.append(f"- **{name}({param_list})**: {desc}")
    lines.append("")
    lines.append("Após receber o resultado da tool, responda ao usuário normalmente em português.")
    return "\n".join(lines)


def _extract_tool_calls(content: str) -> list[dict]:
    """Tenta extrair chamadas de tool do texto do modelo."""
    content = content.strip()

    # Tenta JSON puro
    try:
        obj = json.loads(content)
        if "tool" in obj and "arguments" in obj:
            return [{"name": obj["tool"], "arguments": obj["arguments"]}]
    except Exception:
        pass

    # Tenta extrair JSON de dentro do texto
    pattern = r'\{[^{}]*"tool"\s*:\s*"[^"]+"\s*,[^{}]*"arguments"\s*:\s*\{[^{}]*\}[^{}]*\}'
    matches = re.findall(pattern, content, re.DOTALL)
    result  = []
    for m in matches:
        try:
            obj = json.loads(m)
            if "tool" in obj and "arguments" in obj:
                result.append({"name": obj["tool"], "arguments": obj["arguments"]})
        except Exception:
            pass

    return result

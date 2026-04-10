"""
Cliente LLM unificado.
Configurado via config.yaml → agent.provider = "groq" | "ollama" | "openai_compatible"
"""

import json
import os
import requests


# ── Groq ─────────────────────────────────────────────────────────────────────

def _chat_groq(model, messages, tools, api_key, temperature, max_tokens, timeout) -> dict:
    from groq import Groq

    client = Groq(api_key=api_key, timeout=timeout)

    kwargs = dict(
        model       = model,
        messages    = messages, # As mensagens já devem estar no formato correto
        temperature = temperature,
        max_tokens  = max_tokens,
    )

    if tools:
        # As tools já devem vir no formato {"type": "function", "function": {...}}
        kwargs["tools"]       = tools
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    message  = response.choices[0].message

    tool_calls = []
    if message.tool_calls:
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append({
                "id":        tc.id, # Groq retorna um ID para a tool call
                "name":      tc.function.name,
                "arguments": args,
            })

    return {
        "content":    message.content or "",
        "tool_calls": tool_calls,
    }


# ── Ollama ────────────────────────────────────────────────────────────────────

def _chat_ollama(model, messages, tools, api_base, temperature, max_tokens, timeout) -> dict:
    # Ollama não usa o campo "type" nas tools — remove se existir
    ollama_tools = None
    if tools:
        ollama_tools = [
            {"function": t["function"]}
            for t in tools if "function" in t
        ]

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    if ollama_tools:
        payload["tools"] = ollama_tools

    try:
        resp = requests.post(
            f"{api_base}/api/chat",
            json    = payload,
            timeout = timeout,
        )
        resp.raise_for_status()
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(
            f"Timeout após {timeout}s. O modelo local está lento (CPU only).\n"
            f"Dica: troque para provider: groq no config.yaml"
        )
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Ollama não está acessível em {api_base}.\n"
            f"Suba o serviço com: ollama serve"
        )

    data    = resp.json()
    message = data.get("message", {})

    tool_calls = []
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        tool_calls.append({
            "id":        tc.get("id", "call_0"), # Ollama pode não ter ID, usa um default
            "name":      fn.get("name", ""),
            "arguments": fn.get("arguments", {}),
        })

    return {
        "content":    message.get("content", ""),
        "tool_calls": tool_calls,
    }


def _chat_openai_compatible(
    model,
    messages,
    tools,
    api_base,
    api_key,
    temperature,
    max_tokens,
    timeout,
    auth_header="Authorization",
    auth_scheme="Bearer",
    extra_headers=None,
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if api_key:
        header_value = api_key
        if auth_scheme:
            header_value = f"{auth_scheme} {api_key}"
        headers[auth_header] = header_value

    try:
        resp = requests.post(
            f"{api_base.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(
            f"Timeout após {timeout}s ao chamar o gateway LLM em {api_base}."
        )
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Gateway LLM não está acessível em {api_base}."
        )

    data = resp.json()
    choice = ((data.get("choices") or [{}])[0]).get("message", {})
    tool_calls = []
    for tc in choice.get("tool_calls", []) or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            {
                "id": tc.get("id", "call_0"),
                "name": fn.get("name", ""),
                "arguments": args,
            }
        )

    return {
        "content": choice.get("content", "") or "",
        "tool_calls": tool_calls,
    }


# ── Interface pública ─────────────────────────────────────────────────────────

def chat(config: dict, messages: list, tools: list = None) -> dict:
    agent_cfg   = config.get("agent", {})
    provider    = agent_cfg.get("provider", "ollama").lower()
    temperature = agent_cfg.get("temperature", 0.1)
    max_tokens  = agent_cfg.get("max_tokens", 2048)
    openai_cfg = agent_cfg.get("openai_compatible", {})

    if provider == "groq":
        api_key = agent_cfg.get("api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "❌ GROQ_API_KEY não encontrada.\n"
                "Execute: export GROQ_API_KEY=gsk_sua_chave\n"
                "Ou adicione no .env e rode: source .env"
            )
        model   = agent_cfg.get("model", "llama-3.3-70b-versatile")
        timeout = agent_cfg.get("timeout", 60)
        return _chat_groq(
            model       = model,
            messages    = messages,
            tools       = tools,
            api_key     = api_key,
            temperature = temperature,
            max_tokens  = max_tokens,
            timeout     = timeout,
        )

    if provider == "openai_compatible":
        api_base = openai_cfg.get("api_base") or agent_cfg.get("api_base")
        if not api_base:
            raise RuntimeError(
                "❌ API base do gateway OpenAI-compatible não configurada.\n"
                "Defina agent.openai_compatible.api_base ou LLM_API_BASE."
            )
        api_key = (
            openai_cfg.get("api_key")
            or os.environ.get("LLM_API_KEY", "")
            or agent_cfg.get("api_key", "")
        )
        model = openai_cfg.get("model") or agent_cfg.get("model", "gpt-4.1-mini")
        timeout = openai_cfg.get("timeout", agent_cfg.get("timeout", 60))
        auth_header = openai_cfg.get("auth_header", "Authorization")
        auth_scheme = openai_cfg.get("auth_scheme", "Bearer")
        extra_headers = openai_cfg.get("extra_headers", {})
        return _chat_openai_compatible(
            model=model,
            messages=messages,
            tools=tools,
            api_base=api_base,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
            extra_headers=extra_headers,
        )

    # fallback: ollama
    model    = agent_cfg.get("ollama_model", agent_cfg.get("model", "qwen2.5:7b"))
    api_base = agent_cfg.get("api_base", "http://localhost:11434")
    timeout  = agent_cfg.get("ollama_timeout", agent_cfg.get("timeout", 300))
    return _chat_ollama(
        model       = model,
        messages    = messages,
        tools       = tools,
        api_base    = api_base,
        temperature = temperature,
        max_tokens  = max_tokens,
        timeout     = timeout,
    )

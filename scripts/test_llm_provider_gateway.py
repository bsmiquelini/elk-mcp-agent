"""
Valida o provider openai_compatible sem depender de rede real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

import llm_client


class DummyResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {
                                "id": "call_test",
                                "function": {
                                    "name": "aggregate",
                                    "arguments": json.dumps({"field": "workflow_run.name"}),
                                },
                            }
                        ],
                    }
                }
            ]
        }


def main() -> None:
    captured = {}
    original_post = llm_client.requests.post

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse()

    llm_client.requests.post = fake_post
    try:
        result = llm_client.chat(
            {
                "agent": {
                    "provider": "openai_compatible",
                    "model": "ignored-root-model",
                    "temperature": 0.1,
                    "max_tokens": 512,
                    "openai_compatible": {
                        "api_base": "http://llm-gateway.intra/v1",
                        "model": "qwen2.5-72b-instruct",
                        "api_key": "token-123",
                        "timeout": 33,
                        "auth_header": "Authorization",
                        "auth_scheme": "Bearer",
                        "extra_headers": {"X-Tenant": "ci-cd-intelligence"},
                    },
                }
            },
            messages=[{"role": "user", "content": "teste"}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "aggregate",
                        "description": "agg",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        )
    finally:
        llm_client.requests.post = original_post

    assert captured["url"] == "http://llm-gateway.intra/v1/chat/completions"
    assert captured["json"]["model"] == "qwen2.5-72b-instruct"
    assert captured["json"]["tool_choice"] == "auto"
    assert captured["headers"]["Authorization"] == "Bearer token-123"
    assert captured["headers"]["X-Tenant"] == "ci-cd-intelligence"
    assert captured["timeout"] == 33
    assert result["content"] == "ok"
    assert result["tool_calls"][0]["name"] == "aggregate"
    assert result["tool_calls"][0]["arguments"]["field"] == "workflow_run.name"
    print("OK: provider openai_compatible validado.", flush=True)


if __name__ == "__main__":
    main()

"""
Suíte combinada com 300 validações:
- 280 perguntas de negócio via CLI
- 20 solicitações de visão executiva com geração de relatório HTML
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from test_cli_300_refinement import QUESTIONS as CLI_QUESTIONS, run_question as run_cli_question
from test_executive_report_prompts import EXECUTIVE_CASES, main as run_executive_suite


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main():
    assert_true(len(EXECUTIVE_CASES) == 20, f"Esperava 20 casos executivos, encontrei {len(EXECUTIVE_CASES)}.")
    selected_cli_questions = CLI_QUESTIONS[:280]
    assert_true(len(selected_cli_questions) == 280, f"Esperava 280 perguntas CLI, encontrei {len(selected_cli_questions)}.")

    slowest = ("", 0.0)
    for index, question in enumerate(selected_cli_questions, start=1):
        elapsed, _ = run_cli_question(question)
        if elapsed > slowest[1]:
            slowest = (question, elapsed)
        print(f"CLI {index}/280 OK", flush=True)

    run_executive_suite()

    print("", flush=True)
    print("OK: 300 validações passaram (280 CLI + 20 executivas).", flush=True)
    print(f"Mais lenta na CLI: {slowest[1]:.2f}s :: {slowest[0]}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(1)

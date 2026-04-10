"""
Executa a validação completa do MVP:
- 300 perguntas da CLI cross-validated contra o Elasticsearch
- 20 prompts de visão executiva com geração de relatório HTML
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, args: list[str]) -> None:
    print(f"==> {label}", flush=True)
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    run_step("300 perguntas cross-validated", ["python3", "scripts/test_cli_cross_validated.py"])
    run_step("20 relatórios executivos", ["python3", "scripts/test_executive_report_prompts.py"])
    print("OK: suíte completa validada (300 CLI + 20 executivos).", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

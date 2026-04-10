"""
Validação de 20 solicitações de visão executiva com geração de HTML.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "reports" / "executive-tests"

EXECUTIVE_CASES = [
    {
        "prompt": "Quero uma visão executiva semanal de risco operacional em PRD.",
        "time_range": "7d",
        "include": "overview,risk,prd,approvals",
    },
    {
        "prompt": "Monte um dashboard executivo mensal de sucesso e falhas em PRD.",
        "time_range": "30d",
        "include": "overview,success,risk,prd",
    },
    {
        "prompt": "Quero um resumo executivo trimestral com foco em lead time e aprovações.",
        "time_range": "90d",
        "include": "overview,lead_time,approvals",
    },
    {
        "prompt": "Crie uma visão executiva das esteiras de api para a diretoria.",
        "time_range": "30d",
        "include": "overview,api,success,risk,lead_time",
    },
    {
        "prompt": "Crie um relatório executivo das esteiras de srv.",
        "time_range": "90d",
        "include": "overview,srv,risk,success",
    },
    {
        "prompt": "Quero um resumo executivo das esteiras de bff.",
        "time_range": "90d",
        "include": "overview,bff,risk,success",
    },
    {
        "prompt": "Preciso de um relatório executivo focado em times e vskeys.",
        "time_range": "90d",
        "include": "overview,teams,risk,success",
    },
    {
        "prompt": "Quero uma visão executiva de workflows Java para gestão.",
        "time_range": "30d",
        "include": "overview,java,risk,success",
    },
    {
        "prompt": "Gere uma visão executiva para operações com foco em aprovação pendente.",
        "time_range": "30d",
        "include": "overview,approvals,risk",
    },
    {
        "prompt": "Gere uma visão executiva para diretoria com foco em lead time.",
        "time_range": "30d",
        "include": "overview,lead_time,success",
    },
    {
        "prompt": "Faça um relatório executivo de performance em HML e PRD.",
        "time_range": "30d",
        "include": "overview,lead_time,prd,hml",
    },
    {
        "prompt": "Faça um dashboard gerencial de falhas por ambiente.",
        "time_range": "90d",
        "include": "overview,risk,prd,hml",
    },
    {
        "prompt": "Crie uma visão gerencial com foco em sucesso geral das esteiras.",
        "time_range": "90d",
        "include": "overview,success",
    },
    {
        "prompt": "Crie um relatório para diretoria com foco em risco, sucesso e analistas.",
        "time_range": "90d",
        "include": "overview,risk,success,analysts",
    },
    {
        "prompt": "Quero uma visão executiva curta do ultimo dia em PRD.",
        "time_range": "1d",
        "include": "overview,prd,approvals",
    },
    {
        "prompt": "Quero um painel trimestral das esteiras de api em PRD.",
        "time_range": "90d",
        "include": "overview,api,prd,success,risk,lead_time",
    },
    {
        "prompt": "Quero um painel mensal das esteiras de java em produção.",
        "time_range": "30d",
        "include": "overview,java,prd,success,risk",
    },
    {
        "prompt": "Gere uma visão executiva de confiabilidade operacional.",
        "time_range": "90d",
        "include": "overview,risk,success,approvals",
    },
    {
        "prompt": "Monte um relatório gerencial com os principais indicadores de CI/CD.",
        "time_range": "30d",
        "include": "overview,risk,success,lead_time,approvals,analysts",
    },
    {
        "prompt": "Monte uma visão executiva completa para a diretoria.",
        "time_range": "90d",
        "include": "overview,risk,success,lead_time,approvals,prd,api,teams",
    },
]


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def compact(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(EXECUTIVE_CASES, start=1):
        output_path = OUTPUT_DIR / f"executive_{index:02d}.html"
        proc = subprocess.run(
            [
                "python3",
                "scripts/generate_director_report.py",
                "--prompt",
                case["prompt"],
                "--time-range",
                case["time_range"],
                "--include",
                case["include"],
                "--output",
                str(output_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output = compact((proc.stdout or "") + "\n" + (proc.stderr or ""))
        assert_true(proc.returncode == 0, f"Relatório executivo falhou: {case['prompt']}\n{output}")
        assert_true(output_path.exists(), f"HTML não gerado: {output_path}")
        html = output_path.read_text(encoding="utf-8")
        assert_true("Relatório Executivo" in html or "GitHub Workflow Intelligence" in html, f"Relatório sem título executivo: {output_path}")
        assert_true("<table>" in html, f"Relatório sem tabela executiva: {output_path}")
        assert_true('rel="icon"' in html, f"Relatório sem favicon: {output_path}")
        print(f"{index}/20 OK :: {case['prompt']}", flush=True)

    print("OK: 20 solicitações executivas passaram.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(1)

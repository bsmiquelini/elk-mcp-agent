"""
Validação de perguntas de negócio pela própria CLI do agente.
Foca em evitar timeout e erro interno em intents suportadas pelo caminho data-driven.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

QUESTIONS = [
    "Qual foi o ultimo workflow que rodou?",
    "Quantos deploys ocorreram no ultimo dia?",
    "Qual a taza de sucesso e falha nos deploys de workflows java?",
    "Quais os problemas mais recorrebtes que acontecem nas falhas de jobs de build?",
    "Quais os jobs de workflows que executaram até hoje?",
    "Quais os workflows que executaram até hoje?",
    "Qual foi o workflow que menos executou até hoje?",
    "Qual foi o workflow que mais executou até hoje?",
    "Qual o JOB que a execução mais demora?",
    "Qual a media de execução para workflows Java?",
    "Quais os workflows que mais falham em PRD?",
    "Quais os workflows que tem maior taxa de sucesso em PRD?",
    "Quais os workflows que são mais rapidos, relacione os repositorios?",
    "Quantos analistas rodaram workflows nos ultimos 7 dias?",
    "Quais são os workflows que temos disponivel no ambiente até agora?",
    "Quantos repositorios temos com execuções de workflows?",
    "Qual o analista com menor taxa de sucesso em execução de workflows?",
    "Qual o analista com maior sucesso de execução de workflows?",
    "Qual é a media de execução de jobs de build por workflow?",
    "Qual é a media de execuções por jobs de deploy por workflow?",
    "Qual o workflow que teve menor volume de execuções até hoje?",
]

UNSUPPORTED_QUESTIONS = [
    "Qual a cor dos workflows em PRD?",
]


def compact(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"[╭╮╰╯│─]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def run_question(question: str):
    start = time.time()
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    elapsed = time.time() - start
    output = compact((proc.stdout or "") + "\n" + (proc.stderr or ""))
    assert_true(proc.returncode == 0, f"CLI falhou para: {question}\n{output}")
    assert_true("timeout apos" not in output.lower(), f"Timeout encontrado para: {question}\n{output}")
    assert_true("erro interno" not in output.lower(), f"Erro interno encontrado para: {question}\n{output}")
    assert_true("verificando pre-requisitos" not in output.lower(), f"Saida de startup antiga encontrada para: {question}\n{output}")
    assert_true("descobrindo schema do indice" not in output.lower(), f"Saida de schema antiga encontrada para: {question}\n{output}")
    assert_true(" aggregate(" not in output.lower(), f"Trace tecnico de tool apareceu para: {question}\n{output}")
    assert_true(" search(" not in output.lower(), f"Trace tecnico de tool apareceu para: {question}\n{output}")
    assert_true(len(output) > 40, f"Resposta curta demais para: {question}\n{output}")
    return elapsed, output


def main():
    slowest = ("", 0.0)
    for question in QUESTIONS:
        elapsed, output = run_question(question)
        if elapsed > slowest[1]:
            slowest = (question, elapsed)
        print(f"OK {elapsed:.2f}s :: {question}")

    for question in UNSUPPORTED_QUESTIONS:
        elapsed, output = run_question(question)
        assert_true("reformule" in output.lower(), f"Pergunta sem metrica util deveria pedir reformulacao: {question}\n{output}")
        print(f"OK {elapsed:.2f}s :: {question} -> reformulacao")

    print("")
    print(f"OK: {len(QUESTIONS)} perguntas de negocio passaram.")
    print(f"OK: {len(UNSUPPORTED_QUESTIONS)} perguntas sem metrica util pediram reformulacao.")
    print(f"Mais lenta: {slowest[1]:.2f}s :: {slowest[0]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

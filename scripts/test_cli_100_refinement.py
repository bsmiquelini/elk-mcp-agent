"""
Suíte de refinamento com 100 perguntas de negócio pela CLI real.
Falha se a resposta vier vazia, com pedido de reformulação ou sem contexto útil.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

QUESTIONS = [
    "Qual foi o workflow que mais executou até hoje?",
    "Qual foi o workflow que menos executou até hoje?",
    "Quais repositórios mais executaram workflows nos ultimos 90 dias?",
    "Quais repositórios menos executaram workflows nos ultimos 90 dias?",
    "Quais analistas mais executaram workflows nos ultimos 90 dias?",
    "Quais analistas menos executaram workflows nos ultimos 90 dias?",
    "Quais linguagens mais executaram workflows nos ultimos 90 dias?",
    "Quais branches mais executaram workflows nos ultimos 90 dias?",
    "Quais jobs de build mais executaram nos ultimos 90 dias?",
    "Quais jobs de deploy mais executaram nos ultimos 90 dias?",
    "Quais repositórios do topico api mais executaram workflows em PRD nos ultimos 90 dias?",
    "Quais repositórios do topico frontend mais executaram workflows em STG nos ultimos 90 dias?",
    "Quais analistas do topico risk mais executaram workflows nos ultimos 90 dias?",
    "Quais workflows Java mais executaram nos ultimos 90 dias?",
    "Quais workflows Python mais executaram nos ultimos 90 dias?",
    "Quais workflows TypeScript mais executaram nos ultimos 90 dias?",
    "Quais repositórios privados mais executaram workflows nos ultimos 90 dias?",
    "Quais repositórios publicos mais executaram workflows nos ultimos 90 dias?",
    "Quais branches mais executaram workflows Java nos ultimos 90 dias?",
    "Quais branches mais executaram workflows Python nos ultimos 90 dias?",
    "Quais jobs de build mais executaram em workflows Java nos ultimos 90 dias?",
    "Quais jobs de security mais executaram nos ultimos 90 dias?",
    "Quais workflows de deploy mais executaram em PRD nos ultimos 90 dias?",
    "Quais workflows de build mais executaram nos ultimos 90 dias?",
    "Quais workflows de security mais executaram nos ultimos 90 dias?",
    "Quais analistas mais executaram workflows em PRD nos ultimos 90 dias?",
    "Quais analistas mais executaram workflows Java nos ultimos 90 dias?",
    "Quais linguagens mais executaram workflows em PRD nos ultimos 90 dias?",
    "Quais ambientes mais executaram workflows Java nos ultimos 90 dias?",
    "Quais ambientes mais executaram workflows do topico api nos ultimos 90 dias?",
    "Quantos workflows temos ate hoje?",
    "Quantos repositorios tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos analistas rodaram workflows nos ultimos 90 dias?",
    "Quantas linguagens tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantas branches tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos jobs de build rodaram nos ultimos 90 dias?",
    "Quantos workflows Java rodaram nos ultimos 90 dias?",
    "Quantos workflows Python rodaram nos ultimos 90 dias?",
    "Quantos workflows TypeScript rodaram nos ultimos 90 dias?",
    "Quantos repositorios privados tiveram execucoes de workflows Java nos ultimos 90 dias?",
    "Quantos repositorios publicos tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos analistas rodaram workflows em PRD nos ultimos 90 dias?",
    "Quantas branches rodaram workflows em PRD nos ultimos 90 dias?",
    "Quantos repositorios do topico api tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos repositorios do topico risk tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos repositorios do topico frontend tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos jobs de deploy rodaram nos ultimos 90 dias?",
    "Quantos ambientes tiveram execucoes de workflows nos ultimos 90 dias?",
    "Quantos workflows de build rodaram nos ultimos 90 dias?",
    "Quantos workflows de security rodaram nos ultimos 90 dias?",
    "Quais workflows temos disponiveis ate hoje?",
    "Quais repositórios temos disponiveis nos ultimos 90 dias?",
    "Quais linguagens temos disponiveis nos ultimos 90 dias?",
    "Quais branches temos disponiveis nos ultimos 90 dias?",
    "Quais workflows Java temos disponiveis nos ultimos 90 dias?",
    "Quais workflows Python temos disponiveis nos ultimos 90 dias?",
    "Quais workflows TypeScript temos disponiveis nos ultimos 90 dias?",
    "Quais repositórios do topico api temos disponiveis nos ultimos 90 dias?",
    "Quais repositórios do topico risk temos disponiveis nos ultimos 90 dias?",
    "Quais repositórios do topico frontend temos disponiveis nos ultimos 90 dias?",
    "Quais workflows de deploy temos disponiveis nos ultimos 90 dias?",
    "Quais workflows de build temos disponiveis nos ultimos 90 dias?",
    "Quais workflows de security temos disponiveis nos ultimos 90 dias?",
    "Quais jobs de build temos disponiveis nos ultimos 90 dias?",
    "Quais jobs de deploy temos disponiveis nos ultimos 90 dias?",
    "Quais workflows com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows com menor taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios com menor taxa de sucesso nos ultimos 90 dias?",
    "Quais analistas com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais analistas com menor taxa de sucesso nos ultimos 90 dias?",
    "Quais linguagens com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais branches com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais ambientes com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais jobs com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows Java com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows Python com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows TypeScript com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios do topico api com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios do topico frontend com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios do topico risk com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows de deploy com maior taxa de sucesso em PRD nos ultimos 90 dias?",
    "Quais workflows de build com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows de security com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais branches com maior taxa de falha nos ultimos 90 dias?",
    "Quais ambientes com maior taxa de falha nos ultimos 90 dias?",
    "Quais repositórios com maior volume de falhas nos ultimos 90 dias?",
    "Quais analistas com maior volume de falhas nos ultimos 90 dias?",
    "Quais workflows com maior volume de falhas em PRD nos ultimos 90 dias?",
    "Quais jobs com maior volume de falhas nos ultimos 90 dias?",
    "Quais workflows Java com maior volume de falhas nos ultimos 90 dias?",
    "Quais repositórios do topico api com maior volume de falhas nos ultimos 90 dias?",
    "Quais repositórios privados com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais repositórios publicos com maior taxa de sucesso nos ultimos 90 dias?",
    "Quais workflows de deploy com maior volume de falhas em PRD nos ultimos 90 dias?",
    "Quais workflows com menor duracao media nos ultimos 90 dias?",
    "Quais repositórios com menor duracao media nos ultimos 90 dias?",
    "Quais linguagens com menor duracao media nos ultimos 90 dias?",
    "Quais branches com menor duracao media nos ultimos 90 dias?",
    "Quais jobs com menor duracao media nos ultimos 90 dias?",
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
        timeout=35,
        check=False,
    )
    elapsed = time.time() - start

    output = compact((proc.stdout or "") + "\n" + (proc.stderr or ""))
    _, _, resultado = output.partition(".html")
    resultado =  resultado

    print(f'  RESPOSTA: {resultado}\n')
    assert_true(proc.returncode == 0, f"CLI falhou para: {question}\n{output}")
    assert_true("timeout apos" not in output.lower(), f"Timeout encontrado para: {question}\n{output}")
    assert_true("erro interno" not in output.lower(), f"Erro interno encontrado para: {question}\n{output}")
    assert_true("nao consegui" not in output.lower(), f"Resposta sem utilidade para: {question}\n{output}")
    assert_true("nao encontrei" not in output.lower(), f"Resposta sem dados uteis para: {question}\n{output}")
    assert_true("reformule" not in output.lower(), f"Pergunta pediu reformulacao: {question}\n{output}")
    assert_true(len(output) > 60, f"Resposta curta demais para: {question}\n{output}")
    return elapsed, output


def main():
    slowest = ("", 0.0)
    count = 0
    for index, question in enumerate(QUESTIONS, start=1):
        count = count + 1
        elapsed, _ = run_question(question)
        if elapsed > slowest[1]:
            slowest = (question, elapsed)
        print(f"{count} :: {question}")

    print("")
    print(f"OK: {len(QUESTIONS)} perguntas de refinamento passaram.")
    print(f"Mais lenta: {slowest[1]:.2f}s :: {slowest[0]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

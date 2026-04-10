"""
Suíte ampliada com 300 perguntas de negócio pela CLI real.
Objetivo: validar linguagem natural com resposta útil, sem timeout e sem
mensagem genérica de reformulação.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from test_cli_100_refinement import QUESTIONS as BASE_QUESTIONS

ROOT = Path(__file__).resolve().parents[1]


def compact(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"[╭╮╰╯│─]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def build_questions() -> list[str]:
    questions: list[str] = list(BASE_QUESTIONS)

    exact_business_cases = [
        "Qual foi o workflow que mais foi executado com falha?",
        "Qual foi o workflow que menos executou até hoje? Me aponte o repositorio que menos teve execuções",
        "Qual foi o primeiro workflow a rodar em PRD?",
        "Qual foi o primeiro workflow a rodar no ambiente de PRD?",
        "Qual foi a data de execução do ultimo workflow?",
        "Qual o analista que mais executou workflows no utimo dia?",
        "Qual o analista que mais executou workflows até hoje?",
        "Qual é a esteira que mais falhou na ultima semana?",
        "Qual é a porcentagem de falhas e sucesso em esteiras de api?",
        "Qual é a porcentagem de falhas e sucesso em esteiras de srv?",
        "Qual é a porcentagem de falhas e sucesso em esteiras de bff?",
        "Qual é a porcentagem de sucesso e falha geral em todas as esteiras nos ultimos 7 dias?",
        "Qual é o step com maior porcentagem de falha e em qual esteira?",
        "quantos jobs estão com status wating aguardando aprovação?",
        "Qual é o tempo medio de execução de esteiras de hom e de prd?",
        "Entre o gatilho e o deploy qual é o tempo medio?",
        "Entre o gatilho e o deploy qual é o tempo medio para esteiras de api?",
    ]
    questions.extend(exact_business_cases)

    periods = ["7 dias", "30 dias", "90 dias"]
    envs = ["PRD", "HML"]
    architectures = ["api", "srv", "bff"]
    languages = ["Java", "Python", "TypeScript"]
    workflow_types = ["build", "deploy", "security"]
    topics = ["api", "risk", "frontend"]

    for arch in architectures:
        questions.append(f"Qual é a porcentagem de falhas e sucesso em esteiras de {arch} nos ultimos 7 dias?")
        questions.append(f"Qual é a porcentagem de falhas e sucesso em esteiras de {arch} nos ultimos 30 dias?")
        questions.append(f"Qual é a porcentagem de falhas e sucesso em esteiras de {arch} nos ultimos 90 dias?")

    for arch in ["api"]:
        for period in periods:
            questions.extend(
                [
                    f"Quais repositórios de {arch} mais executaram workflows nos ultimos {period}?",
                    f"Quais repositórios de {arch} com maior taxa de sucesso nos ultimos {period}?",
                    f"Quais repositórios de {arch} com maior volume de falhas nos ultimos {period}?",
                    f"Quais workflows de {arch} mais executaram nos ultimos {period}?",
                    f"Quais workflows de {arch} com maior taxa de sucesso nos ultimos {period}?",
                    f"Quais workflows de {arch} com maior volume de falhas nos ultimos {period}?",
                    f"Entre o gatilho e o deploy qual é o tempo medio para esteiras de {arch} nos ultimos {period}?",
                ]
            )

    for arch in ["api"]:
        questions.extend(
            [
                f"Qual é o tempo medio de execução de esteiras de hom e de prd para esteiras de {arch}?",
                f"Qual é o step com maior porcentagem de falha em esteiras de {arch} e em qual esteira?",
            ]
        )

    for env in envs:
        for period in periods:
            questions.extend(
                [
                    f"Quais workflows mais executaram em {env} nos ultimos {period}?",
                    f"Quais repositórios mais executaram workflows em {env} nos ultimos {period}?",
                    f"Quais analistas mais executaram workflows em {env} nos ultimos {period}?",
                    f"Quais workflows com maior taxa de sucesso em {env} nos ultimos {period}?",
                    f"Quais workflows com maior volume de falhas em {env} nos ultimos {period}?",
                    f"Quais jobs com maior volume de falhas em {env} nos ultimos {period}?",
                    f"Qual é o step com maior porcentagem de falha em {env} e em qual esteira?",
                    f"Qual foi o primeiro workflow a rodar no ambiente de {env}?",
                    f"Qual foi o ultimo workflow a rodar no ambiente de {env}?",
                ]
            )

    for language in languages:
        for period in periods:
            questions.extend(
                [
                    f"Quais workflows {language} mais executaram nos ultimos {period}?",
                    f"Quais workflows {language} com maior taxa de sucesso nos ultimos {period}?",
                    f"Quais workflows {language} com maior volume de falhas nos ultimos {period}?",
                    f"Quais repositórios {language} mais executaram workflows nos ultimos {period}?",
                    f"Quais branches mais executaram workflows {language} nos ultimos {period}?",
                    f"Qual é a media de execução para workflows {language}?",
                ]
            )

    for workflow_type in workflow_types:
        for period in periods:
            questions.extend(
                [
                    f"Quais workflows de {workflow_type} mais executaram nos ultimos {period}?",
                    f"Quais workflows de {workflow_type} com maior taxa de sucesso nos ultimos {period}?",
                    f"Quais workflows de {workflow_type} com maior volume de falhas nos ultimos {period}?",
                    f"Quais jobs de {workflow_type} mais executaram nos ultimos {period}?",
                ]
            )

    for topic in topics:
        for period in periods:
            questions.extend(
                [
                    f"Quais repositórios do topico {topic} mais executaram workflows nos ultimos {period}?",
                    f"Quais repositórios do topico {topic} com maior taxa de sucesso nos ultimos {period}?",
                    f"Quais repositórios do topico {topic} com maior volume de falhas nos ultimos {period}?",
                    f"Quantos repositorios do topico {topic} tiveram execucoes de workflows nos ultimos {period}?",
                    f"Quais workflows do topico {topic} mais executaram nos ultimos {period}?",
                ]
            )

    team_questions = [
        "Quais workflows do time core mais executaram nos ultimos 90 dias?",
        "Quais repositórios do time core mais executaram workflows nos ultimos 90 dias?",
        "Quais workflows do vskey core com maior taxa de sucesso nos ultimos 90 dias?",
        "Quais workflows do time core com maior volume de falhas nos ultimos 90 dias?",
        "Quantas execuções o time core teve nos ultimos 90 dias?",
    ]
    questions.extend(team_questions)

    director_questions = [
        "Qual workflow concentrou mais falhas operacionais nos ultimos 30 dias?",
        "Qual workflow teve melhor taxa de sucesso em produção nos ultimos 30 dias?",
        "Qual repositório concentrou mais falhas em produção nos ultimos 30 dias?",
        "Qual analista concentrou mais execuções na ultima semana?",
        "Qual analista teve a maior taxa de sucesso nos ultimos 30 dias?",
        "Qual analista teve a menor taxa de sucesso nos ultimos 30 dias?",
        "Quais jobs de deploy mais executaram em PRD nos ultimos 30 dias?",
        "Quais jobs de build mais executaram em workflows Java nos ultimos 30 dias?",
        "Qual o JOB que a execução mais demora",
        "Qual a media de execução para workflows Java",
        "Quais os workflows que mais falham em PRD",
        "Quais os workflows que tem maior taxa de sucesso em PRD?",
        "Quais os workflows que são mais rapidos, relacione os repositorios",
        "Quantos analistas rodaram workflows nos ultimos 7 dias",
        "Quais são os workflows que temos disponivel no ambiente até agora?",
        "Quantos repositorios temos com execuções de workflows",
        "Qual o analista com menor taxa de sucesso em execução de workflows",
        "Qual o analista com maior sucesso de execução de workflows?",
        "Qual é a media de execução de jobs de build por workflow?",
        "Qual é a media de execuções por jobs de deploy por workflow?",
    ]
    questions.extend(director_questions)

    unique_questions: list[str] = []
    seen = set()
    for question in questions:
        if question not in seen:
            seen.add(question)
            unique_questions.append(question)

    return unique_questions[:300]


QUESTIONS = build_questions()


def run_question(question: str):
    start = time.time()
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    elapsed = time.time() - start
    output = compact((proc.stdout or "") + "\n" + (proc.stderr or ""))
    print(f"{question}\n  -> {output}\n", flush=True)

    assert_true(proc.returncode == 0, f"CLI falhou para: {question}\n{output}")
    assert_true("timeout apos" not in output.lower(), f"Timeout encontrado para: {question}\n{output}")
    assert_true("erro interno" not in output.lower(), f"Erro interno encontrado para: {question}\n{output}")
    assert_true("nao consegui" not in output.lower(), f"Resposta generica para: {question}\n{output}")
    assert_true("nao encontrei" not in output.lower(), f"Resposta sem dados uteis para: {question}\n{output}")
    assert_true("reformule" not in output.lower(), f"Pergunta pediu reformulacao: {question}\n{output}")
    assert_true(len(output) > 60, f"Resposta curta demais para: {question}\n{output}")

    return elapsed, output


def main():
    assert_true(len(QUESTIONS) == 300, f"Esperava 300 perguntas, mas encontrei {len(QUESTIONS)}.")
    slowest = ("", 0.0)
    for index, question in enumerate(QUESTIONS, start=1):
        elapsed, _ = run_question(question)
        if elapsed > slowest[1]:
            slowest = (question, elapsed)
        print(f"{index}/300 OK", flush=True)

    print("", flush=True)
    print("OK: 300 perguntas de refinamento passaram.", flush=True)
    print(f"Mais lenta: {slowest[1]:.2f}s :: {slowest[0]}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(1)

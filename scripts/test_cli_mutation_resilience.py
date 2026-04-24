"""
Suite de mutacao para validar perguntas de borda sem depender do LLM.

Foco desta rodada:
- ultima/primeira execucao de esteira nomeada
- variacoes com acento e sinonimos (esteira/workflow/pipeline)
- filtros de ambiente
- workflow inexistente sem vazar erro do Ollama
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.test_cli_cross_validated import (
    CLI_TIMEOUT_SECONDS,
    assert_true,
    compact,
    contains_fragment,
    dig,
    document_time,
    env_matches,
    format_local_datetime,
    load_documents,
    parse_iso,
    strip_ansi,
)


def top_workflow_name(all_docs: list[dict], env: str | None = None) -> str | None:
    counter = Counter()
    for doc in all_docs:
        workflow = str(dig(doc, "workflow_run.name") or "").strip()
        if not workflow:
            continue
        if env and not env_matches(doc, env):
            continue
        counter[workflow] += 1
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def workflow_edge_doc(all_docs: list[dict], *, workflow_name: str, order: str, env: str | None = None) -> dict:
    docs = []
    for doc in all_docs:
        current = str(dig(doc, "workflow_run.name") or "").strip()
        when = document_time(doc)
        if not current or not when or current != workflow_name:
            continue
        if env and not env_matches(doc, env):
            continue
        docs.append(doc)
    assert_true(bool(docs), f"Sem documentos para workflow={workflow_name} env={env or '-'}")
    docs.sort(key=lambda doc: document_time(doc) or datetime.min.replace(tzinfo=timezone.utc), reverse=(order == "desc"))
    return docs[0]


def deployment_time(doc: dict) -> datetime | None:
    return (
        parse_iso(dig(doc, "deployment_status.updated_at"))
        or parse_iso(dig(doc, "deployment.updated_at"))
        or document_time(doc)
    )


def latest_failed_deploy_doc(all_docs: list[dict], *, env: str) -> dict | None:
    docs = []
    for doc in all_docs:
        status = str(dig(doc, "deployment_status.state") or "").lower()
        when = deployment_time(doc)
        if status not in {"failure", "failed", "error", "timed_out", "cancelled", "canceled"}:
            continue
        if not when or not env_matches(doc, env):
            continue
        docs.append(doc)
    if not docs:
        return None
    docs.sort(key=lambda doc: deployment_time(doc) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return docs[0]


def mutation_cases(all_docs: list[dict]) -> list[dict]:
    workflow_name = top_workflow_name(all_docs)
    assert_true(bool(workflow_name), "Nenhum workflow encontrado para montar a suite de mutacao.")
    cases = [
        {"question": f"Qual foi a ultima execucao da esteira {workflow_name}", "workflow_name": workflow_name, "order": "desc"},
        {"question": f"Qual foi a ultima execução da esteira {workflow_name}", "workflow_name": workflow_name, "order": "desc"},
        {"question": f"Qual foi a ultima execucao do workflow {workflow_name}", "workflow_name": workflow_name, "order": "desc"},
        {"question": f"Quando foi a ultima execucao da pipeline {workflow_name}", "workflow_name": workflow_name, "order": "desc"},
        {"question": f"Qual foi a primeira execucao da esteira {workflow_name}", "workflow_name": workflow_name, "order": "asc"},
        {"question": f"Qual foi a primeira execucao do workflow {workflow_name}", "workflow_name": workflow_name, "order": "asc"},
    ]

    for env in ["PRD", "DEV"]:
        env_workflow = top_workflow_name(all_docs, env=env)
        if env_workflow:
            cases.append(
                {
                    "question": f"Qual foi a ultima execucao da esteira {env_workflow} em {env}",
                    "workflow_name": env_workflow,
                    "order": "desc",
                    "env": env,
                }
            )

    cases.append(
        {
            "question": "Qual foi a ultima execucao da esteira techdocs",
            "workflow_name": "techdocs",
            "order": "desc",
            "expect_missing": True,
        }
    )
    cases.append(
        {
            "question": "Qual foi a ultima execução do workflow techdocs",
            "workflow_name": "techdocs",
            "order": "desc",
            "expect_missing": True,
        }
    )
    failed_prd = latest_failed_deploy_doc(all_docs, env="PRD")
    if failed_prd:
        cases.append(
            {
                "question": "qual foi o ultimo deploy com falha em PRD",
                "deploy_doc": failed_prd,
                "deploy_order": "desc",
                "env": "PRD",
                "deploy_failure": True,
            }
        )
    return cases


def run_cli(question: str) -> tuple[float, str, str]:
    started = time.time()
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=CLI_TIMEOUT_SECONDS,
        check=False,
    )
    elapsed = time.time() - started
    raw = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    packed = compact(raw)
    assert_true(proc.returncode == 0, f"CLI falhou: {question}\n{raw}")
    return elapsed, raw, packed


def validate_case(all_docs: list[dict], case: dict, raw: str, packed: str) -> None:
    lowered = packed.lower()
    assert_true("ollama" not in lowered, f"Resposta vazou erro do Ollama:\n{raw}")
    assert_true("erro interno" not in lowered, f"Resposta com erro interno:\n{raw}")
    assert_true("nao consegui montar uma resposta util" not in lowered, f"Resposta genérica indevida:\n{raw}")

    if case.get("expect_missing"):
        assert_true("nao encontrei a ultima execucao da esteira" in lowered, f"Esperava fallback coerente de ausencia:\n{raw}")
        assert_true("techdocs" in lowered, f"Workflow ausente nao mencionado:\n{raw}")
        return

    if case.get("deploy_failure"):
        doc = case["deploy_doc"]
        workflow = str(dig(doc, "workflow_run.name") or "")
        repo = str(dig(doc, "repository.full_name") or "")
        when = format_local_datetime(deployment_time(doc))
        assert_true("maior volume de falhas" not in lowered, f"Pergunta pontual caiu em ranking:\n{raw}")
        assert_true("ultimo deploy" in lowered, f"Resposta nao ficou no formato de deploy pontual:\n{raw}")
        assert_true(contains_fragment(packed, workflow), f"Workflow esperado ausente: {workflow}\n{raw}")
        assert_true(contains_fragment(packed, repo), f"Repositorio esperado ausente: {repo}\n{raw}")
        assert_true(contains_fragment(packed, when), f"Timestamp local esperado ausente: {when}\n{raw}")
        assert_true("prd" in lowered, f"Ambiente PRD ausente:\n{raw}")
        assert_true(any(token in lowered for token in ["failure", "failed", "error", "timed_out", "cancelled", "canceled"]), f"Status de falha ausente:\n{raw}")
        return

    doc = workflow_edge_doc(
        all_docs,
        workflow_name=case["workflow_name"],
        order=case["order"],
        env=case.get("env"),
    )
    workflow = str(dig(doc, "workflow_run.name") or "")
    assert_true(contains_fragment(packed, workflow), f"Workflow esperado ausente: {workflow}\n{raw}")
    if case.get("env"):
        assert_true(case["env"].lower() in lowered, f"Ambiente esperado ausente: {case['env']}\n{raw}")
        return

    repo = str(dig(doc, "repository.full_name") or "")
    when = format_local_datetime(document_time(doc))
    assert_true(contains_fragment(packed, repo), f"Repositorio esperado ausente: {repo}\n{raw}")
    assert_true(contains_fragment(packed, when), f"Timestamp local esperado ausente: {when}\n{raw}")


def main() -> None:
    docs = load_documents()
    cases = mutation_cases(docs)
    assert_true(bool(cases), "Nenhum caso mutacional foi gerado.")

    for index, case in enumerate(cases, start=1):
        elapsed, raw, packed = run_cli(case["question"])
        validate_case(docs, case, raw, packed)
        print(f"{index}/{len(cases)} OK :: {case['question']} :: {elapsed:.2f}s", flush=True)

    print(f"OK: {len(cases)} casos mutacionais passaram.", flush=True)


if __name__ == "__main__":
    main()

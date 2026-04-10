"""
Suíte cross-validated da CLI:
- executa perguntas reais na CLI
- confirma no Elasticsearch se a resposta bate com os dados
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))

from config_loader import load_config
from elastic_client import get_client, get_index


SUCCESS_VALUES = {"success", "completed"}
FAILURE_VALUES = {"failure", "failed", "error", "timed_out", "cancelled", "canceled"}
PERIODS = [("7d", "ultimos 7 dias"), ("30d", "ultimo mes"), ("90d", "ultimos 90 dias")]
ARCHITECTURES = ["api", "srv", "bff", "apim"]
TEAMS = ["arch", "devops", "ia", "sre"]
ENVS = ["PRD", "HML", "DEV"]
LANGUAGES = [("Java", "java"), ("Python", "python"), ("TypeScript", "typescript"), ("Node", "node")]
WORKFLOW_TYPES = ["build", "deploy", "security", "rollback"]
TOPICS = ["api", "risk", "frontend", "apim"]


@dataclass
class Spec:
    question: str
    kind: str
    dimension: str | None = None
    time_range: str = "30d"
    architecture: str | None = None
    team: str | None = None
    env: str | None = None
    language: str | None = None
    workflow_type: str | None = None
    topic: str | None = None
    failure_only: bool = False
    success_rate: bool = False
    list_mode: bool = False
    top_n: int = 5
    repo_name: str | None = None
    workflow_name: str | None = None
    anchor_kind: str | None = None
    target_env: str | None = None


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def compact(text: str) -> str:
    text = strip_ansi(text)
    text = re.sub(r"[╭╮╰╯│─]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_fragment(text: str, fragment: str) -> bool:
    return compact(fragment) in compact(text)


def cli_output(question: str) -> tuple[float, str, str]:
    started = time.time()
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    elapsed = time.time() - started
    raw = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    packed = compact(raw)
    assert_true(proc.returncode == 0, f"CLI falhou: {question}\n{raw}")
    lowered = packed.lower()
    assert_true("timeout apos" not in lowered, f"Timeout: {question}\n{raw}")
    assert_true("erro interno" not in lowered, f"Erro interno: {question}\n{raw}")
    assert_true("nao consegui" not in lowered, f"Resposta genérica: {question}\n{raw}")
    assert_true("reformule" not in lowered, f"Reformulação: {question}\n{raw}")
    assert_true("nao encontrei" not in lowered, f"Sem dados úteis: {question}\n{raw}")
    return elapsed, raw, packed


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def dig(data: dict, field: str | None):
    if not field:
        return None
    node = data
    for part in field.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def time_delta_for(time_range: str) -> timedelta:
    value = int(time_range[:-1])
    unit = time_range[-1]
    if unit == "d":
        return timedelta(days=value)
    raise ValueError(f"time_range não suportado: {time_range}")


def document_time(doc: dict) -> datetime | None:
    return parse_iso(dig(doc, "workflow_run.run_started_at")) or parse_iso(dig(doc, "@timestamp"))


def in_time_range(doc: dict, time_range: str) -> bool:
    dt = document_time(doc)
    if not dt:
        return False
    return dt >= (now_utc() - time_delta_for(time_range))


def team_from_repo(doc: dict) -> str | None:
    repo = str(dig(doc, "repository.full_name") or dig(doc, "repository.name") or "")
    repo_name = repo.split("/", 1)[-1]
    head = repo_name.split("-", 1)[0].strip().lower()
    return head or None


def architectures_from_doc(doc: dict) -> list[str]:
    topics = dig(doc, "repository.topics") or []
    if not isinstance(topics, list):
        topics = [topics]
    values = []
    for topic in topics:
        normalized = str(topic).lower()
        for prefix in ("archtecture-", "architecture-"):
            if normalized.startswith(prefix):
                values.append(normalized[len(prefix):])
                break
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def text_contains_type(doc: dict, workflow_type: str, *, dimension: str | None = None) -> bool:
    workflow_name = str(dig(doc, "workflow_run.name") or "").lower()
    job_name = str(dig(doc, "check_run.name") or "").lower()
    task = str(dig(doc, "deployment.task") or "").lower()
    tokens = {
        "build": ["build", "compile"],
        "deploy": ["deploy", "release"],
        "security": ["security", "scan", "sast"],
        "rollback": ["rollback"],
        "gate": ["gate", "approval"],
    }.get(workflow_type, [workflow_type])
    if dimension == "job":
        haystack = job_name
    else:
        haystack = " ".join([workflow_name, job_name, task])
    return any(token in haystack for token in tokens)


def env_matches(doc: dict, env: str) -> bool:
    env = env.upper()
    exact_map = {
        "PRD": {"PRD", "PROD", "PRODUCTION"},
        "HML": {"HML", "HOM", "HOMOLOG"},
        "DEV": {"DEV", "SANDBOX", "DEVELOP"},
    }
    token_map = {
        "PRD": ["prd", "prod", "production", "release"],
        "HML": ["hml", "hom", "homolog", "staging", "stg"],
        "DEV": ["dev", "sandbox", "develop"],
    }
    exact_raw = str(dig(doc, "deployment.environment") or dig(doc, "deployment_status.environment") or "")
    if exact_raw:
        return exact_raw.upper() in exact_map.get(env, set())
    return False


def status_for(doc: dict, dimension: str | None, prefer_deployment: bool) -> str:
    if dimension == "job":
        return str(dig(doc, "check_run.conclusion") or dig(doc, "check_run.status") or "").lower()
    if prefer_deployment:
        return str(dig(doc, "deployment_status.state") or "").lower()
    return str(dig(doc, "workflow_run.conclusion") or dig(doc, "workflow_run.status") or "").lower()


def matches(doc: dict, spec: Spec) -> bool:
    if not in_time_range(doc, spec.time_range):
        return False
    if spec.repo_name and str(dig(doc, "repository.full_name") or "") != spec.repo_name:
        return False
    if spec.workflow_name and str(dig(doc, "workflow_run.name") or "") != spec.workflow_name:
        return False
    if spec.architecture and spec.architecture not in architectures_from_doc(doc):
        return False
    if spec.team and team_from_repo(doc) != spec.team:
        return False
    if spec.env:
        if spec.kind == "latest_failure":
            if str(dig(doc, "deployment.environment") or "").upper() != spec.env.upper():
                return False
        elif not env_matches(doc, spec.env):
            return False
    if spec.language and str(dig(doc, "repository.language") or "").lower() != spec.language.lower():
        return False
    if spec.workflow_type and not text_contains_type(doc, spec.workflow_type, dimension=spec.dimension):
        return False
    if spec.topic:
        topics = [str(item).lower() for item in (dig(doc, "repository.topics") or [])]
        if spec.topic.lower() not in topics:
            return False
    if spec.failure_only and status_for(doc, spec.dimension, prefer_deployment=bool(spec.env or spec.workflow_type == "deploy")) not in FAILURE_VALUES:
        return False
    return True


def dimension_values(doc: dict, dimension: str) -> list[str]:
    if dimension == "workflow":
        value = dig(doc, "workflow_run.name")
        return [str(value)] if value else []
    if dimension == "repository":
        value = dig(doc, "repository.full_name")
        return [str(value)] if value else []
    if dimension == "job":
        value = dig(doc, "check_run.name")
        return [str(value)] if value else []
    if dimension == "team":
        value = team_from_repo(doc)
        return [value] if value else []
    if dimension == "architecture":
        return architectures_from_doc(doc)
    raise ValueError(f"Dimensão não suportada: {dimension}")


def unique_id_for(doc: dict, dimension: str | None) -> str | None:
    if dimension == "job":
        value = dig(doc, "check_run.id")
    else:
        value = dig(doc, "workflow_run.id")
    return str(value) if value is not None else None


def filtered_docs(all_docs: list[dict], spec: Spec) -> list[dict]:
    return [doc for doc in all_docs if matches(doc, spec)]


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} min"
    return f"{minutes / 60:.1f} h"


def duration_seconds(doc: dict, start_field: str, end_field: str) -> float | None:
    start = parse_iso(dig(doc, start_field))
    end = parse_iso(dig(doc, end_field))
    if not start or not end:
        return None
    seconds = (end - start).total_seconds()
    return seconds if seconds > 0 else None


def anchor_value(doc: dict, anchor_kind: str) -> datetime | None:
    field_map = {
        "repository_request": "repository.request.requested_at",
        "pipeline_request": "pipeline_enablement.requested_at",
        "workflow_created": "workflow.created_at",
    }
    return parse_iso(dig(doc, field_map[anchor_kind]))


def top_counts(all_docs: list[dict], spec: Spec) -> list[tuple[str, int]]:
    counters: dict[str, set[str]] = {}
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is None:
            continue
        for value in dimension_values(doc, spec.dimension):
            counters.setdefault(value, set()).add(unique_id)
    rows = [(label, len(ids)) for label, ids in counters.items()]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows[: spec.top_n]


def top_success_rates(all_docs: list[dict], spec: Spec) -> list[tuple[str, int, int, float]]:
    counters: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, str]] = set()
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is None:
            continue
        status = status_for(doc, spec.dimension, prefer_deployment=bool(spec.env or spec.workflow_type == "deploy"))
        for value in dimension_values(doc, spec.dimension):
            key = (value, unique_id)
            if key in seen:
                continue
            seen.add(key)
            bucket = counters.setdefault(value, {"total": 0, "success": 0, "failure": 0})
            bucket["total"] += 1
            if status in SUCCESS_VALUES:
                bucket["success"] += 1
            elif status in FAILURE_VALUES:
                bucket["failure"] += 1
    rows = []
    for label, bucket in counters.items():
        total = bucket["total"]
        success = bucket["success"]
        rate = (success / total) if total else 0.0
        rows.append((label, success, total, rate))
    rows.sort(key=lambda item: (-item[3], item[0]))
    return rows[: spec.top_n]


def top_failures(all_docs: list[dict], spec: Spec) -> list[tuple[str, int]]:
    counters: dict[str, set[str]] = {}
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is None:
            continue
        status = status_for(doc, spec.dimension, prefer_deployment=bool(spec.env or spec.workflow_type == "deploy"))
        if status not in FAILURE_VALUES:
            continue
        for value in dimension_values(doc, spec.dimension):
            counters.setdefault(value, set()).add(unique_id)
    rows = [(label, len(ids)) for label, ids in counters.items()]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows[: spec.top_n]


def distinct_values(all_docs: list[dict], spec: Spec) -> list[str]:
    values = set()
    for doc in filtered_docs(all_docs, spec):
        values.update(dimension_values(doc, spec.dimension))
    return sorted(values)


def status_mix(all_docs: list[dict], spec: Spec) -> tuple[int, int, int]:
    seen = set()
    success = failure = other = 0
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is None or unique_id in seen:
            continue
        seen.add(unique_id)
        status = status_for(doc, spec.dimension, prefer_deployment=True)
        if status in SUCCESS_VALUES:
            success += 1
        elif status in FAILURE_VALUES:
            failure += 1
        else:
            other += 1
    return success, failure, other


def latest_doc(all_docs: list[dict], spec: Spec) -> dict:
    docs = filtered_docs(all_docs, spec)
    docs.sort(key=lambda doc: document_time(doc) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    assert_true(bool(docs), f"Nenhum documento para validar: {spec.question}")
    return docs[0]


def recent_docs(all_docs: list[dict], spec: Spec, limit: int = 5) -> list[dict]:
    docs = filtered_docs(all_docs, spec)
    docs.sort(key=lambda doc: document_time(doc) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    result = []
    seen = set()
    for doc in docs:
        unique_id = unique_id_for(doc, "workflow")
        if unique_id in seen:
            continue
        seen.add(unique_id)
        result.append(doc)
        if len(result) == limit:
            break
    return result


def first_delivery_doc(all_docs: list[dict], spec: Spec) -> tuple[dict, float]:
    assert_true(spec.anchor_kind is not None, f"anchor_kind ausente: {spec.question}")
    docs = filtered_docs(all_docs, spec)
    docs = [doc for doc in docs if str(dig(doc, "deployment.task") or "").lower() in {"deploy", "rollback"}]
    docs.sort(key=lambda doc: parse_iso(dig(doc, "deployment.updated_at")) or datetime.max.replace(tzinfo=timezone.utc))
    for doc in docs:
        anchor_dt = anchor_value(doc, spec.anchor_kind)
        deploy_dt = parse_iso(dig(doc, "deployment.updated_at"))
        if not anchor_dt or not deploy_dt or deploy_dt < anchor_dt:
            continue
        return doc, (deploy_dt - anchor_dt).total_seconds()
    raise AssertionError(f"Sem primeira entrega para validar: {spec.question}")


def average_rollback_duration(all_docs: list[dict], spec: Spec) -> tuple[float, int]:
    docs = filtered_docs(all_docs, spec)
    seen = set()
    values = []
    for doc in docs:
        if str(dig(doc, "deployment.task") or "").lower() != "rollback":
            continue
        unique_id = unique_id_for(doc, "workflow")
        if not unique_id or unique_id in seen:
            continue
        seen.add(unique_id)
        duration = duration_seconds(doc, "workflow_run.run_started_at", "workflow_run.updated_at")
        if duration is not None:
            values.append(duration)
    assert_true(bool(values), f"Sem durações de rollback: {spec.question}")
    return sum(values) / len(values), len(values)


def deploy_frequency_metrics(all_docs: list[dict], spec: Spec) -> tuple[int, float, float]:
    docs = filtered_docs(all_docs, spec)
    execution_ids = {
        str(dig(doc, "workflow_run.id") or dig(doc, "deployment.updated_at"))
        for doc in docs
        if str(dig(doc, "deployment.task") or "").lower() == "deploy"
    }
    total = len(execution_ids)
    days = time_delta_for(spec.time_range).days
    per_day = total / days
    return total, per_day, per_day * 7


def first_dev_to_prd_gap_metrics(all_docs: list[dict], spec: Spec) -> tuple[float, int]:
    docs = filtered_docs(all_docs, spec)
    docs.sort(key=lambda doc: parse_iso(dig(doc, "deployment.updated_at")) or datetime.max.replace(tzinfo=timezone.utc))
    by_repo: dict[str, dict[str, datetime | None]] = {}
    for doc in docs:
        if str(dig(doc, "deployment.task") or "").lower() != "deploy":
            continue
        repo = str(dig(doc, "repository.full_name") or "")
        when = parse_iso(dig(doc, "deployment.updated_at"))
        if not repo or not when:
            continue
        by_repo.setdefault(repo, {"DEV": None, "PRD": None})
        for env in ["DEV", "PRD"]:
            if env_matches(doc, env) and by_repo[repo][env] is None:
                by_repo[repo][env] = when
    values = []
    for row in by_repo.values():
        if row["DEV"] and row["PRD"] and row["PRD"] >= row["DEV"]:
            values.append((row["PRD"] - row["DEV"]).total_seconds())
    assert_true(bool(values), f"Sem amostra DEV->PRD: {spec.question}")
    return sum(values) / len(values), len(values)


def dev_before_promotion_metrics(all_docs: list[dict], spec: Spec) -> tuple[float, int]:
    docs = filtered_docs(all_docs, spec)
    target_env = spec.target_env or spec.env or "PRD"
    by_repo: dict[str, list[dict]] = {}
    for doc in docs:
        if str(dig(doc, "deployment.task") or "").lower() != "deploy":
            continue
        repo = str(dig(doc, "repository.full_name") or "")
        if repo:
            by_repo.setdefault(repo, []).append(doc)
    counts = []
    for repo_docs in by_repo.values():
        repo_docs.sort(key=lambda doc: parse_iso(dig(doc, "deployment.updated_at")) or datetime.max.replace(tzinfo=timezone.utc))
        seen = set()
        dev_count = 0
        first_target = False
        for doc in repo_docs:
            unique_id = unique_id_for(doc, "workflow") or str(dig(doc, "deployment.updated_at"))
            if unique_id in seen:
                continue
            seen.add(unique_id)
            if env_matches(doc, "DEV"):
                dev_count += 1
            if env_matches(doc, target_env):
                first_target = True
                break
        if first_target:
            counts.append(dev_count)
    assert_true(bool(counts), f"Sem amostra DEV antes de promoção: {spec.question}")
    return sum(counts) / len(counts), len(counts)


def multiple_rollbacks_rows(all_docs: list[dict], spec: Spec) -> list[tuple[str, int]]:
    counters: dict[str, set[str]] = {}
    for doc in filtered_docs(all_docs, spec):
        if str(dig(doc, "deployment.task") or "").lower() != "rollback":
            continue
        repo = str(dig(doc, "repository.full_name") or "")
        workflow = str(dig(doc, "workflow_run.name") or "")
        unique_id = unique_id_for(doc, "workflow")
        if repo and workflow and unique_id:
            counters.setdefault(f"{repo} | {workflow}", set()).add(unique_id)
    rows = [(label, len(ids)) for label, ids in counters.items() if len(ids) > 1]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return rows


def actor_emails(all_docs: list[dict], spec: Spec) -> list[str]:
    emails = sorted(
        {
            str(dig(doc, "sender.email") or "")
            for doc in filtered_docs(all_docs, spec)
            if dig(doc, "sender.email") and str(dig(doc, "sender.type") or "").lower() != "bot"
        }
    )
    return [email for email in emails if email]


def analysts_for_workflow(all_docs: list[dict], spec: Spec) -> list[str]:
    analysts = sorted(
        {
            f"{dig(doc, 'sender.login')} <{dig(doc, 'sender.email')}>"
            for doc in filtered_docs(all_docs, spec)
            if dig(doc, "sender.login") and dig(doc, "sender.email") and str(dig(doc, "sender.type") or "").lower() != "bot"
        }
    )
    return analysts


def validate_output(all_docs: list[dict], spec: Spec, raw: str, packed: str):
    if spec.kind == "rank_volume":
        rows = top_counts(all_docs, spec)
        assert_true(bool(rows), f"Sem linhas para validar: {spec.question}")
        label, count = rows[0]
        assert_true(contains_fragment(packed, label), f"Rótulo esperado ausente: {label}\n{raw}")
        assert_true(str(count) in raw, f"Contagem esperada ausente: {count}\n{raw}")
        return

    if spec.kind == "rank_failure":
        rows = top_failures(all_docs, spec)
        if not rows:
            assert_true("0" in packed, f"Esperava resposta zerada: {spec.question}\n{raw}")
            return
        top_count = rows[0][1]
        acceptable = [label for label, count in rows if count == top_count]
        assert_true(any(contains_fragment(packed, label) for label in acceptable), f"Rótulo esperado ausente: {acceptable[0]}\n{raw}")
        return

    if spec.kind == "rank_failure_loose":
        rows = top_failures(all_docs, spec)
        if not rows:
            assert_true("0" in packed, f"Esperava resposta zerada: {spec.question}\n{raw}")
            return
        top_count = rows[0][1]
        acceptable = [label for label, count in rows if count == top_count]
        assert_true(any(contains_fragment(packed, label) for label in acceptable), f"Rótulo esperado ausente: {acceptable[0]}\n{raw}")
        return

    if spec.kind == "rank_success":
        rows = top_success_rates(all_docs, spec)
        if not rows:
            assert_true("0" in packed, f"Esperava resposta zerada: {spec.question}\n{raw}")
            return
        for label, _, _, _ in rows[: min(3, len(rows))]:
            assert_true(contains_fragment(packed, label), f"Rótulo esperado ausente: {label}\n{raw}")
        return

    if spec.kind == "inventory":
        values = distinct_values(all_docs, spec)
        assert_true(bool(values), f"Sem inventário para validar: {spec.question}")
        for value in values[: min(3, len(values))]:
            assert_true(contains_fragment(packed, value), f"Valor esperado ausente: {value}\n{raw}")
        return

    if spec.kind == "count":
        values = distinct_values(all_docs, spec)
        assert_true(str(len(values)) in packed, f"Contagem esperada ausente: {len(values)}\n{raw}")
        return

    if spec.kind == "status_mix":
        success, failure, other = status_mix(all_docs, spec)
        total = success + failure + other
        assert_true(str(total) in packed, f"Total esperado ausente: {total}\n{raw}")
        assert_true(str(success) in packed, f"Sucessos esperados ausentes: {success}\n{raw}")
        assert_true(str(failure) in packed, f"Falhas esperadas ausentes: {failure}\n{raw}")
        return

    if spec.kind == "latest_failure":
        doc = latest_doc(all_docs, spec)
        workflow = str(dig(doc, "workflow_run.name"))
        repo = str(dig(doc, "repository.full_name"))
        when = str(dig(doc, "workflow_run.run_started_at") or dig(doc, "@timestamp"))
        assert_true(contains_fragment(packed, workflow), f"Workflow esperado ausente: {workflow}\n{raw}")
        assert_true(contains_fragment(packed, repo), f"Repo esperado ausente: {repo}\n{raw}")
        assert_true(contains_fragment(packed, when), f"Data esperada ausente: {when}\n{raw}")
        return

    if spec.kind == "recent_list":
        docs = recent_docs(all_docs, spec, limit=1)
        assert_true(bool(docs), f"Sem linhas recentes: {spec.question}")
        for doc in docs:
            repo = str(dig(doc, "repository.full_name"))
            workflow = str(dig(doc, "workflow_run.name"))
            assert_true(contains_fragment(packed, repo), f"Repo esperado ausente: {repo}\n{raw}")
            assert_true(contains_fragment(packed, workflow), f"Workflow esperado ausente: {workflow}\n{raw}")
        return

    if spec.kind == "anchor_lead_time":
        doc, seconds = first_delivery_doc(all_docs, spec)
        repo = str(dig(doc, "repository.full_name"))
        workflow = str(dig(doc, "workflow_run.name"))
        when = str(dig(doc, "deployment.updated_at"))
        assert_true(contains_fragment(packed, repo), f"Repo esperado ausente: {repo}\n{raw}")
        assert_true(contains_fragment(packed, workflow), f"Workflow esperado ausente: {workflow}\n{raw}")
        assert_true(contains_fragment(packed, when), f"Data esperada ausente: {when}\n{raw}")
        assert_true(contains_fragment(packed, format_duration(seconds)), f"Duração esperada ausente: {format_duration(seconds)}\n{raw}")
        return

    if spec.kind == "avg_rollback_duration":
        avg_seconds, count = average_rollback_duration(all_docs, spec)
        assert_true(contains_fragment(packed, format_duration(avg_seconds)), f"Duração média ausente: {format_duration(avg_seconds)}\n{raw}")
        assert_true(str(count) in packed, f"Quantidade esperada ausente: {count}\n{raw}")
        return

    if spec.kind == "frequency":
        total, per_day, _ = deploy_frequency_metrics(all_docs, spec)
        assert_true(str(total) in packed, f"Total esperado ausente: {total}\n{raw}")
        assert_true(f"{per_day:.2f}" in packed, f"Frequência/dia esperada ausente: {per_day:.2f}\n{raw}")
        return

    if spec.kind == "dev_prd_gap":
        avg_seconds, count = first_dev_to_prd_gap_metrics(all_docs, spec)
        assert_true(contains_fragment(packed, format_duration(avg_seconds)), f"Gap esperado ausente: {format_duration(avg_seconds)}\n{raw}")
        assert_true(str(count) in packed, f"Amostra esperada ausente: {count}\n{raw}")
        return

    if spec.kind == "dev_before_promotion":
        avg_count, count = dev_before_promotion_metrics(all_docs, spec)
        assert_true(str(count) in packed, f"Amostra esperada ausente: {count}\n{raw}")
        assert_true("deploys em DEV" in raw or "deploys em dev" in packed.lower(), f"Texto esperado ausente para DEV: {raw}")
        return

    if spec.kind == "email_inventory":
        emails = actor_emails(all_docs, spec)
        assert_true(bool(emails), f"Sem emails para validar: {spec.question}")
        for email in emails[: min(3, len(emails))]:
            assert_true(contains_fragment(packed, email), f"Email esperado ausente: {email}\n{raw}")
        return

    if spec.kind == "last_email":
        doc = latest_doc(all_docs, spec)
        email = str(dig(doc, "sender.email"))
        repo = str(dig(doc, "repository.full_name"))
        when = str(dig(doc, "deployment.updated_at") or dig(doc, "workflow_run.run_started_at"))
        assert_true(contains_fragment(packed, email), f"Email esperado ausente: {email}\n{raw}")
        assert_true(contains_fragment(packed, repo), f"Repo esperado ausente: {repo}\n{raw}")
        assert_true(contains_fragment(packed, when), f"Data esperada ausente: {when}\n{raw}")
        return

    if spec.kind == "analysts_inventory":
        analysts = analysts_for_workflow(all_docs, spec)
        assert_true(bool(analysts), f"Sem analistas para validar: {spec.question}")
        for analyst in analysts[: min(3, len(analysts))]:
            assert_true(contains_fragment(packed, analyst), f"Analista esperado ausente: {analyst}\n{raw}")
        return

    if spec.kind == "multiple_rollbacks":
        rows = multiple_rollbacks_rows(all_docs, spec)
        assert_true(bool(rows), f"Sem múltiplos rollbacks para validar: {spec.question}")
        label, count = rows[0]
        assert_true(contains_fragment(packed, label), f"Esteira esperada ausente: {label}\n{raw}")
        assert_true(str(count) in packed, f"Quantidade esperada ausente: {count}\n{raw}")
        return

    raise AssertionError(f"Kind não suportado: {spec.kind}")


def period_phrase(time_range: str) -> str:
    mapping = {"7d": "ultimos 7 dias", "30d": "ultimo mes", "90d": "ultimos 90 dias"}
    return mapping[time_range]


def build_specs() -> list[Spec]:
    specs: list[Spec] = []

    specs.extend(
        [
            Spec("liste os repositorios que ja executaram workflows em algum momento", "inventory", dimension="repository", time_range="365d", list_mode=True, top_n=20),
            Spec("Mostre os repositorios que ja executaram workflows na base", "inventory", dimension="repository", time_range="365d", list_mode=True, top_n=20),
            Spec("Informe os repositorios que ja executaram workflows historicamente", "inventory", dimension="repository", time_range="365d", list_mode=True, top_n=20),
            Spec("Liste os repositorios que ja executaram workflows ate hoje", "inventory", dimension="repository", time_range="365d", list_mode=True, top_n=20),
            Spec("Liste a quantidade de times que ja executaram esteiras", "count", dimension="team", time_range="365d"),
            Spec("Quantos repositorios temos com execucoes de workflows", "count", dimension="repository", time_range="365d"),
            Spec("Quais arquiteturas executaram deploy no ultimo mes?", "rank_volume", dimension="architecture", workflow_type="deploy", time_range="30d"),
            Spec("Quais arquiteturas executaram deploy em PRD no ultimo mes?", "rank_volume", dimension="architecture", workflow_type="deploy", env="PRD", time_range="30d"),
            Spec("Quais arquiteturas executaram deploy em HML no ultimo mes?", "rank_volume", dimension="architecture", workflow_type="deploy", env="HML", time_range="30d"),
            Spec("Quais arquiteturas executaram deploy em DEV no ultimo mes?", "rank_volume", dimension="architecture", workflow_type="deploy", env="DEV", time_range="30d"),
            Spec("Quais arquiteturas falharam no build no ultimo mes?", "rank_failure", dimension="architecture", workflow_type="build", time_range="30d"),
            Spec("Qual foi o ultimo workflow que falhou em produção?", "latest_failure", dimension="workflow", env="PRD", failure_only=True, time_range="365d"),
            Spec("Qual foi o ultimo workflow que falhou em homologacao?", "latest_failure", dimension="workflow", env="HML", failure_only=True, time_range="365d"),
            Spec("Qual foi o ultimo workflow que falhou em dev?", "latest_failure", dimension="workflow", env="DEV", failure_only=True, time_range="365d"),
            Spec("Liste os repositorios que falharam na ultima semana", "recent_list", dimension="repository", failure_only=True, time_range="7d", list_mode=True),
            Spec("Liste os ultimos projetos que tiveram deploy com falha", "recent_list", dimension="repository", workflow_type="deploy", failure_only=True, time_range="30d", list_mode=True),
            Spec("Liste os ultimos projetos que tiveram deploy com falha em PRD", "recent_list", dimension="repository", workflow_type="deploy", env="PRD", failure_only=True, time_range="30d", list_mode=True),
            Spec("Quais os ultimos deploys das esteiras de bff?", "recent_list", dimension="repository", architecture="bff", workflow_type="deploy", time_range="30d", list_mode=True),
            Spec("Quais os ultimos deploys das esteiras de api?", "recent_list", dimension="repository", architecture="api", workflow_type="deploy", time_range="30d", list_mode=True),
            Spec("Mostre os ultimos deploys das esteiras de apim", "recent_list", dimension="repository", architecture="apim", workflow_type="deploy", time_range="30d", list_mode=True),
            Spec("Mostre os ultimos deploys das esteiras de srv", "recent_list", dimension="repository", architecture="srv", workflow_type="deploy", time_range="30d", list_mode=True),
            Spec("Informe os repositorios que falharam na ultima semana", "recent_list", dimension="repository", failure_only=True, time_range="7d", list_mode=True),
            Spec("Quais os times que mais falharam em etapas de build e gate?", "rank_failure_loose", dimension="team", workflow_type="build", time_range="90d"),
            Spec("Qual a porcentagem de falha e sucesso em deploys do time de devops?", "status_mix", dimension="workflow", team="devops", workflow_type="deploy", time_range="90d"),
            Spec("Qual a porcentagem de falha e sucesso em deploys do time de ia?", "status_mix", dimension="workflow", team="ia", workflow_type="deploy", time_range="90d"),
            Spec("Quais arquiteturas executaram deploy em PRD nos ultimos 90 dias?", "rank_volume", dimension="architecture", workflow_type="deploy", env="PRD", time_range="90d"),
            Spec("Quais arquiteturas executaram deploy em HML nos ultimos 90 dias?", "rank_volume", dimension="architecture", workflow_type="deploy", env="HML", time_range="90d"),
            Spec("Quais arquiteturas executaram deploy em DEV nos ultimos 90 dias?", "rank_volume", dimension="architecture", workflow_type="deploy", env="DEV", time_range="90d"),
            Spec("Quanto tempo leva a execucao media de esteiras de rollback?", "avg_rollback_duration", dimension="workflow", workflow_type="rollback", time_range="90d"),
            Spec("Quais esteiras realizaram rollback nos ultimos 30 dias?", "recent_list", dimension="repository", workflow_type="rollback", time_range="30d", list_mode=True),
            Spec("Quais esteiras executaram mais de um rollback nos ultimos 50 dias?", "multiple_rollbacks", dimension="repository", workflow_type="rollback", time_range="50d"),
            Spec("Qual e a frequencia de deploy da arquitetura api?", "frequency", dimension="workflow", architecture="api", workflow_type="deploy", time_range="90d"),
            Spec("Qual e a frequencia de deploy da arquitetura srv?", "frequency", dimension="workflow", architecture="srv", workflow_type="deploy", time_range="90d"),
            Spec("Qual e a frequencia de deploy do time devops?", "frequency", dimension="workflow", team="devops", workflow_type="deploy", time_range="90d"),
            Spec("Qual e a frequencia de deploy da esteira Deploy Staging?", "frequency", dimension="workflow", workflow_name="Deploy Staging", workflow_type="deploy", time_range="90d"),
            Spec("Quanto tempo leva em media entre o primeiro deploy em DEV e o primeiro deploy em PRD?", "dev_prd_gap", dimension="repository", workflow_type="deploy", time_range="365d"),
            Spec("Em media quantos deploys em DEV ocorrem para o deploy em PRD?", "dev_before_promotion", dimension="repository", workflow_type="deploy", target_env="PRD", time_range="365d"),
            Spec("Quantos times trabalham com as esteiras da arquitetura api?", "count", dimension="team", architecture="api", time_range="90d"),
            Spec("Quais o email dos analistas incluidos nos deploys da arquitetura api?", "email_inventory", dimension="workflow", architecture="api", workflow_type="deploy", time_range="90d"),
            Spec("Quais o email dos analistas incluidos nos deploys da arquitetura bff?", "email_inventory", dimension="workflow", architecture="bff", workflow_type="deploy", time_range="90d"),
            Spec("Qual o email do analista que engatilhou o ultimo deploy em PRD da esteira Deploy Staging?", "last_email", dimension="workflow", workflow_name="Deploy Staging", env="PRD", workflow_type="deploy", time_range="365d"),
            Spec("Quais os analistas que estao trabalhando na esteira Deploy Staging?", "analysts_inventory", dimension="workflow", workflow_name="Deploy Staging", time_range="90d"),
            Spec("Qual foi o tempo entre a abertura do chamado do repositorio nada/arch-api-cash-cambio-contatos-ext e a primeira entrega em PRD?", "anchor_lead_time", dimension="repository", repo_name="nada/arch-api-cash-cambio-contatos-ext", env="PRD", workflow_type="deploy", time_range="365d", anchor_kind="repository_request"),
            Spec("Qual foi o tempo entre a solicitacao de habilitacao da esteira do repositorio nada/devops-bff-pix-web e a primeira entrega em HML?", "anchor_lead_time", dimension="repository", repo_name="nada/devops-bff-pix-web", env="HML", workflow_type="deploy", time_range="365d", anchor_kind="pipeline_request"),
            Spec("Quanto tempo entre a criacao da esteira Rollback Production e o primeiro deploy em PRD?", "anchor_lead_time", dimension="workflow", workflow_name="Rollback Production", env="PRD", workflow_type="rollback", time_range="365d", anchor_kind="workflow_created"),
            Spec("Qual e a frequencia de deploy da arquitetura bff?", "frequency", dimension="workflow", architecture="bff", workflow_type="deploy", time_range="90d"),
            Spec("Quais esteiras realizaram rollback nos ultimos 90 dias?", "recent_list", dimension="repository", workflow_type="rollback", time_range="90d", list_mode=True),
            Spec("Qual o email do analista que engatilhou o ultimo deploy em PRD da esteira Axway Deploy Release?", "last_email", dimension="workflow", workflow_name="Axway Deploy Release", env="PRD", workflow_type="deploy", time_range="365d"),
        ]
    )

    for arch in ARCHITECTURES:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais workflows da arquitetura de {arch} foram executados nos {phrase}?", "rank_volume", dimension="workflow", architecture=arch, time_range=time_range),
                    Spec(f"Quais workflows da arquitetura de {arch} mais falharam nos {phrase}?", "rank_failure", dimension="workflow", architecture=arch, time_range=time_range),
                    Spec(f"Quais workflows da arquitetura de {arch} tem maior taxa de sucesso nos {phrase}?", "rank_success", dimension="workflow", architecture=arch, time_range=time_range),
                    Spec(f"Quais repositorios da arquitetura de {arch} mais executaram workflows nos {phrase}?", "rank_volume", dimension="repository", architecture=arch, time_range=time_range),
                    Spec(f"Quais jobs da arquitetura de {arch} mais executaram workflows nos {phrase}?", "rank_volume", dimension="job", architecture=arch, time_range=time_range),
                ]
            )

    for team in TEAMS:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais workflows do time {team} mais executaram nos {phrase}?", "rank_volume", dimension="workflow", team=team, time_range=time_range),
                    Spec(f"Quais workflows do time {team} mais falharam nos {phrase}?", "rank_failure", dimension="workflow", team=team, time_range=time_range),
                    Spec(f"Quais repositorios do time {team} mais executaram workflows nos {phrase}?", "rank_volume", dimension="repository", team=team, time_range=time_range),
                    Spec(f"Qual a porcentagem de falha e sucesso em deploys do time de {team} nos {phrase}?", "status_mix", dimension="workflow", team=team, workflow_type="deploy", time_range=time_range),
                ]
            )

    for env in ENVS:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais workflows mais executaram em {env} nos {phrase}?", "rank_volume", dimension="workflow", env=env, time_range=time_range),
                    Spec(f"Quais workflows com maior volume de falhas em {env} nos {phrase}?", "rank_failure", dimension="workflow", env=env, time_range=time_range),
                    Spec(f"Quais repositorios mais executaram workflows em {env} nos {phrase}?", "rank_volume", dimension="repository", env=env, time_range=time_range),
                    Spec(f"Quais jobs com maior volume de falhas em {env} nos {phrase}?", "rank_failure", dimension="job", env=env, time_range=time_range),
                ]
            )

    for display_language, language in LANGUAGES:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais workflows {display_language} mais executaram nos {phrase}?", "rank_volume", dimension="workflow", language=language, time_range=time_range),
                    Spec(f"Quais repositorios {display_language} mais executaram workflows nos {phrase}?", "rank_volume", dimension="repository", language=language, time_range=time_range),
                    Spec(f"Quais workflows {display_language} com maior taxa de sucesso nos {phrase}?", "rank_success", dimension="workflow", language=language, time_range=time_range),
                ]
            )

    for workflow_type in WORKFLOW_TYPES:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais workflows de {workflow_type} mais executaram nos {phrase}?", "rank_volume", dimension="workflow", workflow_type=workflow_type, time_range=time_range),
                    Spec(f"Quais workflows de {workflow_type} com maior taxa de sucesso nos {phrase}?", "rank_success", dimension="workflow", workflow_type=workflow_type, time_range=time_range),
                    Spec(f"Quais jobs de {workflow_type} mais executaram nos {phrase}?", "rank_volume", dimension="job", workflow_type=workflow_type, time_range=time_range),
                ]
            )

    for topic in TOPICS:
        for time_range, phrase in PERIODS:
            specs.extend(
                [
                    Spec(f"Quais repositorios do topico {topic} mais executaram workflows nos {phrase}?", "rank_volume", dimension="repository", topic=topic, time_range=time_range),
                    Spec(f"Quais repositorios do topico {topic} com maior volume de falhas nos {phrase}?", "rank_failure", dimension="repository", topic=topic, time_range=time_range),
                    Spec(f"Quantos repositorios do topico {topic} tiveram execucoes de workflows nos {phrase}?", "count", dimension="repository", topic=topic, time_range=time_range),
                ]
            )

    seen = set()
    unique_specs = []
    for spec in specs:
        if spec.question not in seen:
            seen.add(spec.question)
            unique_specs.append(spec)
    return unique_specs


def load_documents() -> list[dict]:
    config = load_config(str(ROOT / "config.yaml"))
    client = get_client(config)
    response = client.search(index=get_index(config), size=2000, sort=["_doc"])
    return [hit["_source"] for hit in response["hits"]["hits"]]


def main(limit: int | None = None, start: int = 1):
    specs = build_specs()
    assert_true(start >= 1, "O parâmetro --start deve ser >= 1.")
    if limit is not None:
        specs = specs[:limit]

    docs = load_documents()
    assert_true(len(docs) > 0, "Nenhum documento encontrado no Elasticsearch.")

    slowest = ("", 0.0)
    total = len(specs)
    selected = specs[start - 1 :]
    for index, spec in enumerate(selected, start=start):
        elapsed, raw, packed = cli_output(spec.question)
        validate_output(docs, spec, raw, packed)
        if elapsed > slowest[1]:
            slowest = (spec.question, elapsed)
        print(f"{index}/{total} OK :: {spec.question}", flush=True)

    print(f"OK: {len(selected)} perguntas cross-validated passaram nesta rodada.", flush=True)
    print(f"Mais lenta: {slowest[1]:.2f}s :: {slowest[0]}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start", type=int, default=1)
    args = parser.parse_args()
    try:
        main(limit=args.limit, start=args.start)
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(1)

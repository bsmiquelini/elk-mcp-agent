"""
Suíte cross-validated da CLI:
- executa perguntas reais na CLI
- confirma no Elasticsearch se a resposta bate com os dados
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))

from config_loader import load_config
from elastic_client import get_client, get_index
from generate_department_question_catalog import build_catalog, discover_context


SUCCESS_VALUES = {"success", "completed"}
FAILURE_VALUES = {"failure", "failed", "error", "timed_out", "cancelled", "canceled"}
CLI_TIMEOUT_SECONDS = int(os.getenv("CLI_TEST_TIMEOUT_SECONDS", "120"))
APP_TZ = ZoneInfo("America/Sao_Paulo")
APP_TZ_NAME = "America/Sao_Paulo"


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
    branch: str | None = None


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
        timeout=CLI_TIMEOUT_SECONDS,
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


def now_local() -> datetime:
    return datetime.now(APP_TZ)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def to_app_timezone(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TZ)


def format_local_datetime(value: datetime | str | None) -> str:
    if value in (None, ""):
        return "-"
    dt = value if isinstance(value, datetime) else parse_iso(str(value))
    if not dt:
        return str(value)
    local_dt = to_app_timezone(dt)
    offset = local_dt.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return f"{local_dt.strftime('%Y-%m-%d %H:%M:%S')} {offset} ({APP_TZ_NAME})"


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
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", time_range):
        return timedelta(days=1)
    if ".." in time_range:
        start_raw, end_raw = time_range.split("..", 1)
        start_day = date.fromisoformat(start_raw)
        end_day = date.fromisoformat(end_raw)
        return timedelta(days=abs((end_day - start_day).days) + 1)
    value = int(time_range[:-1])
    unit = time_range[-1]
    if unit == "d":
        return timedelta(days=value)
    if unit == "h":
        return timedelta(hours=value)
    raise ValueError(f"time_range não suportado: {time_range}")


def document_time(doc: dict) -> datetime | None:
    return parse_iso(dig(doc, "workflow_run.run_started_at")) or parse_iso(dig(doc, "@timestamp"))


def in_time_range(doc: dict, time_range: str) -> bool:
    dt = document_time(doc)
    if not dt:
        return False
    local_dt = to_app_timezone(dt)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", time_range):
        return bool(local_dt and local_dt.date() == date.fromisoformat(time_range))
    if ".." in time_range:
        start_raw, end_raw = time_range.split("..", 1)
        start_day = date.fromisoformat(start_raw)
        end_day = date.fromisoformat(end_raw)
        if end_day < start_day:
            start_day, end_day = end_day, start_day
        return bool(local_dt and start_day <= local_dt.date() <= end_day)
    return bool(local_dt and local_dt >= (now_local() - time_delta_for(time_range)))


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
        "STG": {"STG", "STAGING"},
    }
    token_map = {
        "PRD": ["prd", "prod", "production", "release"],
        "HML": ["hml", "hom", "homolog", "staging", "stg"],
        "DEV": ["dev", "sandbox", "develop"],
        "STG": ["stg", "staging"],
    }
    exact_raw = str(dig(doc, "deployment.environment") or dig(doc, "deployment_status.environment") or "")
    if exact_raw:
        return exact_raw.upper() in exact_map.get(env, set())
    return False


def status_for(doc: dict, dimension: str | None, prefer_deployment: bool) -> str:
    if dimension == "job":
        return str(dig(doc, "check_run.conclusion") or dig(doc, "check_run.status") or "").lower()
    if prefer_deployment:
        deployment_status = str(dig(doc, "deployment_status.state") or "").lower()
        if deployment_status:
            return deployment_status
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
    if spec.branch and str(dig(doc, "workflow_run.head_branch") or "").lower() != spec.branch.lower():
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
    if dimension == "topic":
        topics = dig(doc, "repository.topics") or []
        if not isinstance(topics, list):
            topics = [topics]
        return [
            str(topic).lower()
            for topic in topics
            if topic and not str(topic).lower().startswith(("archtecture-", "architecture-"))
        ]
    if dimension == "language":
        value = dig(doc, "repository.language")
        return [str(value).lower()] if value else []
    if dimension == "branch":
        value = dig(doc, "workflow_run.head_branch")
        return [str(value)] if value else []
    if dimension == "environment":
        value = dig(doc, "deployment.environment") or dig(doc, "deployment_status.environment")
        return [str(value).upper()] if value else []
    raise ValueError(f"Dimensão não suportada: {dimension}")


def unique_id_for(doc: dict, dimension: str | None) -> str | None:
    if dimension == "job":
        value = dig(doc, "check_run.id")
    else:
        value = dig(doc, "workflow_run.id")
    return str(value) if value is not None else None


def filtered_docs(all_docs: list[dict], spec: Spec) -> list[dict]:
    return [doc for doc in all_docs if matches(doc, spec)]


def execution_total(all_docs: list[dict], spec: Spec) -> int:
    unique_ids = set()
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is not None:
            unique_ids.add(unique_id)
    return len(unique_ids)


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
    prefer_deployment = "deploy" in spec.question.lower()
    for doc in filtered_docs(all_docs, spec):
        unique_id = unique_id_for(doc, spec.dimension)
        if unique_id is None or unique_id in seen:
            continue
        seen.add(unique_id)
        status = status_for(doc, spec.dimension, prefer_deployment=prefer_deployment)
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
        if not rows:
            assert_true("0" in packed, f"Esperava resposta zerada: {spec.question}\n{raw}")
            return
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

    if spec.kind == "execution_total":
        total = execution_total(all_docs, spec)
        assert_true(str(total) in packed, f"Total esperado ausente: {total}\n{raw}")
        return

    if spec.kind == "status_mix":
        success, failure, other = status_mix(all_docs, spec)
        considered_total = success + failure
        assert_true(str(considered_total) in packed, f"Total esperado ausente: {considered_total}\n{raw}")
        assert_true(str(success) in packed, f"Sucessos esperados ausentes: {success}\n{raw}")
        assert_true(str(failure) in packed, f"Falhas esperadas ausentes: {failure}\n{raw}")
        if other > 0:
            assert_true("apenas execucoes concluidas em sucesso ou falha" in packed.lower(), f"Contexto sobre outros estados ausente: {raw}")
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
        if not docs:
            assert_true("0" in packed, f"Esperava resposta zerada: {spec.question}\n{raw}")
            return
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


def spec_from_item(item: dict) -> Spec:
    return Spec(
        question=item["question"],
        kind=item["kind"],
        dimension=item.get("dimension"),
        time_range=item.get("time_range", "30d"),
        architecture=item.get("architecture"),
        team=item.get("team"),
        env=item.get("env"),
        language=item.get("language"),
        workflow_type=item.get("workflow_type"),
        topic=item.get("topic"),
        failure_only=item.get("failure_only", False),
        success_rate=item.get("success_rate", False),
        list_mode=item.get("list_mode", False),
        top_n=item.get("top_n", 5),
        repo_name=item.get("repo_name"),
        workflow_name=item.get("workflow_name"),
        anchor_kind=item.get("anchor_kind"),
        target_env=item.get("target_env"),
        branch=item.get("branch"),
    )


def build_specs(all_docs: list[dict], config: dict) -> list[Spec]:
    context = discover_context(all_docs, config)
    items = build_catalog(context)
    return [spec_from_item(item) for item in items]


def load_documents() -> list[dict]:
    config = load_config(str(ROOT / "config.yaml"))
    client = get_client(config)
    response = client.search(index=get_index(config), size=5000, sort=["_doc"])
    return [hit["_source"] for hit in response["hits"]["hits"]]


def main(limit: int | None = None, start: int = 1):
    assert_true(start >= 1, "O parâmetro --start deve ser >= 1.")
    config = load_config(str(ROOT / "config.yaml"))
    docs = load_documents()
    assert_true(len(docs) > 0, "Nenhum documento encontrado no Elasticsearch.")
    specs = build_specs(docs, config)
    if limit is not None:
        specs = specs[:limit]

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

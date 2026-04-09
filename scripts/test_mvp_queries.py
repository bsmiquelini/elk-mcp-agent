"""
Smoke tests do MVP contra os índices github-workflows* e o agente CLI.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
ARTIFACTS_DIR = ROOT / "artifacts" / "dashboards"

from config_loader import load_config
from tools.aggregate import aggregate
from tools.discover_schema import discover_schema
from tools.searcher import search


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def compact(text: str) -> str:
    text = re.sub(r"[╭╮╰╯│─]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def run_agent(question: str) -> str:
    proc = subprocess.run(
        ["python3", "agent/main.py", "--question", question],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    output = compact(strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or "")))
    assert_true(proc.returncode == 0, f"Agente falhou para pergunta: {question}\n{output}")
    return output


def compute_deploy_totals(buckets: list[dict]) -> tuple[int, int, int, int]:
    success_values = {"success", "completed"}
    failure_values = {"failure", "failed", "error", "timed_out"}

    total = sum(bucket.get("count", 0) for bucket in buckets)
    success = sum(bucket.get("count", 0) for bucket in buckets if str(bucket.get("group")).lower() in success_values)
    failure = sum(bucket.get("count", 0) for bucket in buckets if str(bucket.get("group")).lower() in failure_values)
    other = total - success - failure
    return total, success, failure, other


def pct(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{(value / total) * 100:.2f}%"


def assert_dashboard_file(filename: str, fragments: list[str]):
    path = ARTIFACTS_DIR / filename
    assert_true(path.exists(), f"Dashboard HTML nao encontrado: {path}")
    content = path.read_text(encoding="utf-8")
    for fragment in fragments:
        assert_true(fragment in content, f"Fragmento '{fragment}' nao encontrado em {path}")


def main():
    cfg = load_config(str(ROOT / "config.yaml"))

    schema = discover_schema(cfg)
    assert_true("error" not in schema, f"discover_schema falhou: {schema}")
    assert_true(schema["total_docs"] > 0, "Nenhum documento encontrado em github-workflows*")
    profile = schema.get("profile", {})
    assert_true(profile.get("primary_time_field"), "Profile sem primary_time_field")
    assert_true(profile.get("workflow_name_field"), "Profile sem workflow_name_field")
    assert_true(profile.get("job_name_field"), "Profile sem job_name_field")
    assert_true(profile.get("deploy_indicator_field"), "Profile sem deploy_indicator_field")

    latest = search(
        cfg,
        time_range="90d",
        sort=f"{profile['primary_time_field']}:desc",
        limit=1,
    )
    assert_true("error" not in latest, f"Busca do ultimo workflow falhou: {latest}")
    assert_true(latest["shown"] == 1, "Busca do ultimo workflow nao retornou 1 documento")
    latest_doc = latest["documents"][0]
    latest_name = latest_doc["workflow_run"]["name"]
    latest_repo = latest_doc["repository"]["full_name"]
    latest_status = latest_doc["workflow_run"].get("conclusion") or latest_doc["workflow_run"].get("status")

    deploys = aggregate(
        cfg,
        metric="count",
        field=profile["deploy_indicator_field"],
        group_by=profile["deploy_indicator_field"],
        time_range="1d",
        filters={profile["deploy_indicator_field"]: "deploy"},
    )
    assert_true("error" not in deploys, f"Agregacao de deploys falhou: {deploys}")
    deploy_count = sum(bucket.get("count", 0) for bucket in deploys.get("result", []))

    deploy_rate = aggregate(
        cfg,
        metric="count",
        field="deployment_status.state",
        group_by="deployment_status.state",
        time_range="30d",
        filters={"deployment.task": "deploy", "repository.language": "java"},
    )
    assert_true("error" not in deploy_rate, f"Agregacao de taxa de deploy falhou: {deploy_rate}")
    assert_true(len(deploy_rate.get("result", [])) > 0, "Sem buckets para taxa de deploy Java")
    _, success, failure, other = compute_deploy_totals(deploy_rate["result"])
    total = success + failure + other

    build_failures = aggregate(
        cfg,
        metric="count",
        field=profile["job_name_field"],
        group_by=profile["job_name_field"],
        time_range="90d",
        filters={
            profile["job_status_field"]: ["failure", "failed", "error", "timed_out"],
            profile["job_name_field"]: ["*build*", "*compile*"],
        },
    )
    assert_true("error" not in build_failures, f"Agregacao de falhas de build falhou: {build_failures}")
    assert_true(len(build_failures.get("result", [])) > 0, "Sem recorrencia de falhas de build")
    build_top = build_failures["result"][:3]

    executed_jobs = aggregate(
        cfg,
        metric="count",
        field=profile["job_name_field"],
        group_by=profile["job_name_field"],
        time_range="365d",
        size=10,
    )
    assert_true("error" not in executed_jobs, f"Agregacao de jobs executados falhou: {executed_jobs}")
    assert_true(len(executed_jobs.get("result", [])) > 0, "Sem jobs executados para ranking")
    executed_jobs_top = executed_jobs["result"][:5]

    latest_out = run_agent("Qual foi o ultimo workflow que rodou?")
    assert_true("ultimo workflow encontrado foi" in latest_out.lower(), latest_out)
    assert_true(latest_name in latest_out, latest_out)
    assert_true(latest_repo in latest_out, latest_out)
    assert_true(str(latest_status) in latest_out, latest_out)
    assert_dashboard_file("latest_workflow.html", ["Ultimo Workflow Executado", latest_name, latest_repo])

    deploys_out = run_agent("Quantos deploys ocorreram no ultimo dia?")
    if deploy_count == 0:
        assert_true("nenhum deploy ocorreu no ultimo dia" in deploys_out.lower(), deploys_out)
    else:
        assert_true(f"Foram encontrados {deploy_count} deploys no ultimo dia." in deploys_out, deploys_out)
    assert_dashboard_file("deploys_last_day.html", ["Deploys no Ultimo Dia"])

    rate_out = run_agent("Qual a taza de sucesso e falha nos deploys de workflows java?")
    assert_true("taxa dos deploys java" in rate_out.lower(), rate_out)
    assert_true(f"Sucesso: {success} ({pct(success, total)})" in rate_out, rate_out)
    assert_true(f"Falha: {failure} ({pct(failure, total)})" in rate_out, rate_out)
    if other:
        assert_true(f"Outros estados: {other} ({pct(other, total)})" in rate_out, rate_out)
    assert_dashboard_file("java_deploy_success_rate.html", ["Taxa de Sucesso e Falha em Deploys Java", "Distribuicao por Status"])

    build_out = run_agent("Quais os problemas mais recorrebtes que acontecem nas falhas de jobs de build?")
    assert_true("checks/jobs de build" in build_out.lower(), build_out)
    for bucket in build_top:
        fragment = f"{bucket['group']} ({bucket['count']})"
        assert_true(fragment in build_out, build_out)
    assert_dashboard_file("build_failures_recurrence.html", ["Falhas Recorrentes em Jobs de Build", "Top Falhas de Build"])

    executed_jobs_out = run_agent("Quais os jobs de workflows que executaram até hoje?")
    assert_true("jobs/checks que mais executaram" in executed_jobs_out.lower(), executed_jobs_out)
    for bucket in executed_jobs_top:
        fragment = f"{bucket['group']} ({bucket['count']})"
        assert_true(fragment in executed_jobs_out, executed_jobs_out)
    assert_dashboard_file("executed_jobs.html", ["Jobs de Workflows Executados", "Top Jobs Executados"])

    assert_dashboard_file("last_dashboard.html", ["Jobs de Workflows Executados"])

    print("OK: smoke tests do MVP passaram.")


if __name__ == "__main__":
    main()

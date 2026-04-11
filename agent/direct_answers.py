"""
Respostas diretas para perguntas recorrentes do MVP.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import re
import unicodedata

from renderer import print_tool_call
from semantic_rules import (
    extract_architecture_filter,
    extract_environment_semantics,
    extract_pipeline_type_patterns,
    extract_team_filter,
)


def _plain_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def _dig(data: dict, field: str | None):
    if not field:
        return None

    node = data
    for part in field.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _iter_dimension_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


async def _call_tool_json(mcp_session, name: str, args: dict, call_tool) -> dict:
    print_tool_call(name, args)
    raw = await call_tool(mcp_session, name, args)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": raw}


def _deploy_filter_value(field: str | None) -> str | None:
    if not field:
        return None
    if field == "deployment.task":
        return "deploy"
    return "*deploy*"


def _format_percent(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{(value / total) * 100:.2f}%"


def _wants_list_output(question: str) -> bool:
    q = _plain_text(question)
    return any(term in q for term in ["liste", "lista", "mostre", "informe"]) and not any(
        term in q for term in ["quantos", "quantas", "quantidade", "porcentagem", "taxa", "media", "tempo medio"]
    )


def _format_bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def _extract_team_from_repo_name(repo_name: str | None) -> str | None:
    if not repo_name:
        return None
    repo_slug = str(repo_name).split("/", 1)[-1]
    parts = [part for part in repo_slug.split("-") if part]
    if not parts:
        return None
    return parts[0].lower()


def _extract_architectures_from_topics(value) -> list[str]:
    architectures = []
    for topic in _iter_dimension_values(value):
        normalized = _plain_text(topic)
        for prefix in ("archtecture-", "architecture-"):
            if normalized.startswith(prefix):
                architectures.append(normalized[len(prefix):])
                break
    deduped = []
    seen = set()
    for architecture in architectures:
        if architecture and architecture not in seen:
            seen.add(architecture)
            deduped.append(architecture)
    return deduped


def _emoji(kind: str) -> str:
    return {
        "summary": "📊",
        "success": "✅",
        "failure": "❌",
        "duration": "⏱️",
        "deploy": "🚀",
        "people": "👤",
        "warning": "🟡",
        "workflow": "🧭",
    }.get(kind, "📌")


def _success_failure_sets() -> tuple[set[str], set[str]]:
    success_values = {"success", "completed"}
    failure_values = {"failure", "failed", "error", "timed_out", "cancelled", "canceled"}
    return success_values, failure_values


def _status_counts_from_docs(
    docs: list[dict],
    *,
    status_field: str,
    unique_field: str | None = None,
) -> tuple[int, int, int]:
    success_values, failure_values = _success_failure_sets()
    seen = set()
    success = 0
    failure = 0
    other = 0

    for doc in docs:
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        if unique_value:
            if unique_value in seen:
                continue
            seen.add(unique_value)
        status = str(_dig(doc, status_field) or "").lower()
        if status in success_values:
            success += 1
        elif status in failure_values:
            failure += 1
        else:
            other += 1
    return success, failure, other


async def try_direct_answer(question: str, schema: dict, mcp_session, call_tool, config: dict | None = None) -> dict | None:
    profile = schema.get("profile", {})
    config = config or {}
    compound_parts = _split_compound_question(question)
    if len(compound_parts) > 1:
        answers = []
        for part in compound_parts:
            result = await try_direct_answer(part, schema, mcp_session, call_tool, config=config)
            if not result:
                return None
            answers.append(result["answer"])
        return {"answer": "\n\n".join(answers), "dashboard": None}

    q = _plain_text(question)

    latest_workflow = _is_latest_workflow_question(q)
    first_workflow = _is_first_workflow_question(q)
    deploys_last_day = "deploy" in q and "ultimo dia" in q
    deploy_rate_java = "deploy" in q and "java" in q and (("taxa" in q or "taza" in q) or ("sucesso" in q and "falha" in q))
    build_failures = "build" in q and ("falha" in q or "problema" in q) and ("recorr" in q or "recurrent" in q)
    least_executed_workflow = _is_least_executed_workflow_question(q)
    most_executed_workflow = _is_most_executed_workflow_question(q)
    executed_jobs = _is_executed_jobs_question(q)
    executed_workflows = _is_executed_workflows_question(q)
    job_longest_duration = _is_job_longest_duration_question(q)
    average_java_workflow_duration = _is_average_java_workflow_duration_question(q)
    workflows_fail_prd = _is_workflows_most_fail_prd_question(q)
    workflows_best_success_prd = _is_workflows_best_success_prd_question(q)
    fastest_workflows_by_repo = _is_fastest_workflows_by_repo_question(q)
    analysts_ran_workflows = _is_analysts_ran_workflows_question(q)
    analyst_most_executions = _is_top_analyst_by_executions_question(q)
    status_mix_question = _is_status_mix_question(q)
    worst_step_question = _is_worst_step_question(q)
    waiting_jobs_question = _is_waiting_jobs_question(q)
    env_duration_compare_question = _is_environment_duration_compare_question(q)
    lead_time_question = _is_lead_time_question(q)
    request_to_delivery_question = _is_request_to_first_delivery_question(q)
    enablement_to_delivery_question = _is_enablement_to_first_delivery_question(q)
    workflow_creation_to_deploy_question = _is_workflow_creation_to_first_deploy_question(q)
    rollback_average_question = _is_average_rollback_duration_question(q)
    rollback_inventory_question = _is_rollback_inventory_question(q)
    rollback_multiple_question = _is_multiple_rollback_question(q)
    deploy_frequency_question = _is_deploy_frequency_question(q)
    first_dev_to_prd_question = _is_first_dev_to_prd_gap_question(q)
    dev_before_promotion_question = _is_dev_deploys_before_promotion_question(q)
    teams_for_architecture_question = _is_teams_for_architecture_question(q)
    analyst_emails_by_architecture_question = _is_analyst_emails_by_architecture_question(q)
    last_prd_deploy_email_question = _is_last_prd_deploy_actor_email_question(q)
    analysts_working_on_workflow_question = _is_analysts_working_on_workflow_question(q)
    available_workflows = _is_available_workflows_question(q)
    repository_count = _is_repository_count_question(q)
    analyst_lowest_success = _is_analyst_lowest_success_question(q)
    analyst_highest_success = _is_analyst_highest_success_question(q)
    average_build_job_duration = _is_average_build_job_duration_by_workflow_question(q)
    average_deploy_job_executions = _is_average_deploy_job_executions_by_workflow_question(q)
    latest_failed_projects_list = _is_recent_failure_listing_question(q)
    latest_deploys_list = _is_recent_deploy_listing_question(q)
    team_repo_failure_combo = _is_team_repository_failure_combo_question(q)

    if latest_workflow:
        result = await _answer_workflow_edge(
            profile=profile,
            question=question,
            config=config,
            mcp_session=mcp_session,
            call_tool=call_tool,
            order="desc",
        )
        if result:
            return result

    if latest_failed_projects_list:
        result = await _answer_recent_failure_listing(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if latest_deploys_list:
        result = await _answer_recent_deploy_listing(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if team_repo_failure_combo:
        result = await _answer_team_repository_failure_combo(
            question=question,
            config=config,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if first_workflow:
        result = await _answer_workflow_edge(
            profile=profile,
            question=question,
            config=config,
            mcp_session=mcp_session,
            call_tool=call_tool,
            order="asc",
        )
        if result:
            return result

    if analyst_most_executions:
        result = await _answer_top_analyst_by_executions(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if status_mix_question:
        result = await _answer_status_mix(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if worst_step_question:
        result = await _answer_worst_step_failure_rate(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if waiting_jobs_question:
        result = await _answer_waiting_jobs(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if env_duration_compare_question:
        result = await _answer_environment_duration_compare(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if lead_time_question:
        result = await _answer_lead_time_to_deploy(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if request_to_delivery_question:
        result = await _answer_anchor_to_first_delivery(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            anchor_kind="repository_request",
        )
        if result:
            return result

    if enablement_to_delivery_question:
        result = await _answer_anchor_to_first_delivery(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            anchor_kind="pipeline_request",
        )
        if result:
            return result

    if workflow_creation_to_deploy_question:
        result = await _answer_anchor_to_first_delivery(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            anchor_kind="workflow_created",
        )
        if result:
            return result

    if rollback_average_question:
        result = await _answer_average_rollback_duration(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if rollback_inventory_question:
        result = await _answer_recent_rollback_listing(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if rollback_multiple_question:
        result = await _answer_multiple_rollbacks(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if deploy_frequency_question:
        result = await _answer_deploy_frequency(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if first_dev_to_prd_question:
        result = await _answer_first_dev_to_prd_gap(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if dev_before_promotion_question:
        result = await _answer_dev_deploys_before_promotion(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if teams_for_architecture_question:
        result = await _answer_team_count_for_architecture(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if analyst_emails_by_architecture_question:
        result = await _answer_analyst_emails_by_architecture(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if last_prd_deploy_email_question:
        result = await _answer_last_prd_deploy_actor_email(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if analysts_working_on_workflow_question:
        result = await _answer_analysts_working_on_workflow(
            question=question,
            config=config,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if latest_workflow:
        time_field = profile.get("primary_time_field") or "@timestamp"
        workflow_field = profile.get("workflow_name_field") or "workflow_run.name"
        repo_field = profile.get("repository_name_field") or "repository.full_name"
        status_field = profile.get("workflow_status_field") or "workflow_run.status"
        env_field = profile.get("environment_field")

        fields = [workflow_field, repo_field, status_field, time_field]
        if env_field:
            fields.append(env_field)

        result = await _call_tool_json(
            mcp_session,
            "search",
            {
                "time_range": "90d",
                "sort": f"{time_field}:desc",
                "limit": 1,
                "fields": fields,
            },
            call_tool,
        )
        documents = result.get("documents", [])
        if not documents:
            return {"answer": "Nao encontrei workflows no periodo consultado.", "dashboard": None}

        doc = documents[0]
        workflow_name = _dig(doc, workflow_field) or _dig(doc, "workflow.name") or _dig(doc, "workflow_run.name")
        repo_name = _dig(doc, repo_field) or _dig(doc, "repository.full_name") or _dig(doc, "repository.name")
        status = _dig(doc, status_field)
        when = _dig(doc, time_field)
        env = _dig(doc, env_field)

        extra = f" no ambiente {env}" if env else ""
        answer = f"O ultimo workflow encontrado foi `{workflow_name}` no repositorio `{repo_name}`, com status `{status}`{extra}, em `{when}`."
        dashboard = {
            "id": "latest_workflow",
            "title": "Ultimo Workflow Executado",
            "cards": [
                {"label": "Workflow", "value": workflow_name or "-", "tone": "accent"},
                {"label": "Repositorio", "value": repo_name or "-", "tone": "accent"},
                {"label": "Status", "value": status or "-", "tone": _status_tone(status)},
                {"label": "Ambiente", "value": env or "n/a", "tone": "warning"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Detalhes da Execucao",
                    "items": [
                        {"key": "Timestamp", "value": when or "-"},
                        {"key": "Campo temporal", "value": time_field},
                        {"key": "Campo de workflow", "value": workflow_field},
                        {"key": "Campo de status", "value": status_field},
                    ],
                }
            ],
        }
        return {"answer": answer, "dashboard": dashboard}

    if deploys_last_day:
        deploy_field = profile.get("deploy_indicator_field")
        deploy_value = _deploy_filter_value(deploy_field)
        if not deploy_field or not deploy_value:
            return None

        result = await _call_tool_json(
            mcp_session,
            "aggregate",
            {
                "metric": "count",
                "field": deploy_field,
                "group_by": deploy_field,
                "time_range": "1d",
                "filters": {deploy_field: deploy_value},
            },
            call_tool,
        )
        buckets = result.get("result", [])
        total = sum(bucket.get("count", 0) for bucket in buckets)
        env_series = []
        env_field = profile.get("environment_field")
        if env_field:
            env_result = await _call_tool_json(
                mcp_session,
                "aggregate",
                {
                    "metric": "count",
                    "field": env_field,
                    "group_by": env_field,
                    "time_range": "1d",
                    "filters": {deploy_field: deploy_value},
                },
                call_tool,
            )
            env_series = [
                {"label": str(bucket.get("group")), "value": bucket.get("count", 0), "display_value": str(bucket.get("count", 0))}
                for bucket in env_result.get("result", [])
            ]

        if total == 0:
            return {
                "answer": "Nenhum deploy ocorreu no ultimo dia.",
                "dashboard": {
                    "id": "deploys_last_day",
                    "title": "Deploys no Ultimo Dia",
                    "cards": [
                        {"label": "Deploys", "value": "0", "tone": "warning"},
                        {"label": "Periodo", "value": "1d", "tone": "accent"},
                    ],
                    "sections": [
                        {"type": "text", "title": "Resumo", "text": "Nenhum deploy foi encontrado no periodo consultado."}
                    ],
                },
            }

        answer = f"Foram encontrados {total} deploys no ultimo dia."
        dashboard = {
            "id": "deploys_last_day",
            "title": "Deploys no Ultimo Dia",
            "cards": [
                {"label": "Deploys", "value": str(total), "tone": "accent"},
                {"label": "Periodo", "value": "1d", "tone": "accent"},
                {"label": "Campo de deploy", "value": deploy_field, "tone": "accent"},
            ],
            "sections": [],
        }
        if env_series:
            dashboard["sections"].append(
                {"type": "bar", "title": "Distribuicao por Ambiente", "series": env_series}
            )
        return {"answer": answer, "dashboard": dashboard}

    if deploy_rate_java:
        status_field = "deployment_status.state" if "deployment_status.state" in profile.get("candidate_status_fields", []) else profile.get("workflow_status_field")
        deploy_field = profile.get("deploy_indicator_field")
        language_field = profile.get("repository_language_field")
        deploy_value = _deploy_filter_value(deploy_field)
        if not status_field or not deploy_field or not language_field or not deploy_value:
            return None

        result = await _call_tool_json(
            mcp_session,
            "aggregate",
            {
                "metric": "count",
                "field": status_field,
                "group_by": status_field,
                "time_range": "30d",
                "filters": {
                    deploy_field: deploy_value,
                    language_field: "java",
                },
            },
            call_tool,
        )
        buckets = result.get("result", [])
        total = sum(bucket.get("count", 0) for bucket in buckets)
        if total == 0:
            return {
                "answer": "Nao encontrei deploys Java no periodo consultado.",
                "dashboard": {
                    "id": "java_deploy_success_rate",
                    "title": "Taxa de Deploys Java",
                    "cards": [
                        {"label": "Deploys Java", "value": "0", "tone": "warning"},
                        {"label": "Periodo", "value": "30d", "tone": "accent"},
                    ],
                    "sections": [
                        {"type": "text", "title": "Resumo", "text": "Nenhum deploy Java foi encontrado no periodo consultado."}
                    ],
                },
            }

        success_values = {"success", "completed"}
        failure_values = {"failure", "failed", "error", "timed_out"}
        success = sum(bucket.get("count", 0) for bucket in buckets if str(bucket.get("group")).lower() in success_values)
        failure = sum(bucket.get("count", 0) for bucket in buckets if str(bucket.get("group")).lower() in failure_values)
        other = total - success - failure

        pieces = [
            f"Sucesso: {success} ({_format_percent(success, total)})",
            f"Falha: {failure} ({_format_percent(failure, total)})",
        ]
        if other:
            pieces.append(f"Outros estados: {other} ({_format_percent(other, total)})")

        answer = "Taxa dos deploys Java nos ultimos 30 dias: " + " | ".join(pieces) + "."
        dashboard = {
            "id": "java_deploy_success_rate",
            "title": "Taxa de Sucesso e Falha em Deploys Java",
            "cards": [
                {"label": "Total de Deploys", "value": str(total), "tone": "accent"},
                {"label": "Sucesso", "value": str(success), "note": _format_percent(success, total), "tone": "success"},
                {"label": "Falha", "value": str(failure), "note": _format_percent(failure, total), "tone": "danger"},
                {"label": "Outros", "value": str(other), "note": _format_percent(other, total), "tone": "warning"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Distribuicao por Status",
                    "series": [
                        {
                            "label": str(bucket.get("group")),
                            "value": bucket.get("count", 0),
                            "display_value": f"{bucket.get('count', 0)} ({_format_percent(bucket.get('count', 0), total)})",
                        }
                        for bucket in buckets
                    ],
                }
            ],
        }
        return {"answer": answer, "dashboard": dashboard}

    if build_failures:
        job_field = profile.get("job_name_field")
        job_status_field = profile.get("job_status_field") or profile.get("workflow_status_field")
        if not job_field or not job_status_field:
            return None

        result = await _call_tool_json(
            mcp_session,
            "aggregate",
            {
                "metric": "count",
                "field": job_field,
                "group_by": job_field,
                "time_range": "90d",
                "filters": {
                    job_status_field: ["failure", "failed", "error", "timed_out"],
                    job_field: ["*build*", "*compile*"],
                },
            },
            call_tool,
        )
        buckets = result.get("result", [])
        if not buckets:
            return {
                "answer": "Nao encontrei falhas recorrentes de jobs/checks de build nos ultimos 90 dias.",
                "dashboard": {
                    "id": "build_failures_recurrence",
                    "title": "Falhas Recorrentes de Build",
                    "cards": [
                        {"label": "Ocorrencias", "value": "0", "tone": "warning"},
                        {"label": "Periodo", "value": "90d", "tone": "accent"},
                    ],
                    "sections": [
                        {"type": "text", "title": "Resumo", "text": "Nenhum job/check de build com falha recorrente foi encontrado no periodo."}
                    ],
                },
            }

        top = buckets[:5]
        summary = ", ".join(f"{bucket['group']} ({bucket['count']})" for bucket in top)
        answer = f"Nos ultimos 90 dias, os checks/jobs de build com mais falhas foram: {summary}."
        dashboard = {
            "id": "build_failures_recurrence",
            "title": "Falhas Recorrentes em Jobs de Build",
            "cards": [
                {"label": "Periodo", "value": "90d", "tone": "accent"},
                {"label": "Itens no Top 5", "value": str(len(top)), "tone": "accent"},
                {"label": "Campo de job/check", "value": job_field, "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Top Falhas de Build",
                    "series": [
                        {
                            "label": str(bucket.get("group")),
                            "value": bucket.get("count", 0),
                            "display_value": str(bucket.get("count", 0)),
                        }
                        for bucket in top
                    ],
                }
            ],
        }
        return {"answer": answer, "dashboard": dashboard}

    if least_executed_workflow:
        result = await _answer_workflow_execution_extreme(
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=_wide_time_range(question, schema),
            pick="least",
        )
        if result:
            return result

    if most_executed_workflow:
        result = await _answer_workflow_execution_extreme(
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=_wide_time_range(question, schema),
            pick="most",
        )
        if result:
            return result

    if job_longest_duration:
        result = await _answer_duration_by_dimension(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            dimension_field=profile.get("job_name_field"),
            start_field=profile.get("job_start_field"),
            end_field=profile.get("job_end_field"),
            unique_field=profile.get("job_execution_id_field"),
            title="Jobs com Maior Duracao Media",
            intro="O job/check com maior duracao media foi",
            sort_desc=True,
            extra_fields=[profile.get("workflow_name_field"), profile.get("repository_name_field")],
        )
        if result:
            return result

    if average_java_workflow_duration:
        result = await _answer_average_duration(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            start_field=profile.get("workflow_start_field"),
            end_field=profile.get("workflow_end_field"),
            unique_field=profile.get("workflow_execution_id_field"),
            filters={profile.get("repository_language_field"): "java"} if profile.get("repository_language_field") else {},
            title="Media de Duracao de Workflows Java",
            answer_prefix="A media de duracao das execucoes de workflows Java no periodo consultado foi",
        )
        if result:
            return result

    if workflows_fail_prd:
        result = await _answer_status_ranking(
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            group_field=profile.get("workflow_name_field"),
            status_field=_best_status_field(profile),
            filters=_environment_filters(profile, "prd", include_failure=True),
            time_range="365d",
            title="Workflows que Mais Falham em PRD",
            answer_prefix="Os workflows que mais falharam em PRD foram",
        )
        if result:
            return result

    if workflows_best_success_prd:
        result = await _answer_success_rate_by_dimension(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            dimension_field=profile.get("workflow_name_field"),
            title="Taxa de Sucesso por Workflow em PRD",
            answer_prefix="Os workflows com maior taxa de sucesso em PRD foram",
            filters=_environment_filters(profile, "prd"),
            time_range="365d",
            sort_desc=True,
            status_field="deployment_status.state",
            unique_field=profile.get("workflow_execution_id_field"),
        )
        if result:
            return result

    if fastest_workflows_by_repo:
        result = await _answer_fastest_workflows_by_repo(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if analysts_ran_workflows:
        result = await _answer_distinct_actors(
            question=question,
            config=config,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            title="Analistas com Execucao de Workflows",
            answer_prefix="Encontrei",
        )
        if result:
            return result

    if available_workflows:
        result = await _answer_available_workflows(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if repository_count:
        repo_field = profile.get("repository_name_field")
        if repo_field:
            result = await _call_tool_json(
                mcp_session,
                "aggregate",
                {
                    "metric": "cardinality",
                    "field": repo_field,
                    "time_range": "365d",
                },
                call_tool,
            )
            value = int(result.get("result") or 0)
            return {
                "answer": f"Encontrei `{value}` repositorios com execucoes de workflows no periodo consultado.",
                "dashboard": {
                    "id": "repository_count",
                    "title": "Repositorios com Execucao de Workflows",
                    "cards": [
                        {"label": "Repositorios", "value": str(value), "tone": "accent"},
                        {"label": "Periodo", "value": "365d", "tone": "accent"},
                    ],
                    "sections": [],
                },
            }

    if analyst_lowest_success:
        result = await _answer_success_rate_by_dimension(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            dimension_field=profile.get("actor_field"),
            title="Menor Taxa de Sucesso por Analista",
            answer_prefix="Os analistas com menor taxa de sucesso foram",
            filters={},
            time_range="365d",
            sort_desc=False,
            exclude_bots=True,
            status_field=profile.get("workflow_status_field"),
            unique_field=profile.get("workflow_execution_id_field"),
        )
        if result:
            return result

    if analyst_highest_success:
        result = await _answer_success_rate_by_dimension(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            dimension_field=profile.get("actor_field"),
            title="Maior Taxa de Sucesso por Analista",
            answer_prefix="Os analistas com maior taxa de sucesso foram",
            filters={},
            time_range="365d",
            sort_desc=True,
            exclude_bots=True,
            status_field=profile.get("workflow_status_field"),
            unique_field=profile.get("workflow_execution_id_field"),
        )
        if result:
            return result

    if average_build_job_duration:
        result = await _answer_duration_by_dimension(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            dimension_field=profile.get("workflow_name_field"),
            start_field=profile.get("job_start_field"),
            end_field=profile.get("job_end_field"),
            unique_field=profile.get("job_execution_id_field"),
            title="Media de Duracao de Jobs de Build por Workflow",
            intro="A media de duracao de jobs de build por workflow ficou assim",
            sort_desc=True,
            extra_filters={profile.get("job_name_field"): ["*build*", "*compile*"]} if profile.get("job_name_field") else {},
        )
        if result:
            return result

    if average_deploy_job_executions:
        result = await _answer_deploy_job_executions_by_workflow(
            question=question,
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
        )
        if result:
            return result

    if executed_jobs:
        job_field = profile.get("job_name_field")
        if not job_field:
            return None

        time_range = _wide_time_range(question, schema)
        result = await _call_tool_json(
            mcp_session,
            "aggregate",
            {
                "metric": "count",
                "field": job_field,
                "group_by": job_field,
                "time_range": time_range,
                "size": 10,
            },
            call_tool,
        )
        buckets = result.get("result", [])
        if not buckets:
            return {
                "answer": "Nao encontrei jobs/checks executados no periodo consultado.",
                "dashboard": {
                    "id": "executed_jobs",
                    "title": "Jobs Executados",
                    "cards": [
                        {"label": "Jobs Encontrados", "value": "0", "tone": "warning"},
                        {"label": "Periodo", "value": time_range, "tone": "accent"},
                    ],
                    "sections": [
                        {"type": "text", "title": "Resumo", "text": "Nenhum job/check foi encontrado no periodo consultado."}
                    ],
                },
            }

        total = sum(bucket.get("count", 0) for bucket in buckets)
        names = ", ".join(f"{bucket['group']} ({bucket['count']})" for bucket in buckets[:10])
        answer = (
            f"Os jobs/checks que mais executaram no periodo consultado foram: {names}. "
            f"Considerei o campo `{job_field}` em `{time_range}`."
        )
        dashboard = {
            "id": "executed_jobs",
            "title": "Jobs de Workflows Executados",
            "cards": [
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Campo de Job", "value": job_field, "tone": "accent"},
                {"label": "Total nos Top 10", "value": str(total), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Top Jobs Executados",
                    "series": [
                        {
                            "label": str(bucket.get("group")),
                            "value": bucket.get("count", 0),
                            "display_value": str(bucket.get("count", 0)),
                        }
                        for bucket in buckets[:10]
                    ],
                }
            ],
        }
        return {"answer": answer, "dashboard": dashboard}

    if executed_workflows:
        result = await _answer_workflow_execution_ranking(
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=_wide_time_range(question, schema),
        )
        if result:
            return result

    generic_result = await _answer_generic_business_question(
        question=question,
        config=config,
        profile=profile,
        schema=schema,
        mcp_session=mcp_session,
        call_tool=call_tool,
    )
    if generic_result:
        return generic_result

    if _looks_like_business_question(q):
        return _reformulate(
            "Nao consegui montar uma resposta util com seguranca para essa pergunta. "
            "Por favor, reformule informando melhor a metrica desejada, o periodo e se voce quer volume, taxa ou duracao."
        )

    return None


def _status_tone(status: str | None) -> str:
    normalized = str(status or "").lower()
    if normalized in {"success", "completed"}:
        return "success"
    if normalized in {"failure", "failed", "error", "timed_out"}:
        return "danger"
    return "warning"


def _wide_time_range(question: str, schema: dict) -> str:
    return _extract_time_range(question, default="90d")


def _extract_time_range(question: str, default: str = "90d") -> str:
    q = _plain_text(question)
    if "ultimo dia" in q or "utimo dia" in q or "ultimas 24h" in q or "ultimas 24 horas" in q:
        return "1d"
    if "ultima semana" in q or "ultma semana" in q:
        return "7d"
    if "ultimos 7 dias" in q or "ultimas 7 dias" in q:
        return "7d"
    if "ultimos 15 dias" in q:
        return "15d"
    if "ultimos 30 dias" in q or "ultimo mes" in q:
        return "30d"
    if "ultimos 60 dias" in q:
        return "60d"
    if "ultimos 90 dias" in q or "ultimo trimestre" in q:
        return "90d"
    if "ultimos 180 dias" in q or "ultimo semestre" in q:
        return "180d"
    if "ultimos 365 dias" in q or "ultimo ano" in q:
        return "365d"
    if "ate hoje" in q or "ate agora" in q or "historico" in q or "tudo" in q or "algum momento" in q or "ja executaram" in q:
        return "365d"
    return default


def _is_executed_jobs_question(q: str) -> bool:
    mentions_job = any(term in q for term in ["job", "jobs", "check", "checks"])
    asks_listing = any(term in q for term in ["quais", "lista", "lista os", "mostre"])
    asks_execution = any(term in q for term in ["execut", "rod", "rodaram", "rodou"])
    filters = ["build", "deploy", "rollback", "security", "scan", "java", "python", "typescript", "node", "prd", "hml", "stg", "dev", "sandbox", "topico", "branch", "privado", "publico", "falha", "falhas", "sucesso", "taxa", "duracao", "tempo", "time", "vskey", "api", "srv", "bff", "apim"]
    return mentions_job and asks_listing and asks_execution and not any(term in q for term in filters)


def _is_executed_workflows_question(q: str) -> bool:
    mentions_workflow = any(term in q for term in ["workflow", "workflows"])
    asks_listing = any(term in q for term in ["quais", "lista", "lista os", "mostre"])
    asks_execution = any(term in q for term in ["execut", "rod", "rodaram", "rodou"])
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "node", "prd", "hml", "stg", "dev", "sandbox", "privado", "publico", "build", "deploy", "rollback", "security", "scan", "time", "vskey", "api", "srv", "bff", "apim"]
    return (
        mentions_workflow
        and asks_listing
        and asks_execution
        and not _is_executed_jobs_question(q)
        and not any(term in q for term in other_dimensions)
    )


def _is_latest_workflow_question(q: str) -> bool:
    return ("workflow" in q or "esteira" in q or "pipeline" in q) and any(
        pattern in q
        for pattern in [
            "ultimo workflow",
            "ultima execucao de workflow",
            "ultimo workflow que rodou",
            "workflow mais recente",
            "data de execucao do ultimo workflow",
        ]
    )


def _is_first_workflow_question(q: str) -> bool:
    return ("workflow" in q or "esteira" in q or "pipeline" in q) and any(
        pattern in q
        for pattern in [
            "primeiro workflow",
            "primeira execucao de workflow",
            "primeiro workflow a rodar",
            "primeiro workflow que rodou",
            "primeira esteira a rodar",
        ]
    )


def _is_least_executed_workflow_question(q: str) -> bool:
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "prd", "hml", "stg", "privado", "publico", "build", "deploy", "security", "scan", "api", "srv", "bff", "time", "vskey"]
    return (
        q.startswith("qual")
        and "workflow" in q
        and not any(term in q for term in other_dimensions)
        and any(term in q for term in ["menos execut", "menor execu", "menos rod", "menos ocorreu", "menos teve execu"])
    )


def _is_most_executed_workflow_question(q: str) -> bool:
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "prd", "hml", "stg", "privado", "publico", "build", "deploy", "security", "scan", "api", "srv", "bff", "time", "vskey"]
    return (
        q.startswith("qual")
        and "workflow" in q
        and not any(term in q for term in other_dimensions)
        and any(term in q for term in ["mais execut", "maior execu", "mais rod", "mais ocorreu", "mais teve execu"])
    )


def _is_job_longest_duration_question(q: str) -> bool:
    return any(term in q for term in ["job", "jobs", "check", "checks"]) and any(term in q for term in ["mais demora", "maior duracao", "mais lento", "demora mais"])


def _is_average_java_workflow_duration_question(q: str) -> bool:
    return "workflow" in q and "java" in q and any(term in q for term in ["media de execu", "media de dur", "duracao media"])


def _is_workflows_most_fail_prd_question(q: str) -> bool:
    return "workflow" in q and any(term in q for term in ["mais falh", "mais falham"]) and any(term in q for term in ["prd", "produc"])


def _is_workflows_best_success_prd_question(q: str) -> bool:
    return "workflow" in q and any(term in q for term in ["maior taxa de sucesso", "mais sucesso", "melhor taxa de sucesso"]) and any(term in q for term in ["prd", "produc"])


def _is_fastest_workflows_by_repo_question(q: str) -> bool:
    return "workflow" in q and any(term in q for term in ["mais rapidos", "mais rapidos", "mais rapido", "mais rápidos", "mais rápido"]) and any(term in q for term in ["repositorio", "repositorios", "repo", "repos"])


def _is_analysts_ran_workflows_question(q: str) -> bool:
    return any(term in q for term in ["analista", "analistas"]) and "workflow" in q and any(term in q for term in ["quantos", "quantas"]) and any(term in q for term in ["rodaram", "rodou", "execut", "executaram"])


def _is_top_analyst_by_executions_question(q: str) -> bool:
    return (
        any(term in q for term in ["analista", "analistas"])
        and "workflow" in q
        and any(term in q for term in ["mais execut", "mais rod", "maior volume"])
    )


def _is_status_mix_question(q: str) -> bool:
    return any(term in q for term in ["porcentagem", "percentual", "taxa geral"]) and "sucesso" in q and "falha" in q


def _is_worst_step_question(q: str) -> bool:
    return any(term in q for term in ["step", "job", "etapa"]) and any(term in q for term in ["maior porcentagem de falha", "maior taxa de falha"])


def _is_waiting_jobs_question(q: str) -> bool:
    return any(term in q for term in ["job", "jobs", "step", "steps"]) and any(term in q for term in ["waiting", "wating", "aguardando aprovacao", "aguardando aprovação"])


def _is_environment_duration_compare_question(q: str) -> bool:
    return any(term in q for term in ["tempo medio", "tempo medio de execucao", "tempo medio de execução"]) and any(term in q for term in ["hom", "hml"]) and any(term in q for term in ["prd", "prod", "producao", "produção"])


def _is_lead_time_question(q: str) -> bool:
    return "gatilho" in q and "deploy" in q and any(term in q for term in ["tempo medio", "tempo medio", "tempo médio"])


def _is_request_to_first_delivery_question(q: str) -> bool:
    return any(term in q for term in ["chamado", "criacao do repositorio", "criação do repositorio", "abertura do chamado"]) and any(
        term in q for term in ["primeira entrega", "primeiro deploy", "entrega em", "deploy em"]
    )


def _is_enablement_to_first_delivery_question(q: str) -> bool:
    return any(term in q for term in ["habilitacao da esteira", "habilitação da esteira", "solicitacao da esteira", "solicitação da esteira"]) and any(
        term in q for term in ["primeira entrega", "primeiro deploy", "entrega em", "deploy em"]
    )


def _is_workflow_creation_to_first_deploy_question(q: str) -> bool:
    return any(term in q for term in ["criacao da esteira", "criação da esteira"]) and any(
        term in q for term in ["primeiro deploy", "primeira entrega"]
    )


def _is_average_rollback_duration_question(q: str) -> bool:
    return "rollback" in q and any(
        term in q for term in ["tempo medio", "tempo medio de execu", "duracao media", "duração média", "execucao media", "execução média"]
    )


def _is_rollback_inventory_question(q: str) -> bool:
    if any(term in q for term in ["job", "jobs", "check", "checks", "step", "steps"]):
        return False
    if any(term in q for term in ["mais execut", "menos execut", "maior taxa", "menor taxa", "mais falh", "taxa de sucesso"]):
        return False
    return "rollback" in q and any(term in q for term in ["quais", "liste", "lista", "mostre", "informe"]) and any(
        term in q for term in ["realizaram", "executaram", "ocorreram", "tiveram"]
    ) and not _is_multiple_rollback_question(q)


def _is_multiple_rollback_question(q: str) -> bool:
    return "rollback" in q and any(term in q for term in ["mais de um", "mais de 1", "mais de uma vez", "mais de um rollback"])


def _is_deploy_frequency_question(q: str) -> bool:
    return "deploy" in q and any(term in q for term in ["frequencia", "frequência", "cadencia", "cadência", "com que frequencia", "com que frequência"])


def _is_first_dev_to_prd_gap_question(q: str) -> bool:
    return any(term in q for term in ["primeiro deploy em dev", "primeiro deploy em sandbox"]) and "prd" in q and any(
        term in q for term in ["em media", "em média", "quanto tempo"]
    )


def _is_dev_deploys_before_promotion_question(q: str) -> bool:
    return "deploys em dev" in q and any(term in q for term in ["hom", "hml", "prd"]) and any(
        term in q for term in ["em media quantos", "em média quantos", "quantos deploys"]
    )


def _is_teams_for_architecture_question(q: str) -> bool:
    return any(term in q for term in ["quantos times", "quantos squads", "quantos vskeys"]) and any(
        term in q for term in ["arquitetura", "architecture"]
    )


def _is_analyst_emails_by_architecture_question(q: str) -> bool:
    return any(term in q for term in ["email", "e-mail"]) and "analista" in q and any(
        term in q for term in ["arquitetura", "architecture"]
    )


def _is_last_prd_deploy_actor_email_question(q: str) -> bool:
    return any(term in q for term in ["email", "e-mail"]) and "ultimo deploy" in q and "prd" in q and any(
        term in q for term in ["esteira", "workflow", "pipeline"]
    )


def _is_analysts_working_on_workflow_question(q: str) -> bool:
    return any(term in q for term in ["quais os analistas", "quais analistas", "quem sao os analistas", "quem são os analistas"]) and any(
        term in q for term in ["trabalhando na esteira", "trabalhando no workflow", "atuando na esteira", "atuando no workflow"]
    )


def _is_available_workflows_question(q: str) -> bool:
    filters = ["java", "python", "typescript", "prd", "hml", "stg", "topico", "branch", "privado", "publico", "build", "deploy", "security", "scan"]
    return (
        "workflow" in q
        and any(term in q for term in ["temos disponivel", "temos disponiveis", "temos ate agora", "disponivel no ambiente", "disponiveis no ambiente"])
        and not any(term in q for term in filters)
    )


def _is_repository_count_question(q: str) -> bool:
    filters = ["java", "python", "typescript", "prd", "hml", "stg", "topico", "branch", "privado", "publico", "build", "deploy", "security", "scan"]
    return (
        any(term in q for term in ["quantos repositorios", "quantos repositorios temos", "quantos repos"])
        and "workflow" in q
        and not any(term in q for term in filters)
    )


def _is_recent_failure_listing_question(q: str) -> bool:
    return _wants_list_output(q) and any(term in q for term in ["falharam", "falha", "falhou"]) and any(
        term in q for term in ["repositorio", "repositorios", "repo", "repos", "projetos", "projeto"]
    )


def _is_recent_deploy_listing_question(q: str) -> bool:
    return any(term in q for term in ["ultimos deploys", "quais os ultimos deploys", "quais sao os ultimos deploys", "ultimos projetos que tiveram deploy", "ultimos projetos com deploy"])


def _is_team_repository_failure_combo_question(q: str) -> bool:
    return any(term in q for term in ["time", "times"]) and any(term in q for term in ["repositorio", "repositorios"]) and any(
        term in q for term in ["falharam", "falha", "mais falharam", "mais falhou"]
    )


def _is_analyst_lowest_success_question(q: str) -> bool:
    return any(term in q for term in ["analista", "analistas"]) and any(term in q for term in ["menor taxa de sucesso", "menor sucesso"])


def _is_analyst_highest_success_question(q: str) -> bool:
    return any(term in q for term in ["analista", "analistas"]) and any(term in q for term in ["maior sucesso", "maior taxa de sucesso", "melhor taxa de sucesso"])


def _is_average_build_job_duration_by_workflow_question(q: str) -> bool:
    return "build" in q and "workflow" in q and any(term in q for term in ["media de execu", "media de dur", "duracao media"])


def _is_average_deploy_job_executions_by_workflow_question(q: str) -> bool:
    return "deploy" in q and "workflow" in q and any(term in q for term in ["media de execucoes", "media de execucao", "media por jobs"])


def _looks_like_business_question(q: str) -> bool:
    business_terms = [
        "workflow", "workflows", "job", "jobs", "check", "checks", "deploy", "deploys",
        "repositorio", "repositorios", "repo", "analista", "analistas", "sucesso", "falha",
        "duracao", "media", "taxa", "prd", "hom", "dev", "sandbox",
    ]
    return any(term in q for term in business_terms)


def _split_compound_question(question: str) -> list[str]:
    parts = [part.strip(" .") for part in re.split(r"\?\s*", question) if part.strip(" .")]
    return parts


def _infer_exact_environment_value(question: str) -> str | None:
    q = _plain_text(question)
    if any(term in q for term in ["prd", "prod", "producao", "produção"]):
        return "PRD"
    if any(term in q for term in ["hml", "hom", "homolog"]):
        return "HML"
    if any(term in q for term in ["stg", "staging"]):
        return "STG"
    if any(term in q for term in ["dev", "sandbox"]):
        return "DEV"
    return None


def _env_matches_doc(doc: dict, env: str) -> bool:
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
    exact_raw = str(_dig(doc, "deployment.environment") or _dig(doc, "deployment_status.environment") or "")
    if exact_raw:
        return exact_raw.upper() in exact_map.get(env, set())
    branch = str(_dig(doc, "workflow_run.head_branch") or "").lower()
    workflow_name = str(_dig(doc, "workflow_run.name") or "").lower()
    job_name = str(_dig(doc, "check_run.name") or "").lower()
    haystack = " ".join([exact_raw.lower(), branch, workflow_name, job_name])
    return any(token in haystack for token in token_map.get(env, []))


def _reformulate(message: str) -> dict:
    return {"answer": message, "dashboard": None}


def _best_status_field(profile: dict) -> str | None:
    if "deployment_status.state" in profile.get("candidate_status_fields", []):
        return "deployment_status.state"
    return profile.get("workflow_status_field")


def _environment_filters(profile: dict, env_code: str, include_failure: bool = False) -> dict:
    filters = {}
    env_field = profile.get("environment_field")
    if env_field:
        filters[env_field] = env_code.upper()
    if include_failure:
        status_field = _best_status_field(profile)
        if status_field:
            filters[status_field] = ["failure", "failed", "error", "timed_out"]
    return filters


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _duration_seconds(doc: dict, start_field: str | None, end_field: str | None) -> float | None:
    start = _parse_iso(_dig(doc, start_field))
    end = _parse_iso(_dig(doc, end_field))
    if not start or not end:
        return None
    duration = (end - start).total_seconds()
    if duration <= 0:
        return None
    return duration


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} min"
    return f"{minutes / 60:.1f} h"


def _time_range_days(time_range: str) -> int:
    try:
        return max(1, int(str(time_range).rstrip("d")))
    except Exception:
        return 30


def _normalized_phrase(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", _plain_text(value)).strip()


def _match_named_candidate(question: str, candidates: list[str]) -> str | None:
    normalized_question = f" {_normalized_phrase(question)} "
    for candidate in sorted({item for item in candidates if item}, key=lambda item: len(_normalized_phrase(item)), reverse=True):
        variants = {candidate}
        if "/" in candidate:
            variants.add(candidate.split("/", 1)[1])
        for variant in variants:
            normalized_variant = _normalized_phrase(variant)
            if normalized_variant and f" {normalized_variant} " in normalized_question:
                return candidate
    return None


def _extract_explicit_datetime(question: str):
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})(?:[ t](\d{2}:\d{2}(?::\d{2})?))?", question)
    if iso_match:
        date_part = iso_match.group(1)
        time_part = iso_match.group(2) or "00:00:00"
        if len(time_part) == 5:
            time_part += ":00"
        return _parse_iso(f"{date_part}T{time_part}Z")

    br_match = re.search(r"(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?", question)
    if br_match:
        date_part = br_match.group(1)
        time_part = br_match.group(2) or "00:00:00"
        if len(time_part) == 5:
            time_part += ":00"
        try:
            day, month, year = date_part.split("/")
            return _parse_iso(f"{year}-{month}-{day}T{time_part}Z")
        except Exception:
            return None
    return None


def _extract_explicit_repo_reference(question: str) -> str | None:
    match = re.search(r"(?:repositorio|reposit[oó]rio|repo)\s+([a-z0-9_./-]+)", _plain_text(question))
    if not match:
        return None
    return match.group(1).strip()


def _extract_explicit_workflow_reference(question: str) -> str | None:
    match = re.search(r"(?:esteira|workflow|pipeline)\s+(.+?)(?:\s+e\s+o|\s+em\s+[A-Z]{2,4}|\?|$)", question, flags=re.IGNORECASE)
    if not match:
        return None
    candidate = match.group(1).strip(" .")
    if len(candidate) < 3:
        return None
    return candidate


async def _fetch_documents(
    mcp_session,
    call_tool,
    *,
    time_range: str,
    fields: list[str],
    filters: dict | None = None,
    any_filters: dict | None = None,
    sort: str | None = None,
    max_docs: int = 5000,
) -> list[dict]:
    documents = []
    next_page = None

    while len(documents) < max_docs:
        args = {
            "time_range": time_range,
            "fields": [field for field in fields if field],
            "limit": min(200, max_docs - len(documents)),
        }
        if filters:
            args["filters"] = filters
        if any_filters:
            args["any_filters"] = any_filters
        if sort:
            args["sort"] = sort
        if next_page:
            args["search_after"] = next_page

        result = await _call_tool_json(mcp_session, "search", args, call_tool)
        page_docs = result.get("documents", [])
        documents.extend(page_docs)
        next_page = result.get("next_page")
        if not page_docs or not next_page:
            break

    return documents


def _compute_unique_counts(
    docs: list[dict],
    *,
    group_field: str,
    unique_field: str | None = None,
    group_getter=None,
) -> list[dict]:
    counters = defaultdict(set) if unique_field else defaultdict(int)

    for doc in docs:
        group_values = group_getter(doc) if group_getter else _iter_dimension_values(_dig(doc, group_field))
        if not group_values:
            continue
        if unique_field:
            unique_value = _dig(doc, unique_field)
            if unique_value is None:
                continue
            for group_value in group_values:
                counters[str(group_value)].add(str(unique_value))
        else:
            for group_value in group_values:
                counters[str(group_value)] += 1

    rows = []
    for group_value, value in counters.items():
        count = len(value) if unique_field else int(value)
        rows.append({"group": str(group_value), "count": count})
    return rows


async def _answer_workflow_execution_ranking(
    *,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    execution_id_field = profile.get("workflow_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not workflow_field:
        return None

    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[workflow_field, execution_id_field, time_field],
        sort=f"{time_field}:desc" if time_field else None,
    )
    rows = _compute_unique_counts(docs, group_field=workflow_field, unique_field=execution_id_field)
    if not rows:
        return {
            "answer": "Nao encontrei workflows executados no periodo consultado.",
            "dashboard": {
                "id": "executed_workflows",
                "title": "Workflows Executados",
                "cards": [
                    {"label": "Workflows Encontrados", "value": "0", "tone": "warning"},
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                ],
                "sections": [
                    {"type": "text", "title": "Resumo", "text": "Nenhum workflow foi encontrado no periodo consultado."}
                ],
            },
        }

    rows.sort(key=lambda item: (-item["count"], item["group"]))
    top_rows = rows[:10]
    total = sum(item["count"] for item in top_rows)
    names = ", ".join(f"{item['group']} ({item['count']})" for item in top_rows)
    metric_label = "execucoes unicas" if execution_id_field else "eventos"
    answer = (
        f"Os workflows com mais {metric_label} no periodo consultado foram: {names}. "
        f"Considerei `{workflow_field}` agrupado por `{execution_id_field or workflow_field}` em `{time_range}`."
    )
    dashboard = {
        "id": "executed_workflows",
        "title": "Ranking de Execucoes de Workflows",
        "cards": [
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Campo de Workflow", "value": workflow_field, "tone": "accent"},
            {"label": "Chave da Execucao", "value": execution_id_field or "contagem de eventos", "tone": "accent"},
            {"label": "Total no Top 10", "value": str(total), "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Top Workflows Executados",
                "series": [
                    {
                        "label": item["group"],
                        "value": item["count"],
                        "display_value": str(item["count"]),
                    }
                    for item in top_rows
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_workflow_execution_extreme(
    *,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    pick: str,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    execution_id_field = profile.get("workflow_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not workflow_field:
        return None

    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[workflow_field, execution_id_field, time_field],
        sort=f"{time_field}:desc" if time_field else None,
    )
    rows = _compute_unique_counts(docs, group_field=workflow_field, unique_field=execution_id_field)
    if not rows:
        return _reformulate("Nao encontrei workflows suficientes para responder essa pergunta.")

    rows.sort(key=lambda item: (item["count"], item["group"]))
    chosen = rows[-1] if pick == "most" else rows[0]
    metric_label = "execucoes unicas" if execution_id_field else "eventos"
    adjective = "mais executou" if pick == "most" else "menos executou"
    title = "Workflow com Maior Volume de Execucao" if pick == "most" else "Workflow com Menor Volume de Execucao"
    dashboard_id = "most_executed_workflow" if pick == "most" else "least_executed_workflow"
    tone = "accent" if pick == "most" else "warning"
    answer = (
        f"{_emoji('workflow')} O workflow que {adjective} no periodo consultado foi `{chosen['group']}`, "
        f"com `{chosen['count']}` {metric_label} em `{time_range}`. "
        f"Considerei `{execution_id_field or workflow_field}` como chave de execucao."
    )
    dashboard = {
        "id": dashboard_id,
        "title": title,
        "cards": [
            {"label": "Workflow", "value": chosen["group"], "tone": tone},
            {"label": "Execucoes", "value": str(chosen["count"]), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Chave da Execucao", "value": execution_id_field or "contagem de eventos", "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Workflows Observados",
                "series": [
                    {
                        "label": item["group"],
                        "value": item["count"],
                        "display_value": str(item["count"]),
                    }
                    for item in rows[:10]
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_workflow_edge(
    *,
    profile: dict,
    question: str,
    config: dict,
    mcp_session,
    call_tool,
    order: str,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    repo_field = profile.get("repository_name_field")
    status_field = profile.get("workflow_status_field")
    env_field = profile.get("environment_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field") or "@timestamp"
    if not workflow_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    normalized_question = _plain_text(question)
    exact_env = _infer_exact_environment_value(question)
    if exact_env and env_field:
        filters, any_filters = _remove_environment_filters(filters, any_filters, profile)
        filters[env_field] = exact_env
        status_field = "deployment_status.state" if "deployment_status.state" in profile.get("candidate_status_fields", []) else status_field
    if any(term in normalized_question for term in ["falhou", "falha", "erro", "failure", "failed"]):
        if status_field:
            filters[status_field] = ["failure", "failed", "error", "timed_out"]
            filter_labels.append("status de falha")
    if "deploy" in normalized_question:
        deploy_field = profile.get("deploy_indicator_field")
        deploy_value = _deploy_filter_value(deploy_field)
        if deploy_field and deploy_value:
            filters[deploy_field] = deploy_value
            filter_labels.append("deploy")
    result = await _call_tool_json(
        mcp_session,
        "search",
        {
            "time_range": _extract_time_range(question, default="365d"),
            "sort": f"{time_field}:{order}",
            "limit": 1,
            "fields": [workflow_field, repo_field, status_field, env_field, time_field],
            "filters": filters,
            "any_filters": any_filters,
        },
        call_tool,
    )
    docs = result.get("documents", [])
    if not docs:
        return _reformulate("Nao encontrei workflow suficiente para responder essa pergunta.")
    doc = docs[0]
    workflow_name = _dig(doc, workflow_field)
    repo_name = _dig(doc, repo_field)
    status = _dig(doc, status_field)
    env = _dig(doc, env_field)
    when = _dig(doc, time_field)
    adjective = "primeiro" if order == "asc" else "ultimo"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('workflow')} O {adjective} workflow encontrado{context} foi `{workflow_name}` no repositorio `{repo_name}`, "
        f"com status `{status}`"
        + (f" no ambiente `{env}`" if env else "")
        + f", em `{when}`."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "first_workflow" if order == "asc" else "latest_workflow",
            "title": "Primeiro Workflow Executado" if order == "asc" else "Ultimo Workflow Executado",
            "cards": [
                {"label": "Workflow", "value": workflow_name or "-", "tone": "accent"},
                {"label": "Repositorio", "value": repo_name or "-", "tone": "accent"},
                {"label": "Status", "value": status or "-", "tone": _status_tone(status)},
                {"label": "Ambiente", "value": env or "n/a", "tone": "warning"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Detalhes",
                    "items": [
                        {"key": "Timestamp", "value": when or "-"},
                        {"key": "Ordenacao", "value": order},
                        {"key": "Filtro", "value": ", ".join(filter_labels) or "sem filtro"},
                    ],
                }
            ],
        },
    }


async def _answer_recent_failure_listing(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    repo_field = profile.get("repository_name_field")
    status_field = profile.get("workflow_status_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    env_field = profile.get("environment_field")
    if not repo_field or not workflow_field or not status_field or not time_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "repository")
    filters[status_field] = ["failure", "failed", "error", "timed_out", "cancelled", "canceled"]
    if "deploy" in _plain_text(question):
        status_field = _best_status_field(profile) or status_field
        filters.pop(profile.get("workflow_status_field"), None)
        deploy_field = profile.get("deploy_indicator_field")
        deploy_value = _deploy_filter_value(deploy_field)
        if deploy_field and deploy_value:
            filters[deploy_field] = deploy_value
            filter_labels.append("deploy")
        filters[status_field] = ["failure", "failed", "error", "timed_out", "cancelled", "canceled"]

    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="30d"),
        fields=[repo_field, workflow_field, status_field, time_field, env_field, profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc",
        max_docs=50,
    )
    items = []
    seen = set()
    for doc in docs:
        unique_value = _dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field)
        dedupe_key = str(unique_value)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        repo = _dig(doc, repo_field) or "-"
        workflow = _dig(doc, workflow_field) or "-"
        when = _dig(doc, time_field) or "-"
        env = _dig(doc, env_field)
        status = _dig(doc, status_field) or "-"
        extra = f" | ambiente `{env}`" if env else ""
        items.append(f"`{repo}` | workflow `{workflow}` | data `{when}` | status `{status}`{extra}")
        if len(items) == 8:
            break
    if not items:
        return None

    return {
        "answer": (
            f"{_emoji('failure')} Lista dos ultimos registros com falha no periodo `{_extract_time_range(question, default='30d')}`:\n"
            + _format_bullet_list(items)
        ),
        "dashboard": {
            "id": slugify_local(f"recent failures {question}"),
            "title": "Ultimas Falhas Observadas",
            "cards": [
                {"label": "Ocorrencias", "value": str(len(items)), "tone": "danger"},
                {"label": "Periodo", "value": _extract_time_range(question, default='30d'), "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "falhas", "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "table",
                    "title": "Falhas Recentes",
                    "columns": [
                        {"key": "repo", "label": "Repositorio"},
                        {"key": "workflow", "label": "Workflow"},
                        {"key": "when", "label": "Data"},
                        {"key": "status", "label": "Status"},
                        {"key": "env", "label": "Ambiente"},
                    ],
                    "rows": [
                        {
                            "repo": _dig(doc, repo_field) or "-",
                            "workflow": _dig(doc, workflow_field) or "-",
                            "when": _dig(doc, time_field) or "-",
                            "status": _dig(doc, status_field) or "-",
                            "env": _dig(doc, env_field) or "-",
                        }
                        for doc in docs[:8]
                    ],
                }
            ],
        },
    }


async def _answer_recent_deploy_listing(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    repo_field = profile.get("repository_name_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    env_field = profile.get("environment_field")
    status_field = _best_status_field(profile)
    deploy_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_field)
    if not all([workflow_field, repo_field, time_field, status_field, deploy_field, deploy_value]):
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    filters[deploy_field] = deploy_value
    filter_labels.append("deploy")

    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="30d"),
        fields=[repo_field, workflow_field, time_field, env_field, status_field, profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc",
        max_docs=40,
    )
    lines = []
    seen = set()
    for doc in docs:
        unique_value = _dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field)
        if str(unique_value) in seen:
            continue
        seen.add(str(unique_value))
        repo = _dig(doc, repo_field) or "-"
        workflow = _dig(doc, workflow_field) or "-"
        when = _dig(doc, time_field) or "-"
        env = _dig(doc, env_field) or "-"
        status = _dig(doc, status_field) or "-"
        lines.append(f"`{repo}` | workflow `{workflow}` | data `{when}` | ambiente `{env}` | status `{status}`")
        if len(lines) == 8:
            break
    if not lines:
        return None
    return {
        "answer": (
            f"{_emoji('deploy')} Lista dos ultimos deploys observados no periodo `{_extract_time_range(question, default='30d')}`:\n"
            + _format_bullet_list(lines)
        ),
        "dashboard": {
            "id": slugify_local(f"recent deploys {question}"),
            "title": "Ultimos Deploys Observados",
            "cards": [
                {"label": "Deploys", "value": str(len(lines)), "tone": "accent"},
                {"label": "Periodo", "value": _extract_time_range(question, default='30d'), "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "deploy", "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "table",
                    "title": "Deploys Recentes",
                    "columns": [
                        {"key": "repo", "label": "Repositorio"},
                        {"key": "workflow", "label": "Workflow"},
                        {"key": "when", "label": "Data"},
                        {"key": "env", "label": "Ambiente"},
                        {"key": "status", "label": "Status"},
                    ],
                    "rows": [
                        {
                            "repo": _dig(doc, repo_field) or "-",
                            "workflow": _dig(doc, workflow_field) or "-",
                            "when": _dig(doc, time_field) or "-",
                            "env": _dig(doc, env_field) or "-",
                            "status": _dig(doc, status_field) or "-",
                        }
                        for doc in docs[:8]
                    ],
                }
            ],
        },
    }


async def _answer_team_repository_failure_combo(
    *,
    question: str,
    config: dict,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    team_question = re.sub(r"repositorios?", "times", question, flags=re.IGNORECASE)
    repo_question = re.sub(r"times?", "repositorios", question, flags=re.IGNORECASE)

    team_result = await _answer_generic_business_question(
        question=team_question,
        config=config,
        profile=profile,
        schema=schema,
        mcp_session=mcp_session,
        call_tool=call_tool,
    )
    repo_result = await _answer_generic_business_question(
        question=repo_question,
        config=config,
        profile=profile,
        schema=schema,
        mcp_session=mcp_session,
        call_tool=call_tool,
    )
    if not team_result or not repo_result:
        return None
    return {
        "answer": f"{team_result['answer']}\n\n{repo_result['answer']}",
        "dashboard": team_result.get("dashboard"),
    }


async def _answer_top_analyst_by_executions(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    actor_field = profile.get("actor_field")
    actor_type_field = profile.get("actor_type_field")
    workflow_field = profile.get("workflow_name_field")
    execution_id_field = profile.get("workflow_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not actor_field or not workflow_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "actor")
    time_range = _extract_time_range(question, default="90d")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[actor_field, actor_type_field, workflow_field, execution_id_field, time_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    counters = defaultdict(set)
    workflows_by_actor = defaultdict(lambda: defaultdict(int))
    for doc in docs:
        actor = _dig(doc, actor_field)
        if not actor or _is_bot_doc(doc, actor_type_field, actor_field):
            continue
        execution_id = _dig(doc, execution_id_field) or _dig(doc, time_field)
        workflow = _dig(doc, workflow_field)
        if execution_id is None:
            continue
        counters[str(actor)].add(str(execution_id))
        if workflow:
            workflows_by_actor[str(actor)][str(workflow)] += 1
    if not counters:
        return _reformulate("Nao encontrei analistas suficientes para responder essa pergunta.")

    rows = [{"actor": actor, "count": len(execs)} for actor, execs in counters.items()]
    rows.sort(key=lambda row: (row["count"], row["actor"]), reverse=True)
    top = rows[0]
    top_workflow = "-"
    if workflows_by_actor[top["actor"]]:
        top_workflow = max(workflows_by_actor[top["actor"]].items(), key=lambda item: (item[1], item[0]))[0]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('people')} O analista que mais executou workflows{context} no periodo `{time_range}` foi `{top['actor']}`, "
        f"com `{top['count']}` execucoes. O workflow mais frequente dele foi `{top_workflow}`."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "top_analyst_by_executions",
            "title": "Analista com Maior Volume de Execucoes",
            "cards": [
                {"label": "Analista", "value": top["actor"], "tone": "accent"},
                {"label": "Execucoes", "value": str(top["count"]), "tone": "accent"},
                {"label": "Workflow mais frequente", "value": top_workflow, "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Top Analistas",
                    "series": [
                        {"label": row["actor"], "value": row["count"], "display_value": str(row["count"])}
                        for row in rows[:5]
                    ],
                }
            ],
        },
    }


async def _answer_status_mix(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    status_field = _best_status_field(profile)
    unique_field = profile.get("workflow_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not status_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    time_range = _extract_time_range(question, default="90d")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[status_field, unique_field, profile.get("workflow_name_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    success, failure, other = _status_counts_from_docs(docs, status_field=status_field, unique_field=unique_field)
    total = success + failure + other
    if total <= 0:
        return {
            "answer": (
                f"{_emoji('summary')} No periodo `{time_range}`"
                + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                + ", encontrei `0` execucoes unicas. "
                f"{_emoji('success')} Sucesso: `0` (0%). {_emoji('failure')} Falha: `0` (0%)."
            ),
            "dashboard": {
                "id": "status_mix",
                "title": "Distribuicao de Sucesso e Falha",
                "cards": [
                    {"label": "Execucoes", "value": "0", "tone": "warning"},
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                ],
                "sections": [],
            },
        }

    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('summary')} No periodo `{time_range}`{context}, encontrei `{total}` execucoes unicas. "
        f"{_emoji('success')} Sucesso: `{success}` ({_format_percent(success, total)}). "
        f"{_emoji('failure')} Falha: `{failure}` ({_format_percent(failure, total)})."
    )
    if other:
        answer += f" {_emoji('warning')} Outros estados: `{other}` ({_format_percent(other, total)})."

    series = [
        {"label": "Sucesso", "value": success, "display_value": f"{success} ({_format_percent(success, total)})"},
        {"label": "Falha", "value": failure, "display_value": f"{failure} ({_format_percent(failure, total)})"},
    ]
    if other:
        series.append({"label": "Outros", "value": other, "display_value": f"{other} ({_format_percent(other, total)})"})

    return {
        "answer": answer,
        "dashboard": {
            "id": "status_mix",
            "title": "Distribuicao de Sucesso e Falha",
            "cards": [
                {"label": "Execucoes", "value": str(total), "tone": "accent"},
                {"label": "Sucesso", "value": str(success), "note": _format_percent(success, total), "tone": "success"},
                {"label": "Falha", "value": str(failure), "note": _format_percent(failure, total), "tone": "danger"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
            ],
            "sections": [
                {"type": "bar", "title": "Distribuicao por Status", "series": series}
            ],
        },
    }


async def _answer_worst_step_failure_rate(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    job_field = profile.get("job_name_field")
    workflow_field = profile.get("workflow_name_field")
    status_field = profile.get("job_status_field") or profile.get("workflow_status_field")
    unique_field = profile.get("job_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not job_field or not workflow_field or not status_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "job")
    time_range = _extract_time_range(question, default="90d")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[job_field, workflow_field, status_field, unique_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )

    success_values, failure_values = _success_failure_sets()
    counters = defaultdict(lambda: {"total": 0, "failure": 0})
    seen = set()
    for doc in docs:
        workflow_name = _dig(doc, workflow_field)
        job_names = _iter_dimension_values(_dig(doc, job_field))
        status = str(_dig(doc, status_field) or "").lower()
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        for job_name in job_names:
            key = (str(job_name), str(workflow_name or "-"))
            if unique_value:
                dedupe_key = key + (unique_value,)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
            counters[key]["total"] += 1
            if status in failure_values:
                counters[key]["failure"] += 1
            elif status not in success_values:
                pass

    rows = []
    for (job_name, workflow_name), values in counters.items():
        total = values["total"]
        if total <= 0:
            continue
        rows.append(
            {
                "job": job_name,
                "workflow": workflow_name,
                "total": total,
                "failure": values["failure"],
                "failure_rate": values["failure"] / total,
            }
        )
    if not rows:
        return {
            "answer": f"{_emoji('warning')} Nao encontrei steps suficientes para calcular taxa de falha no periodo `{time_range}`.",
            "dashboard": {"id": "worst_step_failure_rate", "title": "Step com Maior Taxa de Falha", "cards": [], "sections": []},
        }

    stable_rows = [row for row in rows if row["total"] >= 3] or rows
    stable_rows.sort(key=lambda row: (row["failure_rate"], row["failure"], row["total"], row["job"]), reverse=True)
    top = stable_rows[:5]
    first = top[0]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('failure')} O step com maior porcentagem de falha{context} foi `{first['job']}` na esteira `{first['workflow']}`, "
        f"com `{first['failure']}` falhas em `{first['total']}` execucoes ({_format_percent(first['failure'], first['total'])})."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "worst_step_failure_rate",
            "title": "Step com Maior Taxa de Falha",
            "cards": [
                {"label": "Step", "value": first["job"], "tone": "danger"},
                {"label": "Esteira", "value": first["workflow"], "tone": "accent"},
                {"label": "Taxa de Falha", "value": _format_percent(first["failure"], first["total"]), "tone": "danger"},
                {"label": "Amostra", "value": str(first["total"]), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Top Steps por Taxa de Falha",
                    "series": [
                        {
                            "label": f"{row['job']} @ {row['workflow']}",
                            "value": round(row["failure_rate"] * 100, 2),
                            "display_value": f"{_format_percent(row['failure'], row['total'])} ({row['total']} execs)",
                        }
                        for row in top
                    ],
                }
            ],
        },
    }


async def _answer_waiting_jobs(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    time_range = _extract_time_range(question, default="90d")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    waiting_tokens = {"waiting", "wating", "pending", "queued", "requested", "action_required"}

    candidates = []
    for status_field, unique_field, label in [
        (profile.get("job_status_field"), profile.get("job_execution_id_field"), "jobs"),
        ("deployment_status.state" if "deployment_status.state" in profile.get("candidate_status_fields", []) else None, profile.get("deployment_execution_id_field"), "deploys"),
    ]:
        if not status_field:
            continue
        docs = await _fetch_documents(
            mcp_session,
            call_tool,
            time_range=time_range,
            fields=[status_field, unique_field, profile.get("job_name_field"), profile.get("workflow_name_field")],
            sort=f"{time_field}:desc" if time_field else None,
        )
        total = 0
        seen = set()
        sample_names = []
        for doc in docs:
            status = str(_dig(doc, status_field) or "").lower()
            if status not in waiting_tokens:
                continue
            unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
            if unique_value:
                if unique_value in seen:
                    continue
                seen.add(unique_value)
            total += 1
            sample_names.extend(_iter_dimension_values(_dig(doc, profile.get("job_name_field"))))
        candidates.append((total, label, sorted(set(sample_names))[:5]))

    best_total, best_label, sample_names = max(candidates or [(0, "jobs", [])], key=lambda item: item[0])
    sample = f" Exemplos: {', '.join(sample_names)}." if sample_names else ""
    answer = f"{_emoji('warning')} Encontrei `{best_total}` {best_label} com status de espera/aprovacao no periodo `{time_range}`.{sample}"
    return {
        "answer": answer,
        "dashboard": {
            "id": "waiting_jobs",
            "title": "Itens Aguardando Aprovacao",
            "cards": [
                {"label": "Quantidade", "value": str(best_total), "tone": "warning"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Exemplos",
                    "items": [{"key": f"Item {index + 1}", "value": name} for index, name in enumerate(sample_names)] or [{"key": "Status", "value": "Nenhum item aguardando aprovacao"}],
                }
            ],
        },
    }


async def _answer_environment_duration_compare(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    start_field = profile.get("workflow_start_field")
    end_field = profile.get("workflow_end_field")
    unique_field = profile.get("workflow_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not start_field or not end_field:
        return None

    base_filters, base_any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    base_filters, base_any_filters = _remove_environment_filters(base_filters, base_any_filters, profile)
    filter_labels = [label for label in filter_labels if not label.startswith("ambiente ")]
    time_range = _extract_time_range(question, default="90d")

    env_payloads = []
    for env_key in ["hml", "prd"]:
        env_filters, env_any_filters, env_label = _filters_for_environment(env_key, config, profile)
        docs = await _fetch_documents(
            mcp_session,
            call_tool,
            time_range=time_range,
            fields=[start_field, end_field, unique_field],
            filters={**base_filters, **env_filters},
            any_filters={**base_any_filters, **env_any_filters},
            sort=f"{time_field}:desc" if time_field else None,
        )
        durations = []
        seen = set()
        for doc in docs:
            unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
            if unique_value:
                if unique_value in seen:
                    continue
                seen.add(unique_value)
            duration = _duration_seconds(doc, start_field, end_field)
            if duration is not None:
                durations.append(duration)
        env_payloads.append((env_label, durations))

    metrics = []
    for env_label, durations in env_payloads:
        avg_seconds = (sum(durations) / len(durations)) if durations else 0
        metrics.append({"env": env_label, "avg_seconds": avg_seconds, "count": len(durations)})

    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('duration')} Comparei o tempo medio de execucao{context} no periodo `{time_range}`. "
        + " ".join(
            f"`{row['env']}`: `{_format_duration(row['avg_seconds'])}` em `{row['count']}` execucoes."
            for row in metrics
        )
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "environment_duration_compare",
            "title": "Tempo Medio por Ambiente",
            "cards": [
                {"label": row["env"], "value": _format_duration(row["avg_seconds"]), "note": f"{row['count']} execs", "tone": "accent"}
                for row in metrics
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Duracao Media por Ambiente",
                    "series": [
                        {"label": row["env"], "value": round(row["avg_seconds"], 2), "display_value": _format_duration(row["avg_seconds"])}
                        for row in metrics
                    ],
                }
            ],
        },
    }


async def _answer_lead_time_to_deploy(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    start_field = profile.get("workflow_start_field")
    deploy_field = profile.get("deployment_updated_field") or profile.get("deployment_created_field")
    unique_field = profile.get("workflow_execution_id_field") or profile.get("deployment_execution_id_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not start_field or not deploy_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if deploy_indicator_field and deploy_value:
        filters[deploy_indicator_field] = deploy_value
        filter_labels = filter_labels + ["deploy"]

    time_range = _extract_time_range(question, default="90d")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[start_field, deploy_field, unique_field, profile.get("workflow_name_field"), profile.get("repository_name_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    durations = []
    seen = set()
    by_workflow = defaultdict(list)
    for doc in docs:
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        if unique_value:
            if unique_value in seen:
                continue
            seen.add(unique_value)
        start = _parse_iso(_dig(doc, start_field))
        end = _parse_iso(_dig(doc, deploy_field))
        if not start or not end:
            continue
        seconds = (end - start).total_seconds()
        if seconds <= 0:
            continue
        durations.append(seconds)
        workflow_name = _dig(doc, profile.get("workflow_name_field"))
        if workflow_name:
            by_workflow[str(workflow_name)].append(seconds)

    if not durations:
        return {
            "answer": f"{_emoji('deploy')} Nao encontrei eventos suficientes para calcular o lead time entre gatilho e deploy no periodo `{time_range}`.",
            "dashboard": {"id": "lead_time_to_deploy", "title": "Lead Time Ate Deploy", "cards": [], "sections": []},
        }

    avg_seconds = sum(durations) / len(durations)
    top_workflow = "-"
    top_workflow_duration = None
    if by_workflow:
        top_workflow, values = max(by_workflow.items(), key=lambda item: len(item[1]))
        top_workflow_duration = sum(values) / len(values)
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('deploy')} O tempo medio entre o gatilho e o deploy{context} no periodo `{time_range}` foi de "
        f"`{_format_duration(avg_seconds)}` com base em `{len(durations)}` execucoes."
    )
    if top_workflow_duration is not None:
        answer += f" {_emoji('workflow')} O workflow mais recorrente nessa amostra foi `{top_workflow}` com media de `{_format_duration(top_workflow_duration)}`."
    return {
        "answer": answer,
        "dashboard": {
            "id": "lead_time_to_deploy",
            "title": "Lead Time Entre Gatilho e Deploy",
            "cards": [
                {"label": "Lead Time Medio", "value": _format_duration(avg_seconds), "tone": "accent"},
                {"label": "Execucoes", "value": str(len(durations)), "tone": "accent"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Resumo",
                    "items": [
                        {"key": "Workflow mais recorrente", "value": top_workflow},
                        {"key": "Media do workflow", "value": _format_duration(top_workflow_duration)},
                        {"key": "Filtro", "value": ", ".join(filter_labels) or "deploy"},
                    ],
                }
            ],
        },
    }


def _scope_candidates_from_docs(docs: list[dict], repo_field: str | None, workflow_field: str | None) -> tuple[list[str], list[str]]:
    repo_candidates = sorted({str(_dig(doc, repo_field)) for doc in docs if _dig(doc, repo_field)})
    workflow_candidates = sorted({str(_dig(doc, workflow_field)) for doc in docs if _dig(doc, workflow_field)})
    return repo_candidates, workflow_candidates


async def _answer_anchor_to_first_delivery(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
    anchor_kind: str,
) -> dict | None:
    anchor_map = {
        "repository_request": ("repository_request_date_field", "abertura do chamado do repositorio"),
        "pipeline_request": ("pipeline_request_date_field", "solicitacao de habilitacao da esteira"),
        "workflow_created": ("workflow_created_field", "criacao da esteira"),
    }
    anchor_profile_key, anchor_label = anchor_map[anchor_kind]
    anchor_field = profile.get(anchor_profile_key)
    repo_field = profile.get("repository_name_field")
    workflow_field = profile.get("workflow_name_field")
    env_field = profile.get("environment_field")
    deploy_time_field = profile.get("deployment_updated_field") or profile.get("deployment_created_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if not anchor_field or not deploy_time_field or not repo_field or not workflow_field or not deploy_indicator_field or not deploy_value:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    explicit_repo = _extract_explicit_repo_reference(question)
    explicit_workflow = _extract_explicit_workflow_reference(question) if anchor_kind == "workflow_created" else None
    if explicit_repo and repo_field:
        filters[repo_field] = explicit_repo
    if explicit_workflow and workflow_field:
        filters[workflow_field] = explicit_workflow
        filter_labels = filter_labels + [f"workflow {explicit_workflow}"]
    else:
        filters[deploy_indicator_field] = deploy_value
        filter_labels = filter_labels + ["deploy"]
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range="365d",
        fields=[repo_field, workflow_field, env_field, anchor_field, deploy_time_field, profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{deploy_time_field}:asc" if deploy_time_field else f"{time_field}:asc",
        max_docs=1200,
    )
    if not docs:
        return None

    repo_candidates, workflow_candidates = _scope_candidates_from_docs(docs, repo_field, workflow_field)
    matched_repo = explicit_repo or _match_named_candidate(question, repo_candidates)
    matched_workflow = explicit_workflow or _match_named_candidate(question, workflow_candidates)
    exact_env = _infer_exact_environment_value(question)
    explicit_anchor = _extract_explicit_datetime(question)

    scoped_docs = []
    for doc in docs:
        if matched_repo and str(_dig(doc, repo_field)) != matched_repo:
            continue
        if matched_workflow and str(_dig(doc, workflow_field)) != matched_workflow:
            continue
        if exact_env and not _env_matches_doc(doc, exact_env):
            continue
        scoped_docs.append(doc)
    if not scoped_docs:
        return None

    scoped_docs.sort(key=lambda doc: _parse_iso(_dig(doc, deploy_time_field)) or datetime.max.replace(tzinfo=timezone.utc))
    first_doc = None
    lead_seconds = None
    anchor_value = explicit_anchor
    for doc in scoped_docs:
        anchor_dt = explicit_anchor or _parse_iso(_dig(doc, anchor_field))
        deploy_dt = _parse_iso(_dig(doc, deploy_time_field))
        if not anchor_dt or not deploy_dt or deploy_dt < anchor_dt:
            continue
        first_doc = doc
        anchor_value = anchor_dt
        lead_seconds = (deploy_dt - anchor_dt).total_seconds()
        break
    if not first_doc or lead_seconds is None:
        return None

    repo_name = _dig(first_doc, repo_field) or "-"
    workflow_name = _dig(first_doc, workflow_field) or "-"
    env_value = _dig(first_doc, env_field) or exact_env or "-"
    deploy_time = _dig(first_doc, deploy_time_field) or "-"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = (
        f"{_emoji('duration')} O tempo entre `{anchor_label}` e a primeira entrega{context}"
        f" foi de `{_format_duration(lead_seconds)}`."
        f" {_emoji('workflow')} Repositorio `{repo_name}` | workflow `{workflow_name}` | ambiente `{env_value}` | primeira entrega em `{deploy_time}`."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"{anchor_kind} first delivery {question}"),
            "title": "Lead Time Ate a Primeira Entrega",
            "cards": [
                {"label": "Lead Time", "value": _format_duration(lead_seconds), "tone": "accent"},
                {"label": "Repositorio", "value": str(repo_name), "tone": "accent"},
                {"label": "Ambiente", "value": str(env_value), "tone": "warning"},
                {"label": "Workflow", "value": str(workflow_name), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Marcos",
                    "items": [
                        {"key": "Marco inicial", "value": anchor_label},
                        {"key": "Data inicial", "value": anchor_value.isoformat().replace("+00:00", "Z") if anchor_value else "-"},
                        {"key": "Primeiro deploy", "value": str(deploy_time)},
                    ],
                }
            ],
        },
    }


async def _answer_average_rollback_duration(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    start_field = profile.get("workflow_start_field")
    end_field = profile.get("workflow_end_field")
    workflow_field = profile.get("workflow_name_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    if not start_field or not end_field or not workflow_field:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    if deploy_indicator_field == "deployment.task":
        filters[deploy_indicator_field] = "rollback"
    else:
        filters[workflow_field] = ["*rollback*"]
    filter_labels = filter_labels + ["rollback"]
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="90d"),
        fields=[start_field, end_field, profile.get("workflow_execution_id_field"), workflow_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    durations = []
    seen = set()
    for doc in docs:
        unique_value = str(_dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, workflow_field) or "")
        if unique_value in seen:
            continue
        seen.add(unique_value)
        duration = _duration_seconds(doc, start_field, end_field)
        if duration is not None:
            durations.append(duration)
    if not durations:
        return None
    avg_seconds = sum(durations) / len(durations)
    answer = (
        f"{_emoji('duration')} O tempo medio de execucao de esteiras de rollback no periodo `{_extract_time_range(question, default='90d')}` "
        f"foi de `{_format_duration(avg_seconds)}` com base em `{len(durations)}` execucoes."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "rollback_average_duration",
            "title": "Duracao Media de Rollbacks",
            "cards": [
                {"label": "Duracao Media", "value": _format_duration(avg_seconds), "tone": "accent"},
                {"label": "Execucoes", "value": str(len(durations)), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_recent_rollback_listing(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    workflow_field = profile.get("workflow_name_field")
    status_field = _best_status_field(profile)
    time_field = profile.get("deployment_updated_field") or profile.get("workflow_start_field") or profile.get("primary_time_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    if not repo_field or not workflow_field or not time_field or not deploy_indicator_field:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    if deploy_indicator_field == "deployment.task":
        filters[deploy_indicator_field] = "rollback"
    else:
        filters[workflow_field] = ["*rollback*"]
    filter_labels = filter_labels + ["rollback"]
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="30d"),
        fields=[repo_field, workflow_field, status_field, time_field, profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc",
        max_docs=100,
    )
    lines = []
    seen = set()
    for doc in docs:
        unique_value = str(_dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field) or "")
        if unique_value in seen:
            continue
        seen.add(unique_value)
        lines.append(
            f"`{_dig(doc, repo_field) or '-'}` | workflow `{_dig(doc, workflow_field) or '-'}` | data `{_dig(doc, time_field) or '-'}` | status `{_dig(doc, status_field) or '-'}`"
        )
        if len(lines) == 8:
            break
    if not lines:
        return None
    return {
        "answer": f"{_emoji('deploy')} Lista das esteiras que realizaram rollback no periodo `{_extract_time_range(question, default='30d')}`:\n" + _format_bullet_list(lines),
        "dashboard": {
            "id": "recent_rollbacks",
            "title": "Rollbacks Recentes",
            "cards": [
                {"label": "Rollbacks", "value": str(len(lines)), "tone": "warning"},
                {"label": "Periodo", "value": _extract_time_range(question, default="30d"), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_multiple_rollbacks(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    workflow_field = profile.get("workflow_name_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    time_field = profile.get("deployment_updated_field") or profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not repo_field or not workflow_field or not deploy_indicator_field:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    if deploy_indicator_field == "deployment.task":
        filters[deploy_indicator_field] = "rollback"
    else:
        filters[workflow_field] = ["*rollback*"]
    filter_labels = filter_labels + ["rollback"]
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="50d"),
        fields=[repo_field, workflow_field, profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    counters = defaultdict(set)
    for doc in docs:
        repo = _dig(doc, repo_field)
        workflow = _dig(doc, workflow_field)
        unique_value = _dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field)
        if repo and workflow and unique_value is not None:
            counters[f"{repo} | {workflow}"].add(str(unique_value))
    rows = sorted(((label, len(ids)) for label, ids in counters.items() if len(ids) > 1), key=lambda item: (-item[1], item[0]))
    if not rows:
        return None
    answer = f"{_emoji('warning')} As esteiras que executaram mais de um rollback no periodo `{_extract_time_range(question, default='50d')}` foram:\n" + _format_bullet_list(
        [f"`{label}` com `{count}` rollbacks" for label, count in rows[:8]]
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "multiple_rollbacks",
            "title": "Esteiras com Mais de Um Rollback",
            "cards": [
                {"label": "Esteiras", "value": str(len(rows)), "tone": "warning"},
                {"label": "Periodo", "value": _extract_time_range(question, default="50d"), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_deploy_frequency(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    workflow_field = profile.get("workflow_name_field")
    time_field = profile.get("deployment_updated_field") or profile.get("workflow_start_field") or profile.get("primary_time_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if not workflow_field or not deploy_indicator_field or not deploy_value:
        return None

    time_range = _extract_time_range(question, default="90d")
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    filters[deploy_indicator_field] = deploy_value
    explicit_workflow = _extract_explicit_workflow_reference(question)
    if explicit_workflow and workflow_field:
        filters[workflow_field] = explicit_workflow
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[workflow_field, repo_field, profile.get("workflow_execution_id_field"), profile.get("repository_topic_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    if not docs:
        return None
    repo_candidates, workflow_candidates = _scope_candidates_from_docs(docs, repo_field, workflow_field)
    matched_workflow = explicit_workflow or _match_named_candidate(question, workflow_candidates)
    subject_label = None
    if matched_workflow:
        docs = [doc for doc in docs if str(_dig(doc, workflow_field)) == matched_workflow]
        subject_label = f"workflow `{matched_workflow}`"
    elif filter_labels:
        subject_label = ", ".join(filter_labels)
    else:
        matched_repo = _match_named_candidate(question, repo_candidates)
        if matched_repo:
            docs = [doc for doc in docs if str(_dig(doc, repo_field)) == matched_repo]
            subject_label = f"repositorio `{matched_repo}`"
    execution_ids = {
        str(_dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field))
        for doc in docs
        if _dig(doc, profile.get("workflow_execution_id_field")) is not None or _dig(doc, time_field) is not None
    }
    total = len(execution_ids)
    days = _time_range_days(time_range)
    per_day = total / days
    per_week = per_day * 7
    answer = (
        f"{_emoji('deploy')} A frequencia de deploy"
        + (f" para {subject_label}" if subject_label else "")
        + f" no periodo `{time_range}` foi de `{total}` deploys, com media de `{per_day:.2f}` por dia "
          f"e `{per_week:.2f}` por semana."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "deploy_frequency",
            "title": "Frequencia de Deploy",
            "cards": [
                {"label": "Deploys", "value": str(total), "tone": "accent"},
                {"label": "Por dia", "value": f"{per_day:.2f}", "tone": "accent"},
                {"label": "Por semana", "value": f"{per_week:.2f}", "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_first_dev_to_prd_gap(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    time_field = profile.get("deployment_updated_field") or profile.get("deployment_created_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if not repo_field or not time_field or not deploy_indicator_field or not deploy_value:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    filters, any_filters = _remove_environment_filters(filters, any_filters, profile)
    filter_labels = [label for label in filter_labels if "ambiente" not in label.lower()]
    filters[deploy_indicator_field] = deploy_value
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range="365d",
        fields=[repo_field, time_field, profile.get("environment_field"), profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:asc",
        max_docs=5000,
    )
    by_repo = defaultdict(lambda: {"DEV": None, "PRD": None})
    for doc in docs:
        repo = _dig(doc, repo_field)
        when = _parse_iso(_dig(doc, time_field))
        if not repo or not when:
            continue
        for env in ["DEV", "PRD"]:
            if _env_matches_doc(doc, env) and by_repo[str(repo)][env] is None:
                by_repo[str(repo)][env] = when
    durations = []
    for values in by_repo.values():
        if values["DEV"] and values["PRD"] and values["PRD"] >= values["DEV"]:
            durations.append((values["PRD"] - values["DEV"]).total_seconds())
    if not durations:
        return None
    avg_seconds = sum(durations) / len(durations)
    answer = (
        f"{_emoji('duration')} Em media, o tempo entre o primeiro deploy em DEV e o primeiro deploy em PRD foi de "
        f"`{_format_duration(avg_seconds)}` com base em `{len(durations)}` esteiras/repositorios."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "first_dev_to_prd_gap",
            "title": "Tempo Medio do Primeiro DEV ate PRD",
            "cards": [
                {"label": "Tempo Medio", "value": _format_duration(avg_seconds), "tone": "accent"},
                {"label": "Amostra", "value": str(len(durations)), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_dev_deploys_before_promotion(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    time_field = profile.get("deployment_updated_field") or profile.get("deployment_created_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if not repo_field or not time_field or not deploy_indicator_field or not deploy_value:
        return None
    target_env = "PRD" if "prd" in _plain_text(question) else "HML"
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    filters, any_filters = _remove_environment_filters(filters, any_filters, profile)
    filter_labels = [label for label in filter_labels if "ambiente" not in label.lower()]
    filters[deploy_indicator_field] = deploy_value
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range="365d",
        fields=[repo_field, time_field, profile.get("environment_field"), profile.get("workflow_execution_id_field")],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:asc",
        max_docs=5000,
    )
    by_repo = defaultdict(list)
    for doc in docs:
        repo = _dig(doc, repo_field)
        when = _parse_iso(_dig(doc, time_field))
        if repo and when:
            by_repo[str(repo)].append(doc)
    counts = []
    for repo_docs in by_repo.values():
        first_target = None
        dev_count = 0
        seen = set()
        for doc in repo_docs:
            unique_value = str(_dig(doc, profile.get("workflow_execution_id_field")) or _dig(doc, time_field))
            if unique_value in seen:
                continue
            seen.add(unique_value)
            if _env_matches_doc(doc, "DEV"):
                dev_count += 1
            if _env_matches_doc(doc, target_env):
                first_target = _parse_iso(_dig(doc, time_field))
                break
        if first_target is not None:
            counts.append(dev_count)
    if not counts:
        return None
    avg_count = sum(counts) / len(counts)
    answer = (
        f"{_emoji('deploy')} Em media, ocorrem `{avg_count:.2f}` deploys em DEV antes do primeiro deploy em `{target_env}` "
        f"na amostra de `{len(counts)}` esteiras/repositorios."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "dev_before_promotion",
            "title": "Deploys em DEV Antes da Promocao",
            "cards": [
                {"label": "Media DEV", "value": f"{avg_count:.2f}", "tone": "accent"},
                {"label": "Destino", "value": target_env, "tone": "warning"},
                {"label": "Amostra", "value": str(len(counts)), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_team_count_for_architecture(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    repo_field = profile.get("repository_name_field")
    topic_field = profile.get("repository_topic_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not repo_field or not topic_field:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "architecture")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="365d"),
        fields=[repo_field, topic_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    teams = sorted({_extract_team_from_repo_name(_dig(doc, repo_field)) for doc in docs if _extract_team_from_repo_name(_dig(doc, repo_field))})
    if not teams:
        return None
    answer = (
        f"{_emoji('people')} Encontrei `{len(teams)}` times trabalhando com essa arquitetura"
        + (f" ({', '.join(filter_labels)})" if filter_labels else "")
        + f": {', '.join(f'`{team}`' for team in teams)}."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "team_count_for_architecture",
            "title": "Times por Arquitetura",
            "cards": [
                {"label": "Times", "value": str(len(teams)), "tone": "accent"},
                {"label": "Arquitetura", "value": ", ".join(filter_labels) or "-", "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_analyst_emails_by_architecture(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    email_field = profile.get("actor_email_field") or "sender.email"
    actor_field = profile.get("actor_field")
    actor_type_field = profile.get("actor_type_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    time_field = profile.get("deployment_updated_field") or profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not actor_field or not deploy_indicator_field or not deploy_value:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "architecture")
    filters[deploy_indicator_field] = deploy_value
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="90d"),
        fields=[email_field, actor_field, actor_type_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    emails = sorted({
        str(_dig(doc, email_field))
        for doc in docs
        if _dig(doc, email_field) and not _is_bot_doc(doc, actor_type_field, actor_field)
    })
    if not emails:
        return None
    answer = f"{_emoji('people')} Os emails dos analistas incluidos nos deploys" + (f" de {', '.join(filter_labels)}" if filter_labels else "") + " sao:\n" + _format_bullet_list([f"`{email}`" for email in emails[:20]])
    return {
        "answer": answer,
        "dashboard": {
            "id": "analyst_emails_by_architecture",
            "title": "Emails de Analistas por Arquitetura",
            "cards": [
                {"label": "Emails", "value": str(len(emails)), "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "deploy", "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_last_prd_deploy_actor_email(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    repo_field = profile.get("repository_name_field")
    email_field = profile.get("actor_email_field") or "sender.email"
    actor_field = profile.get("actor_field")
    time_field = profile.get("deployment_updated_field") or profile.get("workflow_start_field") or profile.get("primary_time_field")
    deploy_indicator_field = profile.get("deploy_indicator_field")
    deploy_value = _deploy_filter_value(deploy_indicator_field)
    if not workflow_field or not repo_field or not time_field or not deploy_indicator_field or not deploy_value:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    filters[deploy_indicator_field] = deploy_value
    explicit_workflow = _extract_explicit_workflow_reference(question)
    if explicit_workflow and workflow_field:
        filters[workflow_field] = explicit_workflow
    filters, any_filters = _remove_environment_filters(filters, any_filters, profile)
    if profile.get("environment_field"):
        filters[profile.get("environment_field")] = "PRD"
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range="365d",
        fields=[workflow_field, repo_field, email_field, actor_field, time_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc",
        max_docs=200,
    )
    workflow_candidates = sorted({str(_dig(doc, workflow_field)) for doc in docs if _dig(doc, workflow_field)})
    matched_workflow = explicit_workflow or _match_named_candidate(question, workflow_candidates)
    if matched_workflow:
        docs = [doc for doc in docs if str(_dig(doc, workflow_field)) == matched_workflow]
    if not docs:
        return None
    doc = docs[0]
    answer = (
        f"{_emoji('people')} O email do analista que engatilhou o ultimo deploy em PRD"
        + (f" da esteira `{matched_workflow}`" if matched_workflow else "")
        + f" foi `{_dig(doc, email_field) or '-'}`"
          f" ({_dig(doc, actor_field) or '-'}) no repositorio `{_dig(doc, repo_field) or '-'}` em `{_dig(doc, time_field) or '-'}`."
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "last_prd_deploy_actor_email",
            "title": "Email do Ultimo Deploy em PRD",
            "cards": [
                {"label": "Email", "value": str(_dig(doc, email_field) or "-"), "tone": "accent"},
                {"label": "Analista", "value": str(_dig(doc, actor_field) or "-"), "tone": "accent"},
                {"label": "Workflow", "value": str(_dig(doc, workflow_field) or "-"), "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_analysts_working_on_workflow(
    *,
    question: str,
    config: dict,
    profile: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    actor_field = profile.get("actor_field")
    email_field = profile.get("actor_email_field") or "sender.email"
    actor_type_field = profile.get("actor_type_field")
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    if not workflow_field or not actor_field:
        return None
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "workflow")
    explicit_workflow = _extract_explicit_workflow_reference(question)
    if explicit_workflow and workflow_field:
        filters[workflow_field] = explicit_workflow
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=_extract_time_range(question, default="90d"),
        fields=[workflow_field, actor_field, email_field, actor_type_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
        max_docs=1000,
    )
    workflow_candidates = sorted({str(_dig(doc, workflow_field)) for doc in docs if _dig(doc, workflow_field)})
    matched_workflow = explicit_workflow or _match_named_candidate(question, workflow_candidates)
    if matched_workflow:
        docs = [doc for doc in docs if str(_dig(doc, workflow_field)) == matched_workflow]
    analysts = sorted(
        {
            f"{_dig(doc, actor_field)} <{_dig(doc, email_field)}>"
            for doc in docs
            if _dig(doc, actor_field) and _dig(doc, email_field) and not _is_bot_doc(doc, actor_type_field, actor_field)
        }
    )
    if not analysts:
        return None
    answer = (
        f"{_emoji('people')} Os analistas que estao trabalhando"
        + (f" na esteira `{matched_workflow}`" if matched_workflow else "")
        + " no periodo consultado sao:\n"
        + _format_bullet_list([f"`{item}`" for item in analysts[:12]])
    )
    return {
        "answer": answer,
        "dashboard": {
            "id": "analysts_working_on_workflow",
            "title": "Analistas por Esteira",
            "cards": [
                {"label": "Analistas", "value": str(len(analysts)), "tone": "accent"},
                {"label": "Workflow", "value": matched_workflow or "-", "tone": "accent"},
            ],
            "sections": [],
        },
    }


def _compute_success_rate_rows(
    docs: list[dict],
    *,
    dimension_field: str,
    status_field: str,
    unique_field: str | None = None,
    actor_type_field: str | None = None,
    exclude_bots: bool = False,
    dimension_getter=None,
) -> list[dict]:
    counters = defaultdict(lambda: {"total": 0, "success": 0, "failure": 0})
    seen = set()
    success_values = {"success", "completed"}
    failure_values = {"failure", "failed", "error", "timed_out"}

    for doc in docs:
        dimensions = dimension_getter(doc) if dimension_getter else _iter_dimension_values(_dig(doc, dimension_field))
        if not dimensions:
            continue
        if exclude_bots and _is_bot_doc(doc, actor_type_field, dimension_field):
            continue
        status = str(_dig(doc, status_field) or "").lower()
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        for dimension in dimensions:
            if unique_value:
                dedupe_key = (dimension, unique_value)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
            counters[dimension]["total"] += 1
            if status in success_values:
                counters[dimension]["success"] += 1
            elif status in failure_values:
                counters[dimension]["failure"] += 1

    rows = []
    for dimension, data in counters.items():
        total = data["total"]
        success = data["success"]
        failure = data["failure"]
        rate = (success / total) if total else 0
        rows.append(
            {
                "dimension": str(dimension),
                "total": total,
                "success": success,
                "failure": failure,
                "success_rate": rate,
            }
        )
    return rows


def _is_bot_doc(doc: dict, actor_type_field: str | None, actor_field: str | None) -> bool:
    actor_type = str(_dig(doc, actor_type_field) or "").lower() if actor_type_field else ""
    actor_name = str(_dig(doc, actor_field) or "").lower() if actor_field else ""
    return actor_type == "bot" or "[bot]" in actor_name or "github-actions" in actor_name


async def _answer_success_rate_by_dimension(
    *,
    question: str,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
    dimension_field: str | None,
    title: str,
    answer_prefix: str,
    filters: dict,
    time_range: str,
    sort_desc: bool,
    status_field: str | None = None,
    unique_field: str | None = None,
    exclude_bots: bool = False,
) -> dict | None:
    status_field = status_field or profile.get("workflow_status_field")
    actor_type_field = profile.get("actor_type_field")
    if not dimension_field or not status_field:
        return None

    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[dimension_field, status_field, actor_type_field],
        filters=filters,
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    rows = _compute_success_rate_rows(
        docs,
        dimension_field=dimension_field,
        status_field=status_field,
        unique_field=unique_field,
        actor_type_field=actor_type_field,
        exclude_bots=exclude_bots,
    )
    rows = [row for row in rows if row["total"] > 0]
    if not rows:
        return _reformulate("Nao encontrei dados suficientes para calcular taxa de sucesso.")

    rows.sort(key=lambda row: (row["success_rate"], row["total"]), reverse=sort_desc)
    top = rows[:5]
    answer = (
        f"{answer_prefix}: "
        + ", ".join(
            f"{row['dimension']} ({row['success']}/{row['total']} = {_format_percent(row['success'], row['total'])})"
            for row in top
        )
        + "."
    )
    dashboard = {
        "id": slugify_local(title),
        "title": title,
        "cards": [
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Dimensoes", "value": str(len(rows)), "tone": "accent"},
            {"label": "Campo", "value": dimension_field, "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Taxa de Sucesso",
                "series": [
                    {
                        "label": row["dimension"],
                        "value": round(row["success_rate"] * 100, 2),
                        "display_value": f"{_format_percent(row['success'], row['total'])} ({row['total']} execs)",
                    }
                    for row in top
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_status_ranking(
    *,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
    group_field: str | None,
    status_field: str | None,
    filters: dict,
    time_range: str,
    title: str,
    answer_prefix: str,
) -> dict | None:
    if not group_field or not status_field:
        return None
    result = await _call_tool_json(
        mcp_session,
        "aggregate",
        {
            "metric": "count",
            "field": group_field,
            "group_by": group_field,
            "time_range": time_range,
            "filters": filters,
            "size": 10,
        },
        call_tool,
    )
    buckets = result.get("result", [])
    if not buckets:
        return _reformulate("Nao encontrei dados suficientes para esse ranking.")
    answer = answer_prefix + ": " + ", ".join(f"{bucket['group']} ({bucket['count']})" for bucket in buckets[:5]) + "."
    dashboard = {
        "id": slugify_local(title),
        "title": title,
        "cards": [
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Campo", "value": group_field, "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": title,
                "series": [
                    {"label": str(bucket["group"]), "value": bucket["count"], "display_value": str(bucket["count"])}
                    for bucket in buckets[:10]
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_average_duration(
    *,
    question: str,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
    start_field: str | None,
    end_field: str | None,
    unique_field: str | None,
    filters: dict,
    title: str,
    answer_prefix: str,
) -> dict | None:
    if not start_field or not end_field:
        return None
    time_range = _wide_time_range(question, schema)
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[start_field, end_field, profile.get("workflow_name_field"), profile.get("repository_name_field")],
        filters=filters,
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    durations = []
    seen = set()
    for doc in docs:
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        if unique_value and unique_value in seen:
            continue
        if unique_value:
            seen.add(unique_value)
        value = _duration_seconds(doc, start_field, end_field)
        if value is not None:
            durations.append(value)
    if not durations:
        return _reformulate("Nao encontrei dados suficientes para calcular a duracao media.")
    avg_seconds = sum(durations) / len(durations)
    answer = f"{answer_prefix} `{_format_duration(avg_seconds)}` com base em `{len(durations)}` execucoes."
    dashboard = {
        "id": slugify_local(title),
        "title": title,
        "cards": [
            {"label": "Duracao Media", "value": _format_duration(avg_seconds), "tone": "accent"},
            {"label": "Execucoes", "value": str(len(durations)), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
        ],
        "sections": [],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_duration_by_dimension(
    *,
    question: str,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
    dimension_field: str | None,
    start_field: str | None,
    end_field: str | None,
    unique_field: str | None,
    title: str,
    intro: str,
    sort_desc: bool,
    extra_fields: list[str] | None = None,
    extra_filters: dict | None = None,
) -> dict | None:
    if not dimension_field or not start_field or not end_field:
        return None
    time_range = _wide_time_range(question, schema)
    fields = [dimension_field, start_field, end_field] + (extra_fields or [])
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=fields,
        filters=extra_filters or {},
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    grouped = defaultdict(list)
    seen = set()
    for doc in docs:
        names = _iter_dimension_values(_dig(doc, dimension_field))
        duration = _duration_seconds(doc, start_field, end_field)
        if not names or duration is None:
            continue
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        for name in names:
            if unique_value:
                dedupe_key = (str(name), unique_value)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
            grouped[str(name)].append(duration)
    if not grouped:
        return _reformulate("Nao encontrei dados suficientes para calcular duracao por grupo.")
    rows = []
    for name, values in grouped.items():
        rows.append({"dimension": name, "avg_seconds": sum(values) / len(values), "count": len(values)})
    rows.sort(key=lambda row: row["avg_seconds"], reverse=sort_desc)
    top = rows[:5]
    if intro.startswith("A media"):
        answer = intro + ": " + ", ".join(f"{row['dimension']} ({_format_duration(row['avg_seconds'])})" for row in top) + "."
    else:
        first = top[0]
        answer = f"{intro} `{first['dimension']}` com duracao media de `{_format_duration(first['avg_seconds'])}`."
    dashboard = {
        "id": slugify_local(title),
        "title": title,
        "cards": [
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Campo", "value": dimension_field, "tone": "accent"},
            {"label": "Grupos", "value": str(len(rows)), "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": title,
                "series": [
                    {
                        "label": row["dimension"],
                        "value": round(row["avg_seconds"], 2),
                        "display_value": _format_duration(row["avg_seconds"]),
                    }
                    for row in top
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_fastest_workflows_by_repo(*, question: str, profile: dict, schema: dict, mcp_session, call_tool) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    repo_field = profile.get("repository_name_field")
    start_field = profile.get("workflow_start_field")
    end_field = profile.get("workflow_end_field")
    if not workflow_field or not repo_field or not start_field or not end_field:
        return None
    time_range = _wide_time_range(question, schema)
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[workflow_field, repo_field, start_field, end_field],
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    grouped = defaultdict(list)
    seen = set()
    for doc in docs:
        workflow = _dig(doc, workflow_field)
        repo = _dig(doc, repo_field)
        duration = _duration_seconds(doc, start_field, end_field)
        if not workflow or not repo or duration is None:
            continue
        execution_id = _dig(doc, profile.get("workflow_execution_id_field"))
        dedupe_key = (str(workflow), str(repo), str(execution_id))
        if execution_id is not None and dedupe_key in seen:
            continue
        if execution_id is not None:
            seen.add(dedupe_key)
        grouped[f"{workflow} @ {repo}"].append(duration)
    if not grouped:
        return _reformulate("Nao encontrei dados suficientes para relacionar workflows rapidos com repositorios.")
    rows = [{"dimension": key, "avg_seconds": sum(values) / len(values)} for key, values in grouped.items()]
    rows.sort(key=lambda row: row["avg_seconds"])
    top = rows[:5]
    answer = "Os workflows mais rapidos por repositorio foram: " + ", ".join(f"{row['dimension']} ({_format_duration(row['avg_seconds'])})" for row in top) + "."
    dashboard = {
        "id": "fastest_workflows_by_repo",
        "title": "Workflows Mais Rapidos por Repositorio",
        "cards": [
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Combinacoes", "value": str(len(rows)), "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Top Mais Rapidos",
                "series": [
                    {"label": row["dimension"], "value": round(row["avg_seconds"], 2), "display_value": _format_duration(row["avg_seconds"])}
                    for row in top
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_distinct_actors(*, question: str, config: dict, profile: dict, schema: dict, mcp_session, call_tool, title: str, answer_prefix: str) -> dict | None:
    actor_field = profile.get("actor_field")
    actor_type_field = profile.get("actor_type_field")
    if not actor_field:
        return None
    time_range = _extract_time_range(question, default="90d")
    filters, any_filters, filter_labels = _extract_business_filters(_plain_text(question), config, profile, "actor")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[actor_field, actor_type_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    actors = sorted({
        str(_dig(doc, actor_field))
        for doc in docs
        if _dig(doc, actor_field) and not _is_bot_doc(doc, actor_type_field, actor_field)
    })
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = f"{_emoji('people')} {answer_prefix} `{len(actors)}` analistas que rodaram workflows{context} no periodo `{time_range}`."
    dashboard = {
        "id": "distinct_analysts",
        "title": title,
        "cards": [
            {"label": "Analistas", "value": str(len(actors)), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
            {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
        ],
        "sections": [
            {
                "type": "kv",
                "title": "Analistas Observados",
                "items": [{"key": f"Analista {index + 1}", "value": actor} for index, actor in enumerate(actors[:12])],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_available_workflows(*, question: str, profile: dict, schema: dict, mcp_session, call_tool) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    if not workflow_field:
        return None
    time_range = _wide_time_range(question, schema)
    result = await _call_tool_json(
        mcp_session,
        "aggregate",
        {
            "metric": "count",
            "field": workflow_field,
            "group_by": workflow_field,
            "time_range": time_range,
            "size": 50,
        },
        call_tool,
    )
    buckets = result.get("result", [])
    if not buckets:
        return _reformulate("Nao encontrei workflows disponiveis nos dados atuais.")
    workflows = [str(bucket["group"]) for bucket in buckets]
    answer = "Os workflows disponiveis observados ate agora sao: " + ", ".join(workflows) + "."
    dashboard = {
        "id": "available_workflows",
        "title": "Workflows Disponiveis",
        "cards": [
            {"label": "Workflows", "value": str(len(workflows)), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Volume por Workflow",
                "series": [
                    {"label": str(bucket["group"]), "value": bucket["count"], "display_value": str(bucket["count"])}
                    for bucket in buckets
                ],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_deploy_job_executions_by_workflow(*, question: str, profile: dict, schema: dict, mcp_session, call_tool) -> dict | None:
    workflow_field = profile.get("workflow_name_field")
    job_field = profile.get("job_name_field")
    if not workflow_field or not job_field:
        return None
    time_range = _wide_time_range(question, schema)
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[workflow_field, job_field, profile.get("job_execution_id_field")],
        filters={job_field: ["*deploy*"]},
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    counts = defaultdict(set)
    for doc in docs:
        workflow = _dig(doc, workflow_field)
        job_id = _dig(doc, profile.get("job_execution_id_field")) or _dig(doc, job_field)
        if workflow and job_id:
            counts[str(workflow)].add(str(job_id))
    if not counts:
        return _reformulate("Nao encontrei jobs de deploy suficientes para essa media.")
    counts_by_workflow = {workflow: len(values) for workflow, values in counts.items()}
    total = sum(counts_by_workflow.values())
    avg = total / len(counts)
    top = sorted(counts_by_workflow.items(), key=lambda item: item[1], reverse=True)[:5]
    answer = (
        f"A media de execucoes de jobs de deploy por workflow foi `{avg:.2f}` no periodo consultado. "
        f"Os maiores volumes foram: " + ", ".join(f"{name} ({count})" for name, count in top) + "."
    )
    dashboard = {
        "id": "deploy_job_executions_by_workflow",
        "title": "Execucoes de Jobs de Deploy por Workflow",
        "cards": [
            {"label": "Media", "value": f"{avg:.2f}", "tone": "accent"},
            {"label": "Workflows", "value": str(len(counts)), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
        ],
        "sections": [
            {
                "type": "bar",
                "title": "Top Volumes de Deploy",
                "series": [{"label": name, "value": count, "display_value": str(count)} for name, count in top],
            }
        ],
    }
    return {"answer": answer, "dashboard": dashboard}


async def _answer_generic_business_question(
    *,
    question: str,
    config: dict,
    profile: dict,
    schema: dict,
    mcp_session,
    call_tool,
) -> dict | None:
    q = _plain_text(question)
    intent = _extract_generic_intent(q)
    if not intent:
        return None

    dimension = _extract_dimension_config(q, profile)
    if not dimension:
        return None

    filters, any_filters, filter_labels = _extract_business_filters(q, config, profile, dimension["kind"])
    time_range = _extract_time_range(question, default="90d")

    if intent == "volume":
        return await _answer_generic_volume_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            order="desc",
        )

    if intent == "volume_bottom":
        return await _answer_generic_volume_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            order="asc",
        )

    if intent == "count":
        return await _answer_generic_distinct_count(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
        )

    if intent == "execution_total":
        return await _answer_generic_execution_total(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
        )

    if intent == "inventory":
        return await _answer_generic_inventory(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
        )

    if intent == "success_rate":
        return await _answer_generic_success_rate_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            order="desc",
        )

    if intent == "success_rate_bottom":
        return await _answer_generic_success_rate_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            order="asc",
        )

    if intent == "failure_count":
        return await _answer_generic_failure_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            by_rate=False,
        )

    if intent == "failure_rate":
        return await _answer_generic_failure_ranking(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
            by_rate=True,
        )

    if intent == "avg_duration":
        return await _answer_generic_average_duration(
            question=question,
            profile=profile,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range=time_range,
            dimension=dimension,
            filters=filters,
            any_filters=any_filters,
            filter_labels=filter_labels,
        )

    return None


def _extract_generic_intent(q: str) -> str | None:
    if "quantas execucoes" in q or "quantidade de execucoes" in q:
        return "execution_total"
    if "quantidade" in q or any(term in q for term in ["quantos", "quantas"]):
        return "count"
    if any(term in q for term in ["ja executaram", "executaram em algum momento", "existem na base", "temos na base", "ja tiveram execu", "historico de"]) and any(
        term in q for term in ["liste", "lista", "mostre", "informe", "quais"]
    ):
        return "inventory"
    if any(term in q for term in ["disponiveis", "disponivel", "temos disponiveis", "temos disponivel"]):
        return "inventory"
    if any(term in q for term in ["menor taxa de sucesso", "pior taxa de sucesso", "menos sucesso"]):
        return "success_rate_bottom"
    if any(term in q for term in ["maior taxa de sucesso", "melhor taxa de sucesso", "mais sucesso"]):
        return "success_rate"
    if "taxa de falha" in q:
        return "failure_rate"
    if any(term in q for term in ["mais falharam", "mais falha", "mais falham", "mais falhou", "executado com falha", "volume de falhas", "maior volume de falhas", "falharam", "falhou", "com falha"]):
        return "failure_count"
    if any(term in q for term in ["media de dur", "duracao media", "tempo medio", "media de execu"]):
        return "avg_duration"
    if any(term in q for term in ["quais", "liste", "lista", "mostre", "informe"]) and any(
        term in q for term in ["executaram", "rodaram", "foram executados", "foi executado"]
    ):
        return "volume"
    if any(term in q for term in ["menos execut", "menor volume", "menos rod", "menos ocorreu", "menos teve execu"]):
        return "volume_bottom"
    if any(term in q for term in ["mais execut", "maior volume", "mais rod", "mais ocorreu", "mais teve execu"]):
        return "volume"
    return None


def _extract_dimension_config(q: str, profile: dict) -> dict | None:
    mentions_specific_dimension = any(
        term in q for term in ["workflow", "workflows", "job", "jobs", "check", "checks", "repositorio", "repositorios", "repo", "repos", "analista", "analistas", "branch", "branches", "linguagem", "linguagens", "ambiente", "ambientes", "topico", "topicos"]
    )
    asks_architecture_dimension = any(term in q for term in ["arquiteturas", "architectures"]) or (
        any(term in q for term in ["arquitetura", "architecture"]) and not mentions_specific_dimension
    )
    asks_team_dimension = any(term in q for term in ["times", "vskeys", "squads"]) or (
        any(term in q for term in ["time", "vskey", "squad"]) and not mentions_specific_dimension
    )

    if asks_architecture_dimension:
        field = profile.get("repository_topic_field")
        if field:
            return {"kind": "architecture", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "arquiteturas"}
    if asks_team_dimension:
        field = profile.get("repository_name_field")
        if field:
            return {"kind": "team", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "times"}
    asks_topics = any(
        pattern in q
        for pattern in [
            "quais topicos",
            "quais os topicos",
            "quantos topicos",
            "topicos com",
            "topicos que",
            "topicos mais",
            "topicos menos",
        ]
    )
    if asks_topics:
        field = profile.get("repository_topic_field")
        if field:
            return {"kind": "topic", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "topicos"}
    if any(term in q for term in ["linguagem", "linguagens", "tecnologia", "tecnologias"]):
        field = profile.get("repository_language_field")
        if field:
            return {"kind": "language", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "linguagens"}
    if any(term in q for term in ["branch", "branches"]):
        field = profile.get("branch_field")
        if field:
            return {"kind": "branch", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "branches"}
    if any(term in q for term in ["ambiente", "ambientes"]):
        field = profile.get("environment_field")
        if field:
            return {"kind": "environment", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "ambientes"}
    if any(term in q for term in ["repositorio", "repositorios", "repo", "repos"]):
        field = profile.get("repository_name_field")
        if field:
            return {"kind": "repository", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "repositorios"}
    if any(term in q for term in ["analista", "analistas"]):
        field = profile.get("actor_field")
        if field:
            return {"kind": "actor", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "analistas", "exclude_bots": True}
    if any(term in q for term in ["job", "jobs", "check", "checks"]):
        field = profile.get("job_name_field")
        if field:
            return {"kind": "job", "field": field, "unique_field": profile.get("job_execution_id_field"), "label": "jobs"}
    field = profile.get("workflow_name_field")
    if field:
        return {"kind": "workflow", "field": field, "unique_field": profile.get("workflow_execution_id_field"), "label": "workflows"}
    return None


def _extract_business_filters(q: str, config: dict, profile: dict, dimension_kind: str) -> tuple[dict, dict, list[str]]:
    filters = {}
    any_filters = {}
    labels = []

    env_filters, env_any_filters, env_labels = extract_environment_semantics(q, config, profile)
    filters.update(env_filters)
    any_filters.update(env_any_filters)
    labels.extend(env_labels)

    language_field = profile.get("repository_language_field")
    if language_field:
        for language in ["java", "python", "typescript", "node"]:
            if re.search(rf"\b{re.escape(language)}\b", q):
                filters[language_field] = language
                labels.append(f"linguagem {language}")
                break

    topic_field = profile.get("repository_topic_field")
    if topic_field:
        match = re.search(r"topicos?\s+([a-z0-9._-]+)", q)
        if match:
            topic = match.group(1)
            filters[topic_field] = topic
            labels.append(f"topico {topic}")

    architecture_filters, architecture_labels = extract_architecture_filter(q, config, topic_field)
    filters.update(architecture_filters)
    labels.extend(architecture_labels)

    private_field = profile.get("repository_private_field")
    if private_field:
        if any(term in q for term in ["privado", "privados", "privada", "privadas"]):
            filters[private_field] = True
            labels.append("repositorios privados")
        elif any(term in q for term in ["publico", "publicos", "publica", "publicas"]):
            filters[private_field] = False
            labels.append("repositorios publicos")

    fork_field = profile.get("repository_fork_field")
    if fork_field and any(term in q for term in ["fork", "forks"]):
        filters[fork_field] = True
        labels.append("repositorios fork")

    branch_field = profile.get("branch_field")
    if branch_field:
        branch_match = re.search(r"branch\s+([a-z0-9._/-]+)", q)
        if branch_match:
            branch = branch_match.group(1)
            filters[branch_field] = branch
            labels.append(f"branch {branch}")
        elif re.search(r"\bmain\b", q):
            filters[branch_field] = "main"
            labels.append("branch main")
        elif re.search(r"\bdevelop\b", q):
            filters[branch_field] = "develop"
            labels.append("branch develop")

    workflow_field = profile.get("workflow_name_field")
    job_field = profile.get("job_name_field")
    workflow_patterns = extract_pipeline_type_patterns(q, config)
    if workflow_patterns:
        if dimension_kind == "job" and job_field:
            filters[job_field] = workflow_patterns
        elif workflow_field:
            filters[workflow_field] = workflow_patterns
        labels.append("tipo de esteira filtrado")

    if job_field and "gate" in q:
        any_filters[job_field] = list(dict.fromkeys(any_filters.get(job_field, []) + ["*gate*", "*approval*"]))
        labels.append("etapas gate")

    team_filters, team_labels = extract_team_filter(q, config, profile.get("repository_name_field"))
    filters.update(team_filters)
    labels.extend(team_labels)

    return filters, any_filters, labels


def _remove_environment_filters(filters: dict, any_filters: dict, profile: dict) -> tuple[dict, dict]:
    clean_filters = dict(filters)
    clean_any_filters = dict(any_filters)
    env_field = profile.get("environment_field")
    candidate_fields = {
        env_field,
        profile.get("workflow_name_field"),
        profile.get("job_name_field"),
        profile.get("branch_field"),
    }
    for field in list(candidate_fields):
        if not field:
            continue
        clean_any_filters.pop(field, None)
    if env_field:
        clean_filters.pop(env_field, None)
    return clean_filters, clean_any_filters


def _environment_rule(config: dict, env_key: str) -> dict:
    return config.get("domain", {}).get("semantic_rules", {}).get("environment_aliases", {}).get(env_key, {})


def _filters_for_environment(env_key: str, config: dict, profile: dict) -> tuple[dict, dict, str]:
    rule = _environment_rule(config, env_key)
    filters = {}
    any_filters = {}
    label = rule.get("label", env_key.upper())
    exact_values = rule.get("exact_values", [])
    contains_tokens = rule.get("contains_tokens", [])
    if profile.get("environment_field") and exact_values:
        filters[profile.get("environment_field")] = exact_values
        return filters, any_filters, label
    for field_name in rule.get("field_preferences", []):
        resolved_field = profile.get(field_name) if field_name.endswith("_field") else field_name
        if not resolved_field:
            continue
        values = []
        if field_name in {"environment_field", "deployment.environment", "deployment_status.environment"}:
            values.extend(exact_values)
        for token in contains_tokens:
            values.extend([f"*{token.lower()}*", f"*{token.upper()}*", f"*{token.title()}*"])
        if values:
            any_filters[resolved_field] = list(dict.fromkeys(values))
    if profile.get("environment_field") and exact_values:
        filters[profile.get("environment_field")] = exact_values
        any_filters.pop(profile.get("environment_field"), None)
    return filters, any_filters, label


def _dimension_source_fields(dimension: dict, profile: dict) -> list[str]:
    if dimension["kind"] == "architecture":
        fields = [profile.get("repository_topic_field"), dimension.get("unique_field")]
    elif dimension["kind"] == "team":
        fields = [profile.get("repository_name_field"), dimension.get("unique_field")]
    else:
        fields = [dimension["field"], dimension.get("unique_field")]
    if dimension.get("exclude_bots"):
        fields.append(profile.get("actor_type_field"))
    return [field for field in fields if field]


def _dimension_values(doc: dict, dimension: dict) -> list[str]:
    kind = dimension.get("kind")
    if kind == "architecture":
        return _extract_architectures_from_topics(_dig(doc, dimension["field"]))
    if kind == "team":
        value = _extract_team_from_repo_name(_dig(doc, dimension["field"]))
        return [value] if value else []
    return _iter_dimension_values(_dig(doc, dimension["field"]))


def _select_status_field_for_filters(profile: dict, dimension: dict, filters: dict) -> str | None:
    if dimension["kind"] == "job":
        return profile.get("job_status_field")
    if profile.get("environment_field") and profile.get("environment_field") in filters and "deployment_status.state" in profile.get("candidate_status_fields", []):
        return "deployment_status.state"
    return profile.get("workflow_status_field")


async def _answer_generic_volume_ranking(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
    order: str,
) -> dict | None:
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile),
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    rows = _compute_unique_counts(docs, group_field=dimension["field"], unique_field=dimension.get("unique_field"))
    if dimension["kind"] in {"architecture", "team"}:
        rows = _compute_unique_counts(
            docs,
            group_field=dimension["field"],
            unique_field=dimension.get("unique_field"),
            group_getter=lambda doc: _dimension_values(doc, dimension),
        )
    if dimension.get("exclude_bots"):
        rows = [row for row in rows if "[bot]" not in row["group"].lower()]
    if not rows:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": (
                f"{_emoji('summary')} No ranking de {dimension['label']}{context}, "
                f"encontrei `0` itens com execucoes no periodo `{time_range}`."
            ),
            "dashboard": {
                "id": slugify_local(f"ranking vazio {dimension['label']}"),
                "title": f"Ranking de {dimension['label'].title()} por Execucoes",
                "cards": [
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                    {"label": "Dimensoes", "value": "0", "tone": "warning"},
                ],
                "sections": [],
            },
        }
    rows.sort(key=lambda item: (item["count"], item["group"]))
    limit = 10 if _wants_list_output(question) else 5
    top = rows[:limit] if order == "asc" else list(reversed(rows[-limit:]))
    descriptor = "mais" if order == "desc" else "menos"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    if _wants_list_output(question):
        answer = (
            f"{_emoji('summary')} Lista de {dimension['label']}{context} que {descriptor} executaram workflows no periodo `{time_range}`:\n"
            + _format_bullet_list([f"`{item['group']}` com `{item['count']}` execucoes" for item in top])
        )
    else:
        answer = (
            f"No ranking de {dimension['label']}{context}, os itens que {descriptor} executaram workflows no periodo consultado foram: "
            + ", ".join(f"{item['group']} ({item['count']})" for item in top)
            + "."
        )
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"ranking {descriptor} {dimension['label']}"),
            "title": f"Ranking de {dimension['label'].title()} por Execucoes",
            "cards": [
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                {"label": "Dimensoes", "value": str(len(rows)), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": f"{dimension['label'].title()} com {descriptor} execucoes",
                    "series": [
                        {"label": item["group"], "value": item["count"], "display_value": str(item["count"])}
                        for item in top
                    ],
                }
            ],
        },
    }


async def _answer_generic_distinct_count(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
) -> dict | None:
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile),
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    values = set()
    for doc in docs:
        if dimension.get("exclude_bots") and _is_bot_doc(doc, profile.get("actor_type_field"), dimension["field"]):
            continue
        values.update(_dimension_values(doc, dimension))
    if not values:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": f"{_emoji('summary')} Encontrei `0` {dimension['label']}{context} no periodo `{time_range}`.",
            "dashboard": {
                "id": slugify_local(f"count {dimension['label']}"),
                "title": f"Contagem de {dimension['label'].title()}",
                "cards": [
                    {"label": "Quantidade", "value": "0", "tone": "warning"},
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                ],
                "sections": [],
            },
        }
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = f"Encontrei `{len(values)}` {dimension['label']}{context} no periodo `{time_range}`."
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"count {dimension['label']}"),
            "title": f"Contagem de {dimension['label'].title()}",
            "cards": [
                {"label": "Quantidade", "value": str(len(values)), "tone": "accent"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_generic_execution_total(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
) -> dict | None:
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    unique_field = dimension.get("unique_field") or profile.get("workflow_execution_id_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile) + ([unique_field] if unique_field else []),
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    values = set()
    for doc in docs:
        unique_value = _dig(doc, unique_field) if unique_field else None
        if unique_value is not None:
            values.add(str(unique_value))
    if not values:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": f"{_emoji('summary')} Encontrei `0` execucoes{context} no periodo `{time_range}`.",
            "dashboard": {
                "id": slugify_local(f"execution total {dimension['label']}"),
                "title": "Contagem de Execucoes",
                "cards": [
                    {"label": "Execucoes", "value": "0", "tone": "warning"},
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                ],
                "sections": [],
            },
        }
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    answer = f"Encontrei `{len(values)}` execucoes{context} no periodo `{time_range}`."
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"execution total {dimension['label']}"),
            "title": "Contagem de Execucoes",
            "cards": [
                {"label": "Execucoes", "value": str(len(values)), "tone": "accent"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
            ],
            "sections": [],
        },
    }


async def _answer_generic_inventory(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
) -> dict | None:
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile),
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    values = sorted({
        value
        for doc in docs
        for value in _dimension_values(doc, dimension)
        if value and not (dimension.get("exclude_bots") and "[bot]" in value.lower())
    })
    if not values:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": f"{_emoji('summary')} Os valores disponiveis para {dimension['label']}{context} no periodo consultado somaram `0` itens.",
            "dashboard": {
                "id": slugify_local(f"inventory {dimension['label']}"),
                "title": f"{dimension['label'].title()} Disponiveis",
                "cards": [
                    {"label": "Total", "value": "0", "tone": "warning"},
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                ],
                "sections": [],
            },
        }
    preview = values[:20] if _wants_list_output(question) else values[:12]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    if _wants_list_output(question):
        answer = (
            f"{_emoji('summary')} Lista de {dimension['label']}{context} observados no periodo `{time_range}`:\n"
            + _format_bullet_list([f"`{value}`" for value in preview])
        )
    else:
        answer = f"Os valores disponiveis para {dimension['label']}{context} no periodo consultado sao: " + ", ".join(preview) + "."
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"inventory {dimension['label']}"),
            "title": f"{dimension['label'].title()} Disponiveis",
            "cards": [
                {"label": "Total", "value": str(len(values)), "tone": "accent"},
                {"label": "Periodo", "value": time_range, "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "kv",
                    "title": "Valores Observados",
                    "items": [{"key": f"Item {index + 1}", "value": value} for index, value in enumerate(preview)],
                }
            ],
        },
    }


async def _answer_generic_success_rate_ranking(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
    order: str,
) -> dict | None:
    status_field = _select_status_field_for_filters(profile, dimension, filters)
    if not status_field:
        return None
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile) + [status_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    rows = _compute_success_rate_rows(
        docs,
        dimension_field=dimension["field"],
        status_field=status_field,
        unique_field=dimension.get("unique_field"),
        actor_type_field=profile.get("actor_type_field"),
        exclude_bots=dimension.get("exclude_bots", False),
        dimension_getter=(lambda doc: _dimension_values(doc, dimension)),
    )
    rows = [row for row in rows if row["total"] > 0]
    if not rows:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": (
                f"{_emoji('summary')} Encontrei `0` execucoes validas para calcular taxa de sucesso em "
                f"{dimension['label']}{context} no periodo `{time_range}`."
            ),
            "dashboard": {
                "id": slugify_local(f"success {dimension['label']}"),
                "title": f"Taxa de Sucesso por {dimension['label'].title()}",
                "cards": [
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                    {"label": "Dimensoes", "value": "0", "tone": "warning"},
                ],
                "sections": [],
            },
        }
    rows.sort(key=lambda row: (row["success_rate"], row["total"], row["dimension"]))
    limit = 10 if _wants_list_output(question) else 5
    top = rows[:limit] if order == "asc" else list(reversed(rows[-limit:]))
    descriptor = "maior" if order == "desc" else "menor"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    if _wants_list_output(question):
        answer = (
            f"{_emoji('success')} Lista de {dimension['label']}{context} com {descriptor} taxa de sucesso no periodo `{time_range}`:\n"
            + _format_bullet_list(
                [f"`{row['dimension']}` com `{row['success']}/{row['total']}` = `{_format_percent(row['success'], row['total'])}`" for row in top]
            )
        )
    else:
        answer = (
            f"No ranking de {dimension['label']}{context}, os itens com {descriptor} taxa de sucesso foram: "
            + ", ".join(
                f"{row['dimension']} ({row['success']}/{row['total']} = {_format_percent(row['success'], row['total'])})"
                for row in top
            )
            + "."
        )
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"success {dimension['label']}"),
            "title": f"Taxa de Sucesso por {dimension['label'].title()}",
            "cards": [
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                {"label": "Dimensoes", "value": str(len(rows)), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Taxa de Sucesso",
                    "series": [
                        {
                            "label": row["dimension"],
                            "value": round(row["success_rate"] * 100, 2),
                            "display_value": _format_percent(row["success"], row["total"]),
                        }
                        for row in top
                    ],
                }
            ],
        },
    }


async def _answer_generic_failure_ranking(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
    by_rate: bool,
) -> dict | None:
    status_field = _select_status_field_for_filters(profile, dimension, filters)
    if not status_field:
        return None
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile) + [status_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    rows = _compute_success_rate_rows(
        docs,
        dimension_field=dimension["field"],
        status_field=status_field,
        unique_field=dimension.get("unique_field"),
        actor_type_field=profile.get("actor_type_field"),
        exclude_bots=dimension.get("exclude_bots", False),
        dimension_getter=(lambda doc: _dimension_values(doc, dimension)),
    )
    rows = [row for row in rows if row["total"] > 0]
    if not rows:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": (
                f"{_emoji('summary')} No ranking de {dimension['label']}{context}, "
                f"encontrei `0` execucoes com falha no periodo `{time_range}`."
            ),
            "dashboard": {
                "id": slugify_local(f"failure {dimension['label']}"),
                "title": f"Falhas por {dimension['label'].title()}",
                "cards": [
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                    {"label": "Dimensoes", "value": "0", "tone": "warning"},
                ],
                "sections": [],
            },
        }
    for row in rows:
        row["failure_rate"] = (row["failure"] / row["total"]) if row["total"] else 0
    if by_rate:
        rows.sort(key=lambda row: (row["failure_rate"], row["failure"], row["dimension"]), reverse=True)
        top = rows[:10] if _wants_list_output(question) else rows[:5]
        if _plain_text(question).startswith("qual"):
            first = top[0]
            answer = (
                f"{_emoji('failure')} O item com maior taxa de falha em {dimension['label']}"
                + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                + f" foi `{first['dimension']}` ({first['failure']}/{first['total']} = {_format_percent(first['failure'], first['total'])})."
            )
        else:
            if _wants_list_output(question):
                answer = (
                    f"{_emoji('failure')} Lista de {dimension['label']}"
                    + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                    + f" com maior taxa de falha no periodo `{time_range}`:\n"
                    + _format_bullet_list(
                        [f"`{row['dimension']}` com `{row['failure']}/{row['total']}` = `{_format_percent(row['failure'], row['total'])}`" for row in top]
                    )
                )
            else:
                answer = (
                    f"No ranking de {dimension['label']}"
                    + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                    + ", os itens com maior taxa de falha foram: "
                    + ", ".join(
                        f"{row['dimension']} ({row['failure']}/{row['total']} = {_format_percent(row['failure'], row['total'])})"
                        for row in top
                    )
                    + "."
                )
        series = [
            {"label": row["dimension"], "value": round(row["failure_rate"] * 100, 2), "display_value": _format_percent(row["failure"], row["total"])}
            for row in top
        ]
    else:
        rows.sort(key=lambda row: (row["failure"], row["total"], row["dimension"]), reverse=True)
        top = rows[:10] if _wants_list_output(question) else rows[:5]
        if _plain_text(question).startswith("qual"):
            first = top[0]
            answer = (
                f"{_emoji('failure')} O item com maior volume de falhas em {dimension['label']}"
                + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                + f" foi `{first['dimension']}` ({first['failure']})."
            )
        else:
            if _wants_list_output(question):
                answer = (
                    f"{_emoji('failure')} Lista de {dimension['label']}"
                    + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                    + f" com maior volume de falhas no periodo `{time_range}`:\n"
                    + _format_bullet_list([f"`{row['dimension']}` com `{row['failure']}` falhas" for row in top])
                )
            else:
                answer = (
                    f"No ranking de {dimension['label']}"
                    + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                    + ", os itens com maior volume de falhas foram: "
                    + ", ".join(f"{row['dimension']} ({row['failure']})" for row in top)
                    + "."
                )
        series = [
            {"label": row["dimension"], "value": row["failure"], "display_value": str(row["failure"])}
            for row in top
        ]
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"failure {dimension['label']}"),
            "title": f"Falhas por {dimension['label'].title()}",
            "cards": [
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                {"label": "Dimensoes", "value": str(len(rows)), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Falhas",
                    "series": series,
                }
            ],
        },
    }


async def _answer_generic_average_duration(
    *,
    question: str,
    profile: dict,
    mcp_session,
    call_tool,
    time_range: str,
    dimension: dict,
    filters: dict,
    any_filters: dict,
    filter_labels: list[str],
) -> dict | None:
    if dimension["kind"] == "job":
        start_field = profile.get("job_start_field")
        end_field = profile.get("job_end_field")
        unique_field = profile.get("job_execution_id_field")
    else:
        start_field = profile.get("workflow_start_field")
        end_field = profile.get("workflow_end_field")
        unique_field = profile.get("workflow_execution_id_field")
    if not start_field or not end_field:
        return None
    time_field = profile.get("workflow_start_field") or profile.get("primary_time_field")
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=_dimension_source_fields(dimension, profile) + [start_field, end_field],
        filters=filters,
        any_filters=any_filters,
        sort=f"{time_field}:desc" if time_field else None,
    )
    grouped = defaultdict(list)
    seen = set()
    for doc in docs:
        duration = _duration_seconds(doc, start_field, end_field)
        if duration is None:
            continue
        unique_value = str(_dig(doc, unique_field)) if unique_field and _dig(doc, unique_field) is not None else None
        for value in _dimension_values(doc, dimension):
            if dimension.get("exclude_bots") and "[bot]" in value.lower():
                continue
            if unique_value:
                dedupe_key = (value, unique_value)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
            grouped[value].append(duration)
    if not grouped:
        context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
        return {
            "answer": (
                f"{_emoji('duration')} Encontrei `0` execucoes validas para calcular duracao media em "
                f"{dimension['label']}{context} no periodo `{time_range}`."
            ),
            "dashboard": {
                "id": slugify_local(f"duration {dimension['label']}"),
                "title": f"Duracao Media por {dimension['label'].title()}",
                "cards": [
                    {"label": "Periodo", "value": time_range, "tone": "accent"},
                    {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                    {"label": "Dimensoes", "value": "0", "tone": "warning"},
                ],
                "sections": [],
            },
        }
    rows = [
        {"dimension": name, "avg_seconds": sum(values) / len(values), "count": len(values)}
        for name, values in grouped.items()
    ]
    rows.sort(key=lambda row: (row["avg_seconds"], row["dimension"]))
    top = rows[:10] if _wants_list_output(question) else rows[:5]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
    if _wants_list_output(question):
        answer = (
            f"{_emoji('duration')} Lista de {dimension['label']}{context} com menor duracao media no periodo `{time_range}`:\n"
            + _format_bullet_list([f"`{row['dimension']}` com media de `{_format_duration(row['avg_seconds'])}`" for row in top])
        )
    else:
        answer = (
            f"No ranking de {dimension['label']}{context}, os itens com menor duracao media foram: "
            + ", ".join(f"{row['dimension']} ({_format_duration(row['avg_seconds'])})" for row in top)
            + "."
        )
    return {
        "answer": answer,
        "dashboard": {
            "id": slugify_local(f"duration {dimension['label']}"),
            "title": f"Duracao Media por {dimension['label'].title()}",
            "cards": [
                {"label": "Periodo", "value": time_range, "tone": "accent"},
                {"label": "Filtro", "value": ", ".join(filter_labels) or "sem filtro", "tone": "accent"},
                {"label": "Dimensoes", "value": str(len(rows)), "tone": "accent"},
            ],
            "sections": [
                {
                    "type": "bar",
                    "title": "Duracao Media",
                    "series": [
                        {"label": row["dimension"], "value": round(row["avg_seconds"], 2), "display_value": _format_duration(row["avg_seconds"])}
                        for row in top
                    ],
                }
            ],
        },
    }


def slugify_local(value: str) -> str:
    text = _plain_text(value)
    text = text.replace(" ", "-")
    return "".join(ch for ch in text if ch.isalnum() or ch == "-").strip("-") or "dashboard"

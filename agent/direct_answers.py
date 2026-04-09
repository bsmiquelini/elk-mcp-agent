"""
Respostas diretas para perguntas recorrentes do MVP.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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
    available_workflows = _is_available_workflows_question(q)
    repository_count = _is_repository_count_question(q)
    analyst_lowest_success = _is_analyst_lowest_success_question(q)
    analyst_highest_success = _is_analyst_highest_success_question(q)
    average_build_job_duration = _is_average_build_job_duration_by_workflow_question(q)
    average_deploy_job_executions = _is_average_deploy_job_executions_by_workflow_question(q)

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
            profile=profile,
            schema=schema,
            mcp_session=mcp_session,
            call_tool=call_tool,
            time_range="7d",
            title="Analistas com Execucao de Workflows",
            answer_prefix="Nos ultimos 7 dias, encontrei",
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
    if "ate hoje" in q or "ate agora" in q or "historico" in q or "tudo" in q:
        return "365d"
    return default


def _is_executed_jobs_question(q: str) -> bool:
    mentions_job = any(term in q for term in ["job", "jobs", "check", "checks"])
    asks_listing = any(term in q for term in ["quais", "lista", "lista os", "mostre"])
    asks_execution = any(term in q for term in ["execut", "rod", "rodaram", "rodou"])
    filters = ["build", "deploy", "security", "scan", "java", "python", "typescript", "prd", "hml", "stg", "topico", "branch", "privado", "publico", "falha", "falhas", "sucesso", "taxa", "duracao", "tempo"]
    return mentions_job and asks_listing and asks_execution and not any(term in q for term in filters)


def _is_executed_workflows_question(q: str) -> bool:
    mentions_workflow = any(term in q for term in ["workflow", "workflows"])
    asks_listing = any(term in q for term in ["quais", "lista", "lista os", "mostre"])
    asks_execution = any(term in q for term in ["execut", "rod", "rodaram", "rodou"])
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "prd", "hml", "stg", "privado", "publico", "build", "deploy", "security", "scan"]
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
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "prd", "hml", "stg", "privado", "publico", "build", "deploy", "security", "scan"]
    return (
        "workflow" in q
        and not any(term in q for term in other_dimensions)
        and any(term in q for term in ["menos execut", "menor execu", "menos rod", "menos ocorreu", "menos teve execu"])
    )


def _is_most_executed_workflow_question(q: str) -> bool:
    other_dimensions = ["repositorio", "repositorios", "repo", "analista", "analistas", "linguagem", "linguagens", "topico", "topicos", "branch", "branches", "ambiente", "ambientes", "java", "python", "typescript", "prd", "hml", "stg", "privado", "publico", "build", "deploy", "security", "scan"]
    return (
        "workflow" in q
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
) -> list[dict]:
    counters = defaultdict(set) if unique_field else defaultdict(int)

    for doc in docs:
        group_values = _iter_dimension_values(_dig(doc, group_field))
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
        f"O workflow que {adjective} no periodo consultado foi `{chosen['group']}`, "
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
    exact_env = _infer_exact_environment_value(question)
    if exact_env and env_field:
        filters[env_field] = exact_env
        any_filters.pop(env_field, None)
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
        f"O {adjective} workflow encontrado{context} foi `{workflow_name}` no repositorio `{repo_name}`, "
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
        f"O analista que mais executou workflows{context} no periodo `{time_range}` foi `{top['actor']}`, "
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


def _compute_success_rate_rows(
    docs: list[dict],
    *,
    dimension_field: str,
    status_field: str,
    unique_field: str | None = None,
    actor_type_field: str | None = None,
    exclude_bots: bool = False,
) -> list[dict]:
    counters = defaultdict(lambda: {"total": 0, "success": 0, "failure": 0})
    seen = set()
    success_values = {"success", "completed"}
    failure_values = {"failure", "failed", "error", "timed_out"}

    for doc in docs:
        dimensions = _iter_dimension_values(_dig(doc, dimension_field))
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


async def _answer_distinct_actors(*, question: str, profile: dict, schema: dict, mcp_session, call_tool, time_range: str, title: str, answer_prefix: str) -> dict | None:
    actor_field = profile.get("actor_field")
    actor_type_field = profile.get("actor_type_field")
    if not actor_field:
        return None
    docs = await _fetch_documents(
        mcp_session,
        call_tool,
        time_range=time_range,
        fields=[actor_field, actor_type_field],
        sort=f"{profile.get('primary_time_field') or '@timestamp'}:desc",
    )
    actors = sorted({
        str(_dig(doc, actor_field))
        for doc in docs
        if _dig(doc, actor_field) and not _is_bot_doc(doc, actor_type_field, actor_field)
    })
    answer = f"{answer_prefix} `{len(actors)}` analistas que rodaram workflows."
    dashboard = {
        "id": "distinct_analysts",
        "title": title,
        "cards": [
            {"label": "Analistas", "value": str(len(actors)), "tone": "accent"},
            {"label": "Periodo", "value": time_range, "tone": "accent"},
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
    if any(term in q for term in ["disponiveis", "disponivel", "temos disponiveis", "temos disponivel"]):
        return "inventory"
    if any(term in q for term in ["menor taxa de sucesso", "pior taxa de sucesso", "menos sucesso"]):
        return "success_rate_bottom"
    if any(term in q for term in ["maior taxa de sucesso", "melhor taxa de sucesso", "mais sucesso"]):
        return "success_rate"
    if "taxa de falha" in q:
        return "failure_rate"
    if any(term in q for term in ["mais falharam", "mais falha", "mais falham", "mais falhou", "executado com falha", "volume de falhas", "maior volume de falhas"]):
        return "failure_count"
    if any(term in q for term in ["media de dur", "duracao media", "tempo medio", "media de execu"]):
        return "avg_duration"
    if any(term in q for term in ["quantos", "quantas"]):
        return "count"
    if any(term in q for term in ["menos execut", "menor volume", "menos rod", "menos ocorreu", "menos teve execu"]):
        return "volume_bottom"
    if any(term in q for term in ["mais execut", "maior volume", "mais rod", "mais ocorreu", "mais teve execu"]):
        return "volume"
    return None


def _extract_dimension_config(q: str, profile: dict) -> dict | None:
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
        for language in ["java", "python", "typescript"]:
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

    team_filters, team_labels = extract_team_filter(q, config, profile.get("repository_name_field"))
    filters.update(team_filters)
    labels.extend(team_labels)

    return filters, any_filters, labels


def _dimension_source_fields(dimension: dict, profile: dict) -> list[str]:
    fields = [dimension["field"], dimension.get("unique_field")]
    if dimension.get("exclude_bots"):
        fields.append(profile.get("actor_type_field"))
    return [field for field in fields if field]


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
    if dimension.get("exclude_bots"):
        rows = [row for row in rows if "[bot]" not in row["group"].lower()]
    if not rows:
        return _reformulate("Nao encontrei dados suficientes para montar o ranking solicitado.")
    rows.sort(key=lambda item: (item["count"], item["group"]))
    top = rows[:5] if order == "asc" else list(reversed(rows[-5:]))
    descriptor = "mais" if order == "desc" else "menos"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
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
        values.update(_iter_dimension_values(_dig(doc, dimension["field"])))
    if not values:
        return _reformulate("Nao encontrei dados suficientes para contar essa dimensao.")
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
        return _reformulate("Nao encontrei dados suficientes para contar as execucoes.")
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
        for value in _iter_dimension_values(_dig(doc, dimension["field"]))
        if value and not (dimension.get("exclude_bots") and "[bot]" in value.lower())
    })
    if not values:
        return _reformulate("Nao encontrei valores disponiveis para essa dimensao.")
    preview = values[:12]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
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
    )
    rows = [row for row in rows if row["total"] > 0]
    if not rows:
        return _reformulate("Nao encontrei dados suficientes para calcular taxa de sucesso.")
    rows.sort(key=lambda row: (row["success_rate"], row["total"], row["dimension"]))
    top = rows[:5] if order == "asc" else list(reversed(rows[-5:]))
    descriptor = "maior" if order == "desc" else "menor"
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
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
    )
    rows = [row for row in rows if row["total"] > 0]
    if not rows:
        return _reformulate("Nao encontrei dados suficientes para montar o ranking de falhas.")
    for row in rows:
        row["failure_rate"] = (row["failure"] / row["total"]) if row["total"] else 0
    if by_rate:
        rows.sort(key=lambda row: (row["failure_rate"], row["failure"], row["dimension"]), reverse=True)
        top = rows[:5]
        if _plain_text(question).startswith("qual"):
            first = top[0]
            answer = (
                f"O item com maior taxa de falha em {dimension['label']}"
                + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                + f" foi `{first['dimension']}` ({first['failure']}/{first['total']} = {_format_percent(first['failure'], first['total'])})."
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
        top = rows[:5]
        if _plain_text(question).startswith("qual"):
            first = top[0]
            answer = (
                f"O item com maior volume de falhas em {dimension['label']}"
                + (f" com filtro de {', '.join(filter_labels)}" if filter_labels else "")
                + f" foi `{first['dimension']}` ({first['failure']})."
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
        for value in _iter_dimension_values(_dig(doc, dimension["field"])):
            if dimension.get("exclude_bots") and "[bot]" in value.lower():
                continue
            if unique_value:
                dedupe_key = (value, unique_value)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
            grouped[value].append(duration)
    if not grouped:
        return _reformulate("Nao encontrei dados suficientes para calcular duracao media.")
    rows = [
        {"dimension": name, "avg_seconds": sum(values) / len(values), "count": len(values)}
        for name, values in grouped.items()
    ]
    rows.sort(key=lambda row: (row["avg_seconds"], row["dimension"]))
    top = rows[:5]
    context = f" com filtro de {', '.join(filter_labels)}" if filter_labels else ""
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

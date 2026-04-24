"""
Gera um catalogo cross-validatable com 800 perguntas no contexto de gestao
DevOps/GitHub. O catalogo e montado a partir dos dados atuais do Elasticsearch,
evitando listas fixas de arquitetura, topico, time, linguagem e branch.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "mcp_server") not in sys.path:
    sys.path.insert(0, str(ROOT / "mcp_server"))

from config_loader import load_config
from elastic_client import get_client, get_index


ARTIFACTS_DIR = ROOT / "artifacts"
JSON_PATH = ARTIFACTS_DIR / "department_question_catalog_800.json"
MD_PATH = ARTIFACTS_DIR / "department_question_catalog_800.md"
APP_TZ = ZoneInfo("America/Sao_Paulo")

GENERAL_PERIODS = [
    ("ultimos 7 dias", "7d"),
    ("ultimos 30 dias", "30d"),
    ("ultimos 90 dias", "90d"),
    ("ultimo semestre", "180d"),
    ("ultimo ano", "365d"),
]
FILTERED_PERIODS = [
    ("ultimos 30 dias", "30d"),
    ("ultimos 90 dias", "90d"),
    ("ultimo semestre", "180d"),
    ("ultimo ano", "365d"),
]
INVENTORY_DIMENSIONS = [
    ("quais arquiteturas existem no ambiente?", "inventory", "architecture"),
    ("quais topicos existem no ambiente?", "inventory", "topic"),
    ("quais linguagens existem no ambiente?", "inventory", "language"),
    ("quais branches existem no ambiente?", "inventory", "branch"),
    ("quais times existem no ambiente?", "inventory", "team"),
    ("quais workflows temos disponiveis ate hoje?", "inventory", "workflow"),
    ("quais repositorios temos disponiveis ate hoje?", "inventory", "repository"),
    ("quantos tipos de arquitetura existem no ambiente?", "count", "architecture"),
    ("quantos topicos diferentes existem no ambiente?", "count", "topic"),
    ("quantas linguagens diferentes existem no ambiente?", "count", "language"),
    ("quantas branches diferentes existem no ambiente?", "count", "branch"),
    ("quantos times diferentes existem no ambiente?", "count", "team"),
]


def plain_text(value: str) -> str:
    return str(value or "").strip().lower()


def dig(data: dict, field: str | None):
    if not field:
        return None
    node = data
    for part in field.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def document_time(doc: dict) -> datetime | None:
    return parse_iso(dig(doc, "workflow_run.run_started_at")) or parse_iso(dig(doc, "@timestamp"))


def team_from_repo_name(repo_name: str | None) -> str | None:
    if not repo_name:
        return None
    repo_slug = str(repo_name).split("/", 1)[-1]
    head = repo_slug.split("-", 1)[0].strip().lower()
    return head or None


def architectures_from_topics(value) -> list[str]:
    raw_topics = value if isinstance(value, list) else [value]
    result = []
    seen = set()
    for topic in raw_topics:
        normalized = plain_text(topic)
        for prefix in ("archtecture-", "architecture-"):
            if normalized.startswith(prefix):
                candidate = normalized[len(prefix) :]
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    result.append(candidate)
                break
    return result


def canonical_env(raw_value: str | None, config: dict) -> str | None:
    normalized = plain_text(raw_value)
    if not normalized:
        return None
    env_rules = config.get("domain", {}).get("semantic_rules", {}).get("environment_aliases", {})
    for env_key, rule in env_rules.items():
        exact_values = {plain_text(item) for item in rule.get("exact_values", [])}
        aliases = {plain_text(item) for item in rule.get("aliases", [])}
        if normalized in exact_values or normalized in aliases:
            return env_key.upper()
    return str(raw_value).upper()


def pick_top(counter: Counter, limit: int) -> list[str]:
    rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [value for value, _ in rows[:limit]]


def load_documents() -> list[dict]:
    config = load_config(str(ROOT / "config.yaml"))
    client = get_client(config)
    response = client.search(index=get_index(config), size=5000, sort=["_doc"])
    return [hit["_source"] for hit in response["hits"]["hits"]]


def discover_context(docs: list[dict], config: dict) -> dict:
    architecture_counter = Counter()
    team_counter = Counter()
    env_counter = Counter()
    language_counter = Counter()
    topic_counter = Counter()
    branch_counter = Counter()
    workflow_counter = Counter()
    repo_counter = Counter()
    language_display: dict[str, str] = {}

    for doc in docs:
        for architecture in architectures_from_topics(dig(doc, "repository.topics")):
            architecture_counter[architecture] += 1

        team = team_from_repo_name(dig(doc, "repository.full_name") or dig(doc, "repository.name"))
        if team:
            team_counter[team] += 1

        env = canonical_env(dig(doc, "deployment.environment") or dig(doc, "deployment_status.environment"), config)
        if env:
            env_counter[env] += 1

        language = plain_text(dig(doc, "repository.language"))
        if language:
            language_counter[language] += 1
            language_display.setdefault(language, str(dig(doc, "repository.language")))

        raw_topics = dig(doc, "repository.topics") or []
        if not isinstance(raw_topics, list):
            raw_topics = [raw_topics]
        for topic in raw_topics:
            normalized = plain_text(topic)
            if not normalized or normalized.startswith("archtecture-") or normalized.startswith("architecture-"):
                continue
            topic_counter[normalized] += 1

        branch = plain_text(dig(doc, "workflow_run.head_branch"))
        if branch:
            branch_counter[branch] += 1

        workflow_name = str(dig(doc, "workflow_run.name") or "").strip()
        if workflow_name:
            workflow_counter[workflow_name] += 1

        repo_name = str(dig(doc, "repository.full_name") or "").strip()
        if repo_name:
            repo_counter[repo_name] += 1

    latest_dt = max((document_time(doc) for doc in docs if document_time(doc)), default=None)
    latest_day = latest_dt.astimezone(APP_TZ).date() if latest_dt else datetime.now(APP_TZ).date()
    rolling_30_start = latest_day - timedelta(days=29)
    absolute_day = latest_day.isoformat()
    absolute_range = f"{rolling_30_start.isoformat()}..{latest_day.isoformat()}"
    absolute_phrase = f"entre {rolling_30_start.isoformat()} e {latest_day.isoformat()}"

    filtered_periods = FILTERED_PERIODS + [(absolute_phrase, absolute_range)]
    general_periods = GENERAL_PERIODS + [
        (f"em {absolute_day}", absolute_day),
        (absolute_phrase, absolute_range),
    ]

    workflow_types = list(config.get("domain", {}).get("semantic_rules", {}).get("workflow_categories", {}).keys())
    if not workflow_types:
        workflow_types = ["build", "deploy", "rollback", "security", "test", "gate"]

    envs = pick_top(env_counter, 4)
    if not envs:
        envs = [key.upper() for key in config.get("domain", {}).get("semantic_rules", {}).get("environment_aliases", {}).keys()]

    languages = [
        {"display": language_display.get(language, language.title()), "value": language}
        for language in pick_top(language_counter, 6)
    ]

    return {
        "architectures": pick_top(architecture_counter, 6),
        "teams": pick_top(team_counter, 6),
        "envs": envs,
        "languages": languages,
        "topics": pick_top(topic_counter, 8),
        "branches": pick_top(branch_counter, 6),
        "workflow_types": workflow_types[:6],
        "workflows": pick_top(workflow_counter, 5),
        "repositories": pick_top(repo_counter, 5),
        "general_periods": general_periods,
        "filtered_periods": filtered_periods,
    }


def build_catalog(context: dict) -> list[dict]:
    items: list[dict] = []

    def add(category: str, question: str, **spec_fields) -> None:
        items.append({"category": category, "question": question, **spec_fields})

    def time_clause(phrase: str) -> str:
        normalized = plain_text(phrase)
        if normalized.startswith(("em ", "entre ")):
            return phrase
        if normalized.startswith(("ultimo ", "ultima ")):
            return f"no {phrase}"
        return f"nos {phrase}"

    for phrase, time_range in context["general_periods"]:
        add("executive-overview", f"quantos workflows rodaram {time_clause(phrase)}?", kind="execution_total", dimension="workflow", time_range=time_range)
        add("executive-overview", f"quantos jobs rodaram {time_clause(phrase)}?", kind="execution_total", dimension="job", time_range=time_range)
        add("executive-overview", f"qual a porcentagem de falha e sucesso nas execucoes {time_clause(phrase)}?", kind="status_mix", dimension="workflow", time_range=time_range)
        add("executive-overview", f"quais workflows mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", time_range=time_range)
        add("executive-overview", f"quais repositorios mais executaram workflows {time_clause(phrase)}?", kind="rank_volume", dimension="repository", time_range=time_range)

    for question, kind, dimension in INVENTORY_DIMENSIONS:
        add("inventory", question, kind=kind, dimension=dimension, time_range="365d")

    for env in context["envs"]:
        for phrase, time_range in context["filtered_periods"]:
            add("environment", f"quais workflows mais executaram em {env} {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", env=env, time_range=time_range)
            add("environment", f"quais workflows com maior volume de falhas em {env} {time_clause(phrase)}?", kind="rank_failure", dimension="workflow", env=env, time_range=time_range)
            add("environment", f"quais repositorios mais executaram workflows em {env} {time_clause(phrase)}?", kind="rank_volume", dimension="repository", env=env, time_range=time_range)
            add("environment", f"qual a porcentagem de falha e sucesso dos deploys em {env} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", env=env, workflow_type="deploy", time_range=time_range)
            add("environment", f"quais deploys falharam em {env} {time_clause(phrase)}?", kind="recent_list", dimension="repository", env=env, workflow_type="deploy", failure_only=True, time_range=time_range, list_mode=True)

    for architecture in context["architectures"]:
        for phrase, time_range in context["filtered_periods"]:
            add("architecture", f"quais workflows da arquitetura {architecture} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", architecture=architecture, time_range=time_range)
            add("architecture", f"quais workflows da arquitetura {architecture} mais falharam {time_clause(phrase)}?", kind="rank_failure", dimension="workflow", architecture=architecture, time_range=time_range)
            add("architecture", f"quais workflows da arquitetura {architecture} tiveram maior taxa de sucesso {time_clause(phrase)}?", kind="rank_success", dimension="workflow", architecture=architecture, time_range=time_range)
            add("architecture", f"quais repositorios da arquitetura {architecture} mais executaram workflows {time_clause(phrase)}?", kind="rank_volume", dimension="repository", architecture=architecture, time_range=time_range)
            add("architecture", f"quantos repositorios da arquitetura {architecture} tiveram execucoes {time_clause(phrase)}?", kind="count", dimension="repository", architecture=architecture, time_range=time_range)
            add("architecture", f"qual a porcentagem de falha e sucesso nas execucoes da arquitetura {architecture} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", architecture=architecture, time_range=time_range)

    for team in context["teams"]:
        for phrase, time_range in context["filtered_periods"]:
            add("team", f"quais workflows do time {team} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", team=team, time_range=time_range)
            add("team", f"quais workflows do time {team} mais falharam {time_clause(phrase)}?", kind="rank_failure", dimension="workflow", team=team, time_range=time_range)
            add("team", f"quais repositorios do time {team} mais executaram workflows {time_clause(phrase)}?", kind="rank_volume", dimension="repository", team=team, time_range=time_range)
            add("team", f"qual a porcentagem de falha e sucesso do time {team} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", team=team, time_range=time_range)
            add("team", f"quantos workflows do time {team} rodaram {time_clause(phrase)}?", kind="execution_total", dimension="workflow", team=team, time_range=time_range)

    for language in context["languages"]:
        display = language["display"]
        value = language["value"]
        for phrase, time_range in context["filtered_periods"]:
            add("language", f"quais workflows {display} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", language=value, time_range=time_range)
            add("language", f"quais repositorios {display} mais executaram workflows {time_clause(phrase)}?", kind="rank_volume", dimension="repository", language=value, time_range=time_range)
            add("language", f"quais workflows {display} tiveram maior taxa de sucesso {time_clause(phrase)}?", kind="rank_success", dimension="workflow", language=value, time_range=time_range)
            add("language", f"qual a porcentagem de falha e sucesso dos workflows {display} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", language=value, time_range=time_range)
            add("language", f"quantos repositorios {display} tiveram execucoes {time_clause(phrase)}?", kind="count", dimension="repository", language=value, time_range=time_range)

    for workflow_type in context["workflow_types"]:
        for phrase, time_range in context["filtered_periods"]:
            add("workflow-type", f"quais workflows de {workflow_type} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", workflow_type=workflow_type, time_range=time_range)
            add("workflow-type", f"quais workflows de {workflow_type} mais falharam {time_clause(phrase)}?", kind="rank_failure", dimension="workflow", workflow_type=workflow_type, time_range=time_range)
            add("workflow-type", f"quais jobs de {workflow_type} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="job", workflow_type=workflow_type, time_range=time_range)
            add("workflow-type", f"qual a porcentagem de falha e sucesso dos workflows de {workflow_type} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", workflow_type=workflow_type, time_range=time_range)

    for topic in context["topics"]:
        for phrase, time_range in context["filtered_periods"]:
            add("topic", f"quais repositorios do topico {topic} mais executaram workflows {time_clause(phrase)}?", kind="rank_volume", dimension="repository", topic=topic, time_range=time_range)
            add("topic", f"quais repositorios do topico {topic} tiveram maior volume de falhas {time_clause(phrase)}?", kind="rank_failure", dimension="repository", topic=topic, time_range=time_range)
            add("topic", f"quantos repositorios do topico {topic} tiveram execucoes de workflows {time_clause(phrase)}?", kind="count", dimension="repository", topic=topic, time_range=time_range)
            add("topic", f"quais workflows do topico {topic} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", topic=topic, time_range=time_range)
            add("topic", f"qual a porcentagem de falha e sucesso dos repositorios do topico {topic} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", topic=topic, time_range=time_range)

    for branch in context["branches"]:
        for phrase, time_range in context["filtered_periods"]:
            add("branch", f"quais workflows da branch {branch} mais executaram {time_clause(phrase)}?", kind="rank_volume", dimension="workflow", branch=branch, time_range=time_range)
            add("branch", f"quais repositorios da branch {branch} mais falharam {time_clause(phrase)}?", kind="rank_failure", dimension="repository", branch=branch, time_range=time_range)
            add("branch", f"qual a porcentagem de falha e sucesso da branch {branch} {time_clause(phrase)}?", kind="status_mix", dimension="workflow", branch=branch, time_range=time_range)
            add("branch", f"quantos workflows rodaram na branch {branch} {time_clause(phrase)}?", kind="execution_total", dimension="workflow", branch=branch, time_range=time_range)

    noisy_items = []
    absolute_range = next((item for item in context["filtered_periods"] if ".." in item[1]), None)
    if context["architectures"]:
        noisy_items.append(
            {
                "category": "noisy-language",
                "question": f"quais esteiras de {context['architectures'][0]} mais falharam no ultimo semestre",
                "kind": "rank_failure",
                "dimension": "workflow",
                "architecture": context["architectures"][0],
                "time_range": "180d",
            }
        )
    if context["topics"]:
        noisy_items.append(
            {
                "category": "noisy-language",
                "question": f"qual a porcentagem de falha e sucesso dos repos do topico {context['topics'][0]} no ultimo ano",
                "kind": "status_mix",
                "dimension": "workflow",
                "topic": context["topics"][0],
                "time_range": "365d",
            }
        )
    if context["teams"]:
        noisy_items.append(
            {
                "category": "noisy-language",
                "question": f"qual porcentagem de falha e sucesso em deploys do time {context['teams'][0]} no ultimo ano",
                "kind": "status_mix",
                "dimension": "workflow",
                "team": context["teams"][0],
                "workflow_type": "deploy",
                "time_range": "365d",
            }
        )
    if absolute_range:
        noisy_items.append(
            {
                "category": "noisy-language",
                "question": f"quais as esteiras que mais apresentam falhas {absolute_range[0]}?",
                "kind": "rank_failure",
                "dimension": "workflow",
                "time_range": absolute_range[1],
            }
        )
    items.extend(noisy_items)

    categories_in_order: list[str] = []
    buckets: dict[str, list[dict]] = {}
    seen = set()
    for item in items:
        key = plain_text(item["question"])
        if key in seen:
            continue
        seen.add(key)
        category = item["category"]
        if category not in buckets:
            buckets[category] = []
            categories_in_order.append(category)
        buckets[category].append(item)

    total_unique = sum(len(bucket) for bucket in buckets.values())
    if total_unique < 800:
        raise ValueError(f"Catalogo insuficiente: {total_unique} perguntas unicas.")

    final_items: list[dict] = []
    indexes = {category: 0 for category in categories_in_order}
    while len(final_items) < 800:
        progressed = False
        for category in categories_in_order:
            bucket = buckets[category]
            index = indexes[category]
            if index >= len(bucket):
                continue
            final_items.append(bucket[index])
            indexes[category] += 1
            progressed = True
            if len(final_items) == 800:
                break
        if not progressed:
            break

    for index, item in enumerate(final_items, start=1):
        item["id"] = index

    return final_items


def write_json(items: list[dict]) -> None:
    JSON_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(items: list[dict]) -> None:
    lines = [
        "# Catalogo de 800 Perguntas DevOps/GitHub",
        "",
        "Gerado com base nos valores atualmente indexados no Elasticsearch.",
        "",
    ]
    grouped: dict[str, list[dict]] = {}
    ordered_categories: list[str] = []
    for item in items:
        category = item["category"]
        if category not in grouped:
            grouped[category] = []
            ordered_categories.append(category)
        grouped[category].append(item)

    for category in ordered_categories:
        lines.append(f"## {category}")
        lines.append("")
        for item in grouped[category]:
            lines.append(f"{item['id']}. {item['question']}")
        lines.append("")

    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(str(ROOT / "config.yaml"))
    docs = load_documents()
    context = discover_context(docs, config)
    items = build_catalog(context)
    write_json(items)
    write_markdown(items)
    print(f"OK: {len(items)} perguntas geradas.")
    print(f"JSON: {JSON_PATH}")
    print(f"MD: {MD_PATH}")


if __name__ == "__main__":
    main()

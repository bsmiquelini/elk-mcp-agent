"""
Regras semânticas configuráveis para interpretar perguntas de negócio.
"""

from __future__ import annotations

import re
import unicodedata


def plain_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def get_rules(config: dict) -> dict:
    return config.get("domain", {}).get("semantic_rules", {})


def extract_pipeline_type_patterns(question: str, config: dict) -> list[str]:
    q = plain_text(question)
    rules = get_rules(config).get("workflow_categories", {})
    patterns = []
    for rule in rules.values():
        aliases = [plain_text(alias) for alias in rule.get("aliases", [])]
        if any(alias in q for alias in aliases):
            for token in rule.get("contains", []):
                patterns.extend([f"*{token.lower()}*", f"*{token.upper()}*", f"*{token.title()}*"])
    deduped = []
    seen = set()
    for pattern in patterns:
        if pattern not in seen:
            seen.add(pattern)
            deduped.append(pattern)
    return deduped


def extract_architecture_filter(question: str, config: dict, topic_field: str | None) -> tuple[dict, list[str]]:
    if not topic_field:
        return {}, []

    q = plain_text(question)
    rules = get_rules(config).get("architecture", {})
    aliases = [plain_text(alias) for alias in rules.get("aliases", ["arquitetura", "arquiteturas", "architecture", "architectures"])]
    explicit_aliases = [alias for alias in aliases if alias not in {"esteira", "esteiras", "workflow", "workflows", "pipeline", "pipelines"}]
    value = _extract_named_value(q, explicit_aliases) if _contains_alias(q, explicit_aliases) else None
    if not value:
        implicit_matches = re.findall(
            r"(?:esteiras?|workflows?|pipelines?|repositorios?|repos?)\s+(?:de|do|da|dos|das)\s+([a-z0-9._/-]+)",
            q,
        )
        for candidate in implicit_matches:
            if candidate not in _NAMED_VALUE_STOPWORDS:
                value = candidate
                break
    if not value:
        return {}, []

    templates = rules.get("value_templates", ["archtecture-{value}"])
    values = [template.format(value=value) for template in templates]
    return {topic_field: values}, [f"arquitetura {value}"]


def extract_team_filter(question: str, config: dict, repo_field: str | None) -> tuple[dict, list[str]]:
    if not repo_field:
        return {}, []

    q = plain_text(question)
    rules = get_rules(config).get("team", {})
    aliases = [plain_text(alias) for alias in rules.get("aliases", ["time", "vskey", "value stream", "squad"])]
    team_name = _extract_named_value(q, aliases)
    if not team_name:
        return {}, []

    patterns = []
    for template in rules.get("repo_patterns", ["*/{value}-*", "{value}-*"]):
        patterns.append(template.format(value=team_name))
    return {repo_field: patterns}, [f"time {team_name}"]


def extract_environment_semantics(question: str, config: dict, profile: dict) -> tuple[dict, dict, list[str]]:
    rules = get_rules(config).get("environment_aliases", {})
    q = plain_text(question)
    matched_key = None
    matched_rule = None
    for key, rule in rules.items():
        aliases = [plain_text(alias) for alias in rule.get("aliases", [])]
        if _contains_alias(q, aliases):
            matched_key = key
            matched_rule = rule
            break
    if not matched_rule:
        return {}, {}, []

    filters = {}
    any_filters = {}
    labels = [matched_rule.get("label", matched_key.upper())]

    exact_values = matched_rule.get("exact_values", [])
    contains_tokens = matched_rule.get("contains_tokens", [])
    resolved_env_field = profile.get("environment_field")
    if resolved_env_field and exact_values:
        filters[resolved_env_field] = exact_values
        return filters, any_filters, labels

    for field_name in matched_rule.get("field_preferences", []):
        resolved_field = profile.get(field_name) if field_name.endswith("_field") else field_name
        if not resolved_field:
            continue
        values = []
        if field_name in {"environment_field", "deployment.environment", "deployment_status.environment"}:
            values.extend(exact_values)
        values.extend(_wildcards_for_tokens(contains_tokens))
        if values:
            any_filters[resolved_field] = _dedupe(values)

    return filters, any_filters, labels


def _wildcards_for_tokens(tokens: list[str]) -> list[str]:
    values = []
    for token in tokens:
        values.extend([f"*{token.lower()}*", f"*{token.upper()}*", f"*{token.title()}*"])
    return values


def _extract_named_value(question: str, aliases: list[str]) -> str | None:
    for alias in aliases:
        pattern = rf"{re.escape(alias)}(?:\s+de|\s+do|\s+da|\s+dos|\s+das)?\s+([a-z0-9._/-]+)"
        match = re.search(pattern, question)
        if match:
            candidate = match.group(1)
            if candidate not in _NAMED_VALUE_STOPWORDS:
                return candidate
    return None


def _contains_alias(question: str, aliases: list[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9_-]){re.escape(alias)}(?![a-z0-9_-])", question) for alias in aliases)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


_NAMED_VALUE_STOPWORDS = {
    "que",
    "ja",
    "executaram",
    "executou",
    "rodaram",
    "rodou",
    "tiveram",
    "teve",
    "mais",
    "menos",
    "maior",
    "menor",
    "ultimo",
    "ultimos",
    "ultima",
    "ultimas",
    "falharam",
    "falhou",
    "falha",
    "falhas",
    "sucesso",
    "deploy",
    "build",
    "rollback",
    "security",
    "scan",
    "gate",
    "approval",
    "test",
    "tests",
    "workflow",
    "workflows",
    "esteira",
    "esteiras",
    "pipeline",
    "pipelines",
    "trabalham",
    "trabalha",
    "trabalhando",
    "entrega",
    "primeiro",
    "primeira",
    "apresenta",
    "apresentam",
    "erro",
    "erros",
    "topico",
    "topicos",
    "topic",
    "topics",
    "linguagem",
    "linguagens",
    "tecnologia",
    "tecnologias",
    "time",
    "times",
    "squad",
    "squads",
    "vskey",
    "vskeys",
    "branch",
    "branches",
    "repositorio",
    "repositorios",
    "repo",
    "repos",
    "existe",
    "existem",
    "existir",
    "existentes",
    "disponivel",
    "disponiveis",
    "ambiente",
    "ambientes",
    "hoje",
    "atual",
    "atuais",
    "atualmente",
    "diferente",
    "diferentes",
    "distinto",
    "distintos",
    "distinta",
    "distintas",
}

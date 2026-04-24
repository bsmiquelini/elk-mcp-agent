"""
Monta o system prompt compacto para caber no contexto do modelo.
"""


def build_system_prompt(config: dict, schema: dict) -> str:
    domain    = config.get("domain", {})
    vocab     = domain.get("vocabulary", {})
    semantic_rules = domain.get("semantic_rules", {})
    hints     = domain.get("field_semantics", {})
    profile   = schema.get("profile", {})
    nested_paths = schema.get("nested_paths", [])
    nested_paths_text = ", ".join(nested_paths) if nested_paths else "nenhum"

    fields_summary  = _summarize_fields(schema)
    vocab_summary   = _summarize_vocab(vocab)
    semantic_summary = _summarize_semantic_rules(semantic_rules)
    hints_summary   = _summarize_hints(hints, schema)

    return f"""Você é um assistente de análise de workflows do GitHub no Elasticsearch. Responda em português, de forma objetiva.
Use APENAS dados retornados pelas tools. Nunca invente valores.

# Índice: {schema.get("index")} | {schema.get("total_docs")} docs | {schema.get("total_fields")} campos

# Campos nested detectados
{nested_paths_text}

# Campos sugeridos por conceito
Tempo principal: {profile.get("primary_time_field") or "não inferido"}
Workflow: {profile.get("workflow_name_field") or "não inferido"}
Status principal: {profile.get("workflow_status_field") or "não inferido"}
Check/job: {profile.get("job_name_field") or "não inferido"}
Status de check/job: {profile.get("job_status_field") or "não inferido"}
Repositório: {profile.get("repository_name_field") or "não inferido"}
Linguagem: {profile.get("repository_language_field") or "não inferido"}
Deploy: {profile.get("deploy_indicator_field") or "não inferido"}
Ambiente: {profile.get("environment_field") or "não inferido"}

# Campos disponíveis
{fields_summary}

# Valores conhecidos (amostra)
{_summarize_samples(schema.get("sample_values", {}))}

# Semântica de campos
{hints_summary}

# Vocabulário de negócio
{vocab_summary}

# Regras semânticas configuráveis
{semantic_summary}

# Tools disponíveis e quando usar

**explore_field(field, time_range, time_field, filters, size)**
→ Use ANTES de filtrar quando não souber os valores de um campo.
→ Para campos dentro de {nested_paths_text}, lembre que os valores reais podem variar por job.
→ `time_range` aceita relativo (`7d`), dia absoluto (`2026-04-23`) e intervalo absoluto (`2026-04-01..2026-04-23`).

**aggregate(metric, field, group_by, time_range, time_field, filters, nested_filter, interval, size)**
→ Métricas: count | avg | sum | min | max | percentiles | stats | cardinality | date_histogram
→ Para contar tipos distintos de um campo use metric='cardinality'.
→ Para ranking use group_by com metric='count'.
→ A tool resolve automaticamente a variante agregável do campo (ex: `.keyword`) quando necessário.
→ Se o campo ou filtro estiver dentro de {nested_paths_text}, use nested_filter.
→ Use `time_field` quando a pergunta depender de um campo temporal específico como `workflow_run.run_started_at`.

**search(filters, nested_filters, time_range, time_field, fields, sort, limit)**
→ Para buscar documentos específicos.
→ `time_range` aceita relativo (`30d`), dia absoluto (`2026-04-23`) e intervalo absoluto (`2026-04-01..2026-04-23`).

# Padrões úteis
→ Para "taxa de sucesso e falha", prefira `aggregate(metric='count', field='<campo de status>', group_by='<campo de status>', ...)`.
→ Para "problemas recorrentes", prefira 30d ou 90d se o usuário não informar período.
→ Para perguntas de build, procure primeiro em campos como `check_run.name` ou `jobs.name`.
→ Para perguntas de deploy, procure primeiro em `deployment.*` e depois em nomes de workflow/check contendo deploy.

# Regras
1. Os caminhos nested detectados foram: {nested_paths_text}.
2. Para filtros em campos simples use filters. Para filtros em campos nested use nested_filter ou nested_filters.
3. Não assuma campos fixos. Use os campos sugeridos acima apenas como ponto de partida e confirme com o schema.
4. Não assuma `.keyword` manualmente; a tool resolve isso quando o campo tiver subcampo agregável.
5. Para "quantos tipos de X" use metric='cardinality', field='X'.
6. Para "quais são os X" use metric='count', group_by='X'.
7. Se não souber os valores de um campo, chame explore_field primeiro.
8. Para "último workflow que rodou", use search com sort='{profile.get("primary_time_field") or config.get("elasticsearch", {}).get("time_field", "@timestamp")}:desc' e limit=1.
9. Para "taxa de sucesso e falha", agrupe pelo melhor campo de status disponível e calcule percentuais a partir das contagens.
10. Para perguntas sobre falhas recorrentes de build, se existir campo de check/job use-o; caso contrário, deixe claro a limitação.
11. Se o usuário pedir recorrência sem período explícito, use 30d ou 90d em vez do default curto.
12. Quando houver campos de deploy (`deployment.task`, `deployment.environment`, `deployment_status.state` ou equivalentes), prefira-os para perguntas de deploy.
13. Duração está em ms apenas se existir campo de duração; confirme pelo schema antes de converter.
14. Apresente tabelas e gráfico de barras ASCII para rankings:
   repo-a  ████████░░░░  82 (45%)
   repo-b  ████░░░░░░░░  41 (22%)
15. Use ✅ saudável | ⚠ atenção | 🔴 crítico conforme thresholds:
   Taxa de falha: ✅ <5% | ⚠ >10% | 🔴 >15%
   Duração média: ✅ <10min | ⚠ >20min | 🔴 >30min
16. Se a pergunta correlacionar múltiplos campos de check/job sem nested paths ou sem granularidade suficiente, deixe claro que o resultado é aproximado em nível de documento/evento.
"""


def _summarize_fields(schema: dict) -> str:
    fields = schema.get("fields", {})
    lines  = []
    for name, meta in sorted(fields.items()):
        exact = meta.get("exact_field")
        extra = f" | exato={exact}" if exact and exact != name else ""
        lines.append(f"  {name}: {meta.get('type','?')}{extra}")
    return "\n".join(lines)


def _summarize_samples(samples: dict) -> str:
    lines = []
    for field, values in samples.items():
        if field == "build_id":
            continue
        lines.append(f"  {field}: {', '.join(str(v) for v in values[:6])}")
    return "\n".join(lines)


def _summarize_hints(hints: dict, schema: dict) -> str:
    fields = schema.get("fields", {})
    lines = []
    for field, meta in hints.items():
        if field not in fields:
            continue
        desc = meta.get("description", "")[:120]
        lines.append(f"  {field}: {desc}")
    return "\n".join(lines)


def _summarize_vocab(vocab: dict) -> str:
    lines = []
    for term, meaning in vocab.items():
        lines.append(f"  '{term}' → {meaning}")
    return "\n".join(lines)


def _summarize_semantic_rules(rules: dict) -> str:
    lines = []
    architecture = rules.get("architecture", {})
    if architecture:
        lines.append(
            "  arquitetura: usa os templates "
            + ", ".join(architecture.get("value_templates", []))
        )
    team = rules.get("team", {})
    if team:
        lines.append(
            "  time/vskey: deriva pelo prefixo do repositório com padrões "
            + ", ".join(team.get("repo_patterns", []))
        )
    environments = rules.get("environment_aliases", {})
    for env_name, env_rule in environments.items():
        contains = ", ".join(env_rule.get("contains_tokens", []))
        lines.append(f"  {env_name}: aliases em nomes/ambiente como {contains}")
    categories = rules.get("workflow_categories", {})
    for category, rule in categories.items():
        tokens = ", ".join(rule.get("contains", []))
        lines.append(f"  categoria {category}: procura tokens {tokens}")
    return "\n".join(lines) if lines else "  nenhuma"

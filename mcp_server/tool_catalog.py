"""
Catálogo de tools MCP e despachantes.
"""

from __future__ import annotations

from mcp.types import Tool

from tools import aggregate, discover_schema, explore_field, search


def list_tool_specs() -> list[Tool]:
    return [
        Tool(
            name="discover_schema",
            description=(
                "Descobre o schema completo do índice Elasticsearch: campos, tipos, "
                "campos nested e amostra de valores. Execute no início para entender "
                "o que está disponível nos dados."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="explore_field",
            description=(
                "Descobre os valores únicos de qualquer campo do índice, incluindo "
                "workflow, check_run, deployment e repository. Use quando ainda não "
                "souber os valores exatos antes de filtrar."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Campo a explorar. Ex: check_run.name, workflow_run.status, deployment.environment, repository.topics",
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Período. Ex: 1d, 7d, 30d, 90d",
                        "default": "30d",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filtros de contexto {campo: valor}",
                        "default": {},
                    },
                    "size": {
                        "type": "integer",
                        "description": "Máximo de valores retornados",
                        "default": 200,
                    },
                },
                "required": ["field"],
            },
        ),
        Tool(
            name="aggregate",
            description=(
                "Executa agregações arbitrárias: count, avg, sum, min, max, percentiles, "
                "cardinality, stats e date_histogram. Suporta agrupamento por qualquer "
                "campo e filtros contextuais."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "Tipo de métrica: count | avg | sum | min | max | percentiles | cardinality | stats | date_histogram",
                    },
                    "field": {
                        "type": "string",
                        "description": "Campo alvo da métrica. Ex: workflow_run.conclusion, deployment_status.state, repository.name",
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Campo para agrupar resultados. Ex: repository.name, workflow_run.name, check_run.name, deployment.environment",
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Período. Ex: 1d, 7d, 30d, 90d",
                        "default": "7d",
                    },
                    "filters": {
                        "type": "object",
                        "description": "Filtros simples {campo: valor ou [valores]}",
                        "default": {},
                    },
                    "any_filters": {
                        "type": "object",
                        "description": "Filtros alternativos em OR entre campos {campo: valor ou [valores]}",
                        "default": {},
                    },
                    "nested_filter": {
                        "type": "object",
                        "description": "Filtro em campo nested quando existir",
                        "default": {},
                    },
                    "interval": {
                        "type": "string",
                        "description": "Para date_histogram: day | week | month",
                    },
                    "size": {
                        "type": "integer",
                        "description": "Máximo de buckets no group_by",
                        "default": 50,
                    },
                    "percentiles": {
                        "type": "array",
                        "description": "Percentis a calcular. Default: [50, 75, 90, 95, 99]",
                        "items": {"type": "number"},
                    },
                },
                "required": ["metric", "field"],
            },
        ),
        Tool(
            name="search",
            description=(
                "Busca documentos com filtros livres, suporte a wildcard, ordenação, "
                "seleção de campos e nested quando existir."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "description": "Filtros em campos não nested {campo: valor ou [valores]}",
                        "default": {},
                    },
                    "any_filters": {
                        "type": "object",
                        "description": "Filtros alternativos em OR entre campos {campo: valor ou [valores]}",
                        "default": {},
                    },
                    "nested_filters": {
                        "type": "object",
                        "description": "Filtros em campos nested quando existirem",
                        "default": {},
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Período. Ex: 1d, 7d, 30d, 90d",
                        "default": "7d",
                    },
                    "fields": {
                        "type": "array",
                        "description": "Campos a retornar. Omitir retorna todos.",
                        "items": {"type": "string"},
                    },
                    "sort": {
                        "type": "string",
                        "description": "Ordenação: campo:asc ou campo:desc. Ex: @timestamp:desc",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Máximo de documentos por página (max 200)",
                        "default": 10,
                    },
                    "search_after": {
                        "type": "array",
                        "description": "Cursor retornado em next_page para paginação",
                        "items": {},
                    },
                },
                "required": [],
            },
        ),
    ]


def build_handlers(config: dict) -> dict:
    return {
        "discover_schema": lambda a: discover_schema(config),
        "explore_field": lambda a: explore_field(
            config,
            field=a["field"],
            time_range=a.get("time_range"),
            filters=a.get("filters", {}),
            size=a.get("size", 200),
        ),
        "aggregate": lambda a: aggregate(
            config,
            metric=a["metric"],
            field=a["field"],
            group_by=a.get("group_by"),
            time_range=a.get("time_range"),
            filters=a.get("filters", {}),
            any_filters=a.get("any_filters", {}),
            interval=a.get("interval"),
            nested_filter=a.get("nested_filter", {}),
            size=a.get("size", 50),
            percentiles=a.get("percentiles"),
        ),
        "search": lambda a: search(
            config,
            filters=a.get("filters", {}),
            any_filters=a.get("any_filters", {}),
            nested_filters=a.get("nested_filters", {}),
            time_range=a.get("time_range"),
            fields=a.get("fields"),
            sort=a.get("sort"),
            limit=a.get("limit", 10),
            search_after=a.get("search_after"),
        ),
    }

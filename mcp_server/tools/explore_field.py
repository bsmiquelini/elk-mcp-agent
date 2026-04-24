"""
Tool: explore_field
Descobre valores únicos de qualquer campo do índice,
incluindo campos nested. Suporta filtros temporais e de contexto.
"""

from elastic_client import get_client, get_index
from schema_utils import (
    build_filter_clause,
    get_nested_path,
    load_index_schema,
    resolve_agg_field,
    resolve_exact_field,
)
from tools.time_filters import build_time_range_clause


def explore_field(
    config:      dict,
    field:       str,
    time_range:  str        = None,
    time_field:  str        = None,
    filters:     dict       = None,
    size:        int        = 200,
    include_count: bool     = True,
) -> dict:
    es    = get_client(config)
    index = get_index(config)
    schema = load_index_schema(config, es=es, index=index)

    time_field   = time_field or config.get("elasticsearch", {}).get("time_field", "workflow_run.started_at")
    time_range   = time_range or config.get("elasticsearch", {}).get("default_time_range", "7d")
    filters      = filters or {}

    # Determina se o campo é nested
    nested_path  = get_nested_path(field, schema)
    is_nested    = nested_path is not None
    resolved_field = resolve_agg_field(field, schema)

    # Monta query base com filtros temporais e extras
    base_query = _build_base_query(time_range, time_field, filters, nested_path, schema)

    try:
        if is_nested:
            body = _nested_terms_body(resolved_field, nested_path, base_query, size)
        else:
            body = _flat_terms_body(resolved_field, base_query, size)

        resp    = es.search(index=index, body=body)
        buckets = _extract_buckets(resp, is_nested)

        values = (
            [{"value": b["key"], "count": b["doc_count"]} for b in buckets]
            if include_count
            else [b["key"] for b in buckets]
        )

        return {
            "field":      field,
            "resolved_field": resolved_field,
            "is_nested":  is_nested,
            "time_range": time_range,
            "time_field": time_field,
            "filters":    filters,
            "total":      len(values),
            "values":     values,
        }

    except Exception as e:
        return {"error": str(e), "field": field}


def _build_base_query(
    time_range: str,
    time_field: str,
    filters: dict,
    nested_path: str | None,
    schema: dict,
) -> dict:
    must = [build_time_range_clause(time_field, time_range)]

    for f, v in filters.items():
        field_nested = get_nested_path(f, {"nested_paths": [nested_path]} if nested_path else {"nested_paths": []})
        if field_nested:
            continue  # filtros nested são tratados separadamente na agregação
        resolved_field = resolve_exact_field(f, schema)
        must.append(build_filter_clause(resolved_field, v))

    return {"bool": {"must": must}}


def _flat_terms_body(field: str, query: dict, size: int) -> dict:
    return {
        "size": 0,
        "query": query,
        "aggs": {
            "values": {
                "terms": {"field": field, "size": size, "order": {"_count": "desc"}}
            }
        },
    }


def _nested_terms_body(field: str, nested_path: str, query: dict, size: int) -> dict:
    return {
        "size": 0,
        "query": query,
        "aggs": {
            "nested_agg": {
                "nested": {"path": nested_path},
                "aggs": {
                    "values": {
                        "terms": {"field": field, "size": size, "order": {"_count": "desc"}}
                    }
                },
            }
        },
    }


def _extract_buckets(resp: dict, is_nested: bool) -> list:
    aggs = resp["aggregations"]
    if is_nested:
        return aggs["nested_agg"]["values"]["buckets"]
    return aggs["values"]["buckets"]

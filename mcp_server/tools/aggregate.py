"""
Tool: aggregate
Executa agregações arbitrárias no Elasticsearch.
O LLM monta os parâmetros; a tool traduz para DSL e executa.
Suporta métricas simples, agrupamentos, nested e date_histogram.
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


def aggregate(
    config:      dict,
    metric:      str,
    field:       str,
    group_by:    str | None  = None,
    time_range:  str         = None,
    time_field:  str | None  = None,
    filters:     dict        = None,
    any_filters: dict        = None,
    interval:    str | None  = None,
    nested_filter: dict      = None,
    size:        int         = 50,
    percentiles: list        = None,
) -> dict:
    """
    Parâmetros:
        metric        : count | avg | sum | min | max | percentiles | cardinality | date_histogram
        field         : campo alvo da métrica (ex: workflow_run.duration_ms)
        group_by      : campo para agrupar os resultados (ex: repository.name)
        time_range    : período ex: 1d, 7d, 30d, 90d
        filters       : filtros simples {campo: valor}
        interval      : para date_histogram: day | week | month
        nested_filter : filtro dentro de campo nested {campo: valor}
        size          : número máximo de buckets no group_by
        percentiles   : lista de percentis ex: [50, 90, 95, 99]
    """
    es          = get_client(config)
    index       = get_index(config)
    schema      = load_index_schema(config, es=es, index=index)
    time_field  = time_field or config.get("elasticsearch", {}).get("time_field", "workflow_run.started_at")
    time_range  = time_range or config.get("elasticsearch", {}).get("default_time_range", "7d")
    filters     = filters or {}
    any_filters = any_filters or {}
    nested_filter = nested_filter or {}
    percentiles = percentiles or [50, 75, 90, 95, 99]
    resolved_field = resolve_agg_field(field, schema)
    resolved_group_by = resolve_agg_field(group_by, schema) if group_by else None

    # Detecta se o campo alvo é nested
    nested_path = get_nested_path(resolved_field, schema)
    is_nested   = nested_path is not None

    # Detecta se o group_by é nested
    group_nested_path = get_nested_path(resolved_group_by, schema) if resolved_group_by else None

    # Query base (apenas campos não nested)
    base_query = _build_query(time_range, time_field, filters, any_filters, schema)

    # Monta a agregação de acordo com o tipo de métrica
    inner_agg = _build_metric_agg(metric, resolved_field, interval, percentiles)

    # Envolve em nested se necessário
    if is_nested:
        inner_agg = _wrap_nested(inner_agg, nested_path, nested_filter, schema)

    # Envolve em group_by se necessário
    if resolved_group_by:
        agg_body = _wrap_group_by(inner_agg, resolved_group_by, group_nested_path, size)
    else:
        agg_body = inner_agg

    try:
        resp   = es.search(index=index, body={"size": 0, "query": base_query, "aggs": agg_body})
        result = _parse_response(resp, metric, group_by, is_nested, group_nested_path, field)

        return {
            "metric":     metric,
            "field":      field,
            "resolved_field": resolved_field,
            "group_by":   group_by,
            "resolved_group_by": resolved_group_by,
            "time_range": time_range,
            "time_field": time_field,
            "filters":    filters,
            "any_filters": any_filters,
            "result":     result,
        }

    except Exception as e:
        return {"error": str(e), "metric": metric, "field": field}


# ── Builders ──────────────────────────────────────────────────

def _build_query(time_range: str, time_field: str, filters: dict, any_filters: dict, schema: dict) -> dict:
    must = [build_time_range_clause(time_field, time_range)]
    should = []
    for f, v in filters.items():
        if get_nested_path(f, schema):
            continue  # nested filters tratados dentro da agg
        resolved_field = resolve_exact_field(f, schema)
        if v is not None:
            must.append(build_filter_clause(resolved_field, v))
    for f, v in any_filters.items():
        if get_nested_path(f, schema):
            continue
        resolved_field = resolve_exact_field(f, schema)
        if v is not None:
            should.append(build_filter_clause(resolved_field, v))
    query = {"bool": {"must": must}}
    if should:
        query["bool"]["should"] = should
        query["bool"]["minimum_should_match"] = 1
    return query


def _build_metric_agg(metric: str, field: str, interval: str | None, percentiles: list) -> dict:
    if metric == "count":
        return {"metric": {"value_count": {"field": field}}}
    if metric == "avg":
        return {"metric": {"avg": {"field": field}}}
    if metric == "sum":
        return {"metric": {"sum": {"field": field}}}
    if metric == "min":
        return {"metric": {"min": {"field": field}}}
    if metric == "max":
        return {"metric": {"max": {"field": field}}}
    if metric == "cardinality":
        return {"metric": {"cardinality": {"field": field}}}
    if metric == "percentiles":
        return {"metric": {"percentiles": {"field": field, "percents": percentiles}}}
    if metric == "date_histogram":
        cal_interval = interval or "day"
        return {
            "metric": {
                "date_histogram": {
                    "field":             field,
                    "calendar_interval": cal_interval,
                    "min_doc_count":     1,
                }
            }
        }
    if metric == "stats":
        return {
            "metric_stats": {"stats": {"field": field}},
            "metric_p95":   {"percentiles": {"field": field, "percents": [50, 90, 95, 99]}},
        }
    return {"metric": {"value_count": {"field": field}}}


def _wrap_nested(inner_agg: dict, nested_path: str, nested_filter: dict, schema: dict) -> dict:
    if nested_filter:
        filter_field, filter_value = next(iter(nested_filter.items()))
        resolved_filter_field = resolve_exact_field(filter_field, schema)
        filter_clause = build_filter_clause(resolved_filter_field, filter_value)

        return {
            "nested_wrap": {
                "nested": {"path": nested_path},
                "aggs": {
                    "filtered": {
                        "filter": filter_clause,
                        "aggs":   inner_agg,
                    }
                },
            }
        }

    return {
        "nested_wrap": {
            "nested": {"path": nested_path},
            "aggs":   inner_agg,
        }
    }


def _wrap_group_by(inner_agg: dict, group_by: str, nested_path: str | None, size: int) -> dict:
    if nested_path:
        return {
            "group_nested": {
                "nested": {"path": nested_path},
                "aggs": {
                    "groups": {
                        "terms": {"field": group_by, "size": size, "order": {"_count": "desc"}},
                        "aggs":  inner_agg,
                    }
                },
            }
        }
    return {
        "groups": {
            "terms": {"field": group_by, "size": size, "order": {"_count": "desc"}},
            "aggs":  inner_agg,
        }
    }


# ── Parser de resposta ────────────────────────────────────────

def _parse_response(
    resp:              dict,
    metric:            str,
    group_by:          str | None,
    is_nested:         bool,
    group_nested_path: str | None,
    field:             str,
) -> dict | list:
    aggs = resp["aggregations"]

    if group_by:
        if group_nested_path:
            buckets = aggs["group_nested"]["groups"]["buckets"]
        else:
            buckets = aggs["groups"]["buckets"]

        result = []
        for b in buckets:
            value = _extract_metric_value(b, metric, is_nested)
            result.append({"group": b["key"], "count": b["doc_count"], "value": value})
        return result

    return _extract_metric_value(aggs, metric, is_nested)


def _extract_metric_value(agg_node: dict, metric: str, is_nested: bool) -> dict | float | None:
    node = agg_node

    if is_nested:
        node = node.get("nested_wrap", node)
        node = node.get("filtered", node)

    if metric == "stats":
        stats = node.get("metric_stats", {})
        percs = node.get("metric_p95", {})
        return {
            "count": stats.get("count"),
            "avg":   stats.get("avg"),
            "min":   stats.get("min"),
            "max":   stats.get("max"),
            "sum":   stats.get("sum"),
            "percentiles": percs.get("values", {}),
        }

    if metric == "percentiles":
        return node.get("metric", {}).get("values", {})

    if metric == "date_histogram":
        buckets = node.get("metric", {}).get("buckets", [])
        return [{"date": b["key_as_string"], "count": b["doc_count"]} for b in buckets]

    return node.get("metric", {}).get("value")

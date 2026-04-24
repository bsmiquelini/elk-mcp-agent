"""
Tool: search
Busca documentos no Elasticsearch com filtros livres.
Suporta campos nested, ordenação e seleção de campos.
"""

from elastic_client import get_client, get_index
from schema_utils import build_filter_clause, get_nested_path, load_index_schema, resolve_exact_field
from tools.time_filters import build_time_range_clause


def search(
    config:         dict,
    filters:        dict = None,
    any_filters:    dict = None,
    nested_filters: dict = None,
    time_range:     str  = None,
    time_field:     str  = None,
    fields:         list = None,
    sort:           str  = None,
    limit:          int  = 10,
    search_after:   list = None,
) -> dict:
    es           = get_client(config)
    index        = get_index(config)
    schema       = load_index_schema(config, es=es, index=index)
    time_field   = time_field or config.get("elasticsearch", {}).get("time_field", "workflow_run.started_at")
    time_range   = time_range or config.get("elasticsearch", {}).get("default_time_range", "7d")
    filters      = filters or {}
    any_filters  = any_filters or {}
    limit        = min(limit, 200)

    must = [build_time_range_clause(time_field, time_range)]
    should = []

    for f, v in filters.items():
        resolved_field = resolve_exact_field(f, schema)
        if v is not None:
            must.append(build_filter_clause(resolved_field, v))

    for f, v in any_filters.items():
        resolved_field = resolve_exact_field(f, schema)
        if v is not None:
            should.append(build_filter_clause(resolved_field, v))

    if nested_filters:
        for f, v in nested_filters.items():
            nested_path = get_nested_path(f, schema)
            resolved_field = resolve_exact_field(f, schema)
            if not nested_path:
                must.append(build_filter_clause(resolved_field, v))
                continue

            filter_clause = build_filter_clause(resolved_field, v)

            must.append({
                "nested": {
                    "path":  nested_path,
                    "query": filter_clause,
                }
            })

    query = {"bool": {"must": must}}
    if should:
        query["bool"]["should"] = should
        query["bool"]["minimum_should_match"] = 1

    body = {
        "size":  limit,
        "query": query,
        "sort":  _parse_sort(sort, time_field, schema),
    }

    if fields:
        body["_source"] = fields

    if search_after:
        body["search_after"] = search_after

    try:
        resp      = es.search(index=index, body=body)
        hits      = resp["hits"]["hits"]
        total     = resp["hits"]["total"]["value"]
        documents = [h["_source"] for h in hits]
        last_sort = hits[-1].get("sort") if hits else None

        return {
            "total":      total,
            "shown":      len(documents),
            "time_range": time_range,
            "time_field": time_field,
            "filters":    filters,
            "any_filters": any_filters,
            "documents":  documents,
            "next_page":  last_sort,
        }

    except Exception as e:
        return {"error": str(e)}


def _parse_sort(sort: str | None, default_field: str, schema: dict) -> list:
    if not sort:
        return [{default_field: {"order": "desc"}}]
    if ":" in sort:
        field, order = sort.split(":", 1)
        return [{resolve_exact_field(field.strip(), schema): {"order": order.strip()}}]
    return [{resolve_exact_field(sort, schema): {"order": "desc"}}]

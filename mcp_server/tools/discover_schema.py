"""
Tool: discover_schema
Descobre o schema completo do índice Elasticsearch.
Retorna campos, tipos, campos nested e uma amostra de valores
para os campos mais relevantes — tudo dinamicamente.
"""

from elastic_client import get_client, get_index
from schema_utils import load_index_schema


def discover_schema(config: dict) -> dict:
    es    = get_client(config)
    index = get_index(config)

    try:
        schema = load_index_schema(config, es=es, index=index)
        fields = schema["fields"]
        nested_paths = schema["nested_paths"]

        # Stats do índice
        stats_resp  = es.indices.stats(index=index)
        total_docs  = stats_resp["_all"]["primaries"]["docs"]["count"]

        # Amostra de valores para campos keyword não nested (top 10 por campo)
        sample_values = _sample_keyword_fields(es, index, fields)

        return {
            "index":         index,
            "total_docs":    total_docs,
            "total_fields":  len(fields),
            "nested_paths":  nested_paths,
            "fields":        fields,
            "profile":       schema.get("profile", {}),
            "sample_values": sample_values,
        }

    except Exception as e:
        return {"error": str(e), "index": index}


def _sample_keyword_fields(es, index: str, fields: dict) -> dict:
    """Retorna amostra de valores para campos keyword não nested."""
    keyword_fields = [
        name for name, meta in fields.items()
        if meta.get("type") == "keyword" and not meta.get("nested")
    ][:12]  # Limita para não sobrecarregar o startup

    if not keyword_fields:
        return {}

    aggs = {
        f.replace(".", "_"): {"terms": {"field": f, "size": 10}}
        for f in keyword_fields
    }

    try:
        resp   = es.search(index=index, body={"size": 0, "aggs": aggs})
        result = {}
        for field in keyword_fields:
            key     = field.replace(".", "_")
            buckets = resp["aggregations"][key]["buckets"]
            result[field] = [b["key"] for b in buckets]
        return result
    except Exception:
        return {}

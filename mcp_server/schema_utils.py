"""
Helpers para descobrir e resolver campos dinamicamente a partir do mapping.
"""

from elastic_client import get_client, get_index

AGGREGATABLE_TYPES = {
    "keyword",
    "date",
    "long",
    "integer",
    "short",
    "byte",
    "float",
    "double",
    "half_float",
    "scaled_float",
    "unsigned_long",
    "boolean",
    "ip",
}


def load_index_schema(config: dict, es=None, index: str | None = None) -> dict:
    es = es or get_client(config)
    index = index or get_index(config)

    mapping_resp = es.indices.get_mapping(index=index)
    fields = {}
    nested_paths = []

    for _, mapping in mapping_resp.items():
        raw_props = mapping.get("mappings", {}).get("properties", {})
        _flatten(raw_props, "", fields, nested_paths, parent_nested=False)

    profile = infer_schema_profile(fields)

    return {
        "index": index,
        "fields": fields,
        "nested_paths": sorted(set(nested_paths)),
        "profile": profile,
    }


def _flatten(
    properties: dict,
    prefix: str,
    result: dict,
    nested_paths: list,
    parent_nested: bool,
):
    for name, definition in properties.items():
        full_name = f"{prefix}{name}" if prefix else name
        field_type = definition.get("type", "object")

        if field_type == "nested":
            nested_paths.append(full_name)
            _flatten(
                definition.get("properties", {}),
                f"{full_name}.",
                result,
                nested_paths,
                parent_nested=True,
            )
            continue

        if "properties" in definition:
            _flatten(
                definition["properties"],
                f"{full_name}.",
                result,
                nested_paths,
                parent_nested=parent_nested,
            )
            continue

        exact_field = full_name
        aggregatable = field_type in AGGREGATABLE_TYPES

        for subfield_name, subfield_def in definition.get("fields", {}).items():
            subfield_full_name = f"{full_name}.{subfield_name}"
            subfield_type = subfield_def.get("type", "object")
            result[subfield_full_name] = {
                "type": subfield_type,
                "nested": parent_nested,
                "exact_field": subfield_full_name,
                "aggregatable": subfield_type in AGGREGATABLE_TYPES,
                "parent_field": full_name,
            }
            if subfield_type == "keyword" and subfield_name == "keyword":
                exact_field = subfield_full_name
                aggregatable = True

        result[full_name] = {
            "type": field_type,
            "nested": parent_nested,
            "exact_field": exact_field,
            "aggregatable": aggregatable,
        }


def get_nested_path(field: str | None, schema: dict) -> str | None:
    if not field:
        return None

    candidates = [field]
    if field.endswith(".keyword"):
        candidates.append(field[:-8])

    for candidate in candidates:
        for path in schema.get("nested_paths", []):
            if candidate == path or candidate.startswith(f"{path}."):
                return path
    return None


def resolve_exact_field(field: str, schema: dict) -> str:
    meta = schema.get("fields", {}).get(field)
    if meta:
        return meta.get("exact_field", field)

    if field.endswith(".keyword"):
        return field

    base_meta = schema.get("fields", {}).get(field)
    if base_meta:
        return base_meta.get("exact_field", field)
    return field


def resolve_agg_field(field: str, schema: dict) -> str:
    meta = schema.get("fields", {}).get(field)
    if meta:
        exact_field = meta.get("exact_field", field)
        if meta.get("type") == "text" and exact_field != field:
            return exact_field
        if meta.get("aggregatable"):
            return field
        return exact_field

    if field.endswith(".keyword"):
        return field

    base_meta = schema.get("fields", {}).get(field)
    if base_meta:
        return base_meta.get("exact_field", field)
    return field


def build_filter_clause(field: str, value):
    if isinstance(value, list):
        if not value:
            return {"bool": {"must_not": [{"match_all": {}}]}}

        if any(isinstance(item, str) and "*" in item for item in value):
            clauses = [_build_single_filter_clause(field, item) for item in value]
            return {
                "bool": {
                    "should": clauses,
                    "minimum_should_match": 1,
                }
            }

        return {"terms": {field: value}}

    return _build_single_filter_clause(field, value)


def _build_single_filter_clause(field: str, value):
    if isinstance(value, str) and "*" in value:
        return {"wildcard": {field: value}}
    return {"term": {field: value}}


def infer_schema_profile(fields: dict) -> dict:
    profile = {
        "primary_time_field": _pick_first(
            fields,
            [
                "workflow_run.run_started_at",
                "workflow_run.created_at",
                "check_run.started_at",
                "deployment_status.updated_at",
                "deployment.created_at",
                "@timestamp",
            ],
        ),
        "workflow_name_field": _pick_first(
            fields,
            [
                "workflow_run.name",
                "workflow.name",
                "workflow_run.display_title",
            ],
        ),
        "workflow_execution_id_field": _pick_first(
            fields,
            [
                "workflow_run.id",
                "workflow_run.run_number",
            ],
        ),
        "workflow_status_field": _pick_first(
            fields,
            [
                "workflow_run.conclusion",
                "workflow_run.status",
                "deployment_status.state",
            ],
        ),
        "job_name_field": _pick_first(
            fields,
            [
                "check_run.name",
                "jobs.name",
            ],
        ),
        "job_execution_id_field": _pick_first(
            fields,
            [
                "check_run.id",
            ],
        ),
        "job_status_field": _pick_first(
            fields,
            [
                "check_run.conclusion",
                "check_run.status",
                "jobs.conclusion",
                "jobs.status",
            ],
        ),
        "repository_name_field": _pick_first(
            fields,
            [
                "repository.full_name",
                "repository.name",
            ],
        ),
        "repository_topic_field": _pick_first(
            fields,
            [
                "repository.topics",
            ],
        ),
        "repository_language_field": _pick_first(
            fields,
            [
                "repository.language",
                "repository.primary_language",
            ],
        ),
        "repository_private_field": _pick_first(
            fields,
            [
                "repository.private",
            ],
        ),
        "repository_fork_field": _pick_first(
            fields,
            [
                "repository.fork",
            ],
        ),
        "deploy_indicator_field": _pick_first(
            fields,
            [
                "deployment.task",
                "deployment.environment",
                "deployment_status.environment",
                "workflow_run.name",
                "workflow.name",
                "check_run.name",
            ],
        ),
        "environment_field": _pick_first(
            fields,
            [
                "deployment.environment",
                "deployment_status.environment",
            ],
        ),
        "deployment_created_field": _pick_first(
            fields,
            [
                "deployment.created_at",
            ],
        ),
        "deployment_updated_field": _pick_first(
            fields,
            [
                "deployment.updated_at",
                "deployment_status.updated_at",
            ],
        ),
        "actor_field": _pick_first(
            fields,
            [
                "sender.login",
                "workflow_run.actor.login",
                "workflow_run.triggering_actor.login",
            ],
        ),
        "actor_email_field": _pick_first(
            fields,
            [
                "sender.email",
                "workflow_run.actor.email",
                "workflow_run.triggering_actor.email",
            ],
        ),
        "actor_type_field": _pick_first(
            fields,
            [
                "sender.type",
                "workflow_run.actor.type",
                "workflow_run.triggering_actor.type",
            ],
        ),
        "workflow_start_field": _pick_first(
            fields,
            [
                "workflow_run.run_started_at",
                "workflow_run.created_at",
            ],
        ),
        "repository_request_date_field": _pick_first(
            fields,
            [
                "repository.request.requested_at",
            ],
        ),
        "repository_requester_email_field": _pick_first(
            fields,
            [
                "repository.request.requester_email",
            ],
        ),
        "repository_created_field": _pick_first(
            fields,
            [
                "repository.created_at",
            ],
        ),
        "pipeline_request_date_field": _pick_first(
            fields,
            [
                "pipeline_enablement.requested_at",
            ],
        ),
        "pipeline_requester_email_field": _pick_first(
            fields,
            [
                "pipeline_enablement.requester_email",
            ],
        ),
        "workflow_created_field": _pick_first(
            fields,
            [
                "workflow.created_at",
            ],
        ),
        "deployment_execution_id_field": _pick_first(
            fields,
            [
                "deployment.id",
                "deployment_status.id",
            ],
        ),
        "branch_field": _pick_first(
            fields,
            [
                "workflow_run.head_branch",
            ],
        ),
        "workflow_end_field": _pick_first(
            fields,
            [
                "workflow_run.updated_at",
            ],
        ),
        "job_start_field": _pick_first(
            fields,
            [
                "check_run.started_at",
                "jobs.started_at",
            ],
        ),
        "job_end_field": _pick_first(
            fields,
            [
                "check_run.completed_at",
                "jobs.completed_at",
            ],
        ),
    }

    profile["candidate_time_fields"] = _collect(
        fields,
        [
            "@timestamp",
            "workflow_run.run_started_at",
            "workflow_run.created_at",
            "workflow_run.updated_at",
            "check_run.started_at",
            "check_run.completed_at",
            "deployment.created_at",
            "deployment.updated_at",
            "deployment_status.updated_at",
        ],
    )
    profile["candidate_status_fields"] = _collect(
        fields,
        [
            "workflow_run.conclusion",
            "workflow_run.status",
            "check_run.conclusion",
            "check_run.status",
            "deployment_status.state",
        ],
    )
    profile["candidate_workflow_fields"] = _collect(
        fields,
        [
            "workflow_run.name",
            "workflow.name",
            "workflow_run.display_title",
            "workflow.path",
            "workflow_run.path",
        ],
    )
    profile["candidate_job_fields"] = _collect(
        fields,
        [
            "check_run.name",
            "check_run.conclusion",
            "check_run.status",
            "jobs.name",
            "jobs.conclusion",
            "jobs.status",
        ],
    )
    profile["candidate_deploy_fields"] = _collect(
        fields,
        [
            "deployment.task",
            "deployment.environment",
            "deployment_status.state",
            "deployment_status.environment",
        ],
    )
    profile["success_values_hint"] = ["success", "completed"]
    profile["failure_values_hint"] = ["failure", "failed", "error", "timed_out"]
    return profile


def _pick_first(fields: dict, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def _collect(fields: dict, candidates: list[str]) -> list[str]:
    return [candidate for candidate in candidates if candidate in fields]

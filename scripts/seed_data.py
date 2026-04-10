"""
Seed de dados para índices github-workflows-*.
Gera eventos simulados próximos do formato real vindo de webhooks do GitHub.
"""

import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
from faker import Faker

load_dotenv()
fake = Faker("pt_BR")
SEED = 42

random.seed(SEED)
Faker.seed(SEED)

ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USER = "elastic"
ES_PASSWORD = os.getenv("ELASTIC_PASSWORD", "changeme123")
INDEX_PREFIX = "github-workflows"
DAYS = 300
TARGET_DOCS = 1800
ES_REQUEST_TIMEOUT = int(os.getenv("ELASTICSEARCH_TIMEOUT", "60"))
SEED_NOW = None

ENTERPRISE = {
    "id": 36467,
    "name": "nada Enterprise",
    "slug": "nada",
    "description": "Conta Enterprise Cloud do nada para governanca centralizada",
    "created_at": "2023-05-10T21:59:27.000Z",
    "updated_at": "2025-08-12T20:54:29.000Z",
}

ORGANIZATION = {
    "id": 151876077,
    "login": "nada",
    "description": "Organization relacionada a projetos core do nada",
}

GITHUB_APP = {
    "id": 15368,
    "name": "GitHub Actions",
    "slug": "github-actions",
    "description": "Automate your workflow from idea to production",
    "client_id": "Iv1.05c79e9ad1f6bdfa",
    "created_at": "2018-07-30T09:30:17.000Z",
    "updated_at": "2025-12-02T18:13:15.000Z",
    "owner": {
        "id": 9919,
        "login": "github",
        "type": "Organization",
        "site_admin": False,
        "user_view_type": "public",
    },
}

USERS = [
    {"login": "leonardo-l-lotaif_nada", "email": "leonardo.lotaif@nada.com.br", "type": "User"},
    {"login": "maria.souza_nada", "email": "maria.souza@nada.com.br", "type": "User"},
    {"login": "joao.silva_nada", "email": "joao.silva@nada.com.br", "type": "User"},
    {"login": "bruno.miquelini_nada", "email": "bruno.miquelini@nada.com.br", "type": "User"},
    {"login": "ana.sre_nada", "email": "ana.sre@nada.com.br", "type": "User"},
    {"login": "bia.devops_nada", "email": "bia.devops@nada.com.br", "type": "User"},
    {"login": "github-actions[bot]", "email": "github-actions-bot@noreply.github.com", "type": "Bot"},
]

REPOSITORIES = [
    {
        "name": "arch-api-cash-cambio-contatos-ext",
        "full_name": "nada/arch-api-cash-cambio-contatos-ext",
        "description": "[CASHHUB - OPEN CASH HUB]",
        "language": "java",
        "topics": ["api", "cashhub", "cloud", "oas31", "archtecture-api", "architecture-api"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "nexus",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.12,
        "requested_days_ago": 210,
        "repo_created_days_ago": 190,
        "pipeline_requested_days_ago": 175,
    },
    {
        "name": "arch-srv-credit-engine",
        "full_name": "nada/arch-srv-credit-engine",
        "description": "[CREDIT - CORE ENGINE]",
        "language": "java",
        "topics": ["java", "spring-boot", "credit", "archtecture-srv", "architecture-srv"],
        "private": True,
        "custom_properties": {
            "api-publish": "true",
            "registry": "nexus",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.18,
        "requested_days_ago": 240,
        "repo_created_days_ago": 220,
        "pipeline_requested_days_ago": 205,
    },
    {
        "name": "devops-bff-pix-web",
        "full_name": "nada/devops-bff-pix-web",
        "description": "[PIX - WEB FRONTEND]",
        "language": "typescript",
        "topics": ["frontend", "react", "pix", "web", "archtecture-bff", "architecture-bff"],
        "private": False,
        "custom_properties": {
            "api-publish": "false",
            "registry": "npm",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.08,
        "requested_days_ago": 170,
        "repo_created_days_ago": 155,
        "pipeline_requested_days_ago": 145,
    },
    {
        "name": "ia-srv-data-risk-pipeline",
        "full_name": "nada/ia-srv-data-risk-pipeline",
        "description": "[RISK - DATA PIPELINE]",
        "language": "python",
        "topics": ["python", "data", "risk", "etl", "archtecture-srv", "architecture-srv"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "pypi",
            "self-update": "true",
            "self-update-workflows": "false",
            "copilot-review": "false",
        },
        "failure_bias": 0.15,
        "requested_days_ago": 260,
        "repo_created_days_ago": 245,
        "pipeline_requested_days_ago": 230,
    },
    {
        "name": "sre-apim-gateway-core",
        "full_name": "nada/sre-apim-gateway-core",
        "description": "[APIM - GATEWAY CORE]",
        "language": "node",
        "topics": ["node", "gateway", "apim", "archtecture-apim", "architecture-apim"],
        "private": True,
        "custom_properties": {
            "api-publish": "true",
            "registry": "npm",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.1,
        "requested_days_ago": 150,
        "repo_created_days_ago": 135,
        "pipeline_requested_days_ago": 120,
    },
    {
        "name": "devops-api-release-ops",
        "full_name": "nada/devops-api-release-ops",
        "description": "[DEVOPS - RELEASE OPS]",
        "language": "node",
        "topics": ["node", "devops", "ops", "archtecture-api", "architecture-api"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "npm",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.09,
        "requested_days_ago": 120,
        "repo_created_days_ago": 110,
        "pipeline_requested_days_ago": 95,
    },
    {
        "name": "sre-srv-observability",
        "full_name": "nada/sre-srv-observability",
        "description": "[SRE - OBSERVABILITY]",
        "language": "python",
        "topics": ["python", "observability", "sre", "archtecture-srv", "architecture-srv"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "pypi",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "false",
        },
        "failure_bias": 0.13,
        "requested_days_ago": 200,
        "repo_created_days_ago": 182,
        "pipeline_requested_days_ago": 168,
    },
]

WORKFLOWS = [
    {
        "name": "Build and Test",
        "path": ".github/workflows/build-and-test.yaml",
        "kind": "build",
        "events": ["push", "pull_request"],
        "check_names": ["build", "compile", "unit-tests"],
        "base_duration_ms": 180_000,
        "enablement_days_ago": 170,
    },
    {
        "name": "Axway Deploy Release",
        "path": ".github/workflows/api-deploy-release.yaml",
        "kind": "deploy",
        "events": ["push", "workflow_dispatch"],
        "check_names": ["call-deploy-prd / axway-deploy", "deploy-release", "smoke-test"],
        "base_duration_ms": 420_000,
        "enablement_days_ago": 150,
    },
    {
        "name": "Deploy Staging",
        "path": ".github/workflows/deploy-staging.yaml",
        "kind": "deploy",
        "events": ["push"],
        "check_names": ["call-deploy-hml / axway-deploy", "deploy-staging", "smoke-test"],
        "base_duration_ms": 300_000,
        "enablement_days_ago": 155,
    },
    {
        "name": "Security Scan",
        "path": ".github/workflows/security-scan.yaml",
        "kind": "security",
        "events": ["schedule"],
        "check_names": ["dependency-scan", "sast"],
        "base_duration_ms": 240_000,
        "enablement_days_ago": 165,
    },
    {
        "name": "Rollback Production",
        "path": ".github/workflows/rollback-prd.yaml",
        "kind": "rollback",
        "events": ["workflow_dispatch"],
        "check_names": ["rollback-prd", "rollback-validation", "approval-gate"],
        "base_duration_ms": 210_000,
        "enablement_days_ago": 140,
    },
    {
        "name": "APIM Deploy Gateway",
        "path": ".github/workflows/apim-deploy.yaml",
        "kind": "deploy",
        "events": ["push", "workflow_dispatch"],
        "check_names": ["deploy-apim-prd", "deploy-apim-hml", "smoke-test"],
        "base_duration_ms": 360_000,
        "enablement_days_ago": 130,
    },
    {
        "name": "Node Build and Test",
        "path": ".github/workflows/node-build.yaml",
        "kind": "build",
        "events": ["push", "pull_request"],
        "check_names": ["node-build", "lint", "unit-tests", "quality-gate"],
        "base_duration_ms": 150_000,
        "enablement_days_ago": 160,
    },
]

BRANCHES = ["main", "develop", "release/v2.1", "feature/pix-ui", "feature/credit-limit"]
DEPLOY_ENVS = ["PRD", "HML", "STG", "DEV", "SANDBOX"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", ".000Z")


def _random_user() -> dict:
    base = random.choice(USERS)
    return {
        "id": random.randint(100_000, 999_999_999),
        "login": base["login"],
        "email": base["email"],
        "node_id": f"U_kgDO{uuid.uuid4().hex[:8]}",
        "site_admin": False,
        "type": base["type"],
        "user_view_type": "public",
    }


def _ensure_repo_seed(repo: dict, now: datetime) -> None:
    seed_now = SEED_NOW or now
    if "_seed_created_at" in repo:
        return
    repo["_seed_requested_at"] = seed_now - timedelta(days=repo.get("requested_days_ago", 180), hours=2)
    repo["_seed_created_at"] = seed_now - timedelta(days=repo.get("repo_created_days_ago", 160))
    repo["_seed_pipeline_requested_at"] = seed_now - timedelta(days=repo.get("pipeline_requested_days_ago", 145), hours=4)
    repo["_seed_pushed_at"] = seed_now - timedelta(hours=random.randint(1, 48))
    repo["_seed_requester"] = random.choice([user for user in USERS if user["type"] == "User"])


def _repository_doc(repo: dict, now: datetime) -> dict:
    _ensure_repo_seed(repo, now)
    created_at = repo["_seed_created_at"]
    pushed_at = repo["_seed_pushed_at"]
    requester = repo["_seed_requester"]
    return {
        "id": random.randint(1_000_000_000, 1_999_999_999),
        "name": repo["name"],
        "full_name": repo["full_name"],
        "description": repo["description"],
        "language": repo["language"],
        "topics": repo["topics"],
        "private": repo["private"],
        "fork": False,
        "size": random.randint(20, 400),
        "has_issues": True,
        "has_projects": False,
        "open_issues_count": random.randint(0, 5),
        "created_at": _iso(created_at),
        "updated_at": _iso(pushed_at + timedelta(minutes=3)),
        "pushed_at": _iso(pushed_at),
        "owner": {
            "id": ORGANIZATION["id"],
            "login": ORGANIZATION["login"],
            "type": "Organization",
            "user_view_type": "public",
        },
        "custom_properties": repo["custom_properties"],
        "request": {
            "requested_at": _iso(repo["_seed_requested_at"]),
            "requester_email": requester["email"],
            "requester_login": requester["login"],
            "ticket": f"REQ-{random.randint(10000, 99999)}",
        },
    }


def _workflow_conclusion(workflow: dict, repo: dict) -> str:
    roll = random.random()
    if roll < repo["failure_bias"]:
        return random.choice(["failure", "failure", "timed_out"])
    if roll < repo["failure_bias"] + 0.04:
        return "cancelled"
    return "success"


def _deployment_state(conclusion: str) -> str:
    mapping = {
        "success": "success",
        "failure": "failure",
        "timed_out": "error",
        "cancelled": "inactive",
    }
    return mapping.get(conclusion, "waiting")


def _pick_check_name(workflow: dict, conclusion: str) -> str:
    if workflow["kind"] == "build" and conclusion in {"failure", "timed_out"}:
        return random.choice(["build", "compile", "docker-build", "quality-gate", "approval-gate"])
    if workflow["kind"] == "deploy" and conclusion in {"failure", "timed_out"}:
        return random.choice(["call-deploy-prd / axway-deploy", "deploy-release", "deploy-staging", "deploy-apim-prd", "smoke-test"])
    if workflow["kind"] == "rollback":
        return random.choice(workflow["check_names"])
    return random.choice(workflow["check_names"])


def _document_index_name(event_time: datetime) -> str:
    return f"{INDEX_PREFIX}-{event_time.strftime('%Y.%m.%d')}"


def _workflow_reference_dates(workflow: dict, seed_now: datetime) -> tuple[datetime, datetime]:
    created_at = seed_now - timedelta(days=workflow.get("enablement_days_ago", 150))
    updated_at = seed_now - timedelta(days=max(1, workflow.get("enablement_days_ago", 150) - 10))
    return created_at, updated_at


def _pick_valid_repo_and_workflow(event_time: datetime) -> tuple[dict, dict]:
    seed_now = SEED_NOW or event_time
    valid_pairs = []
    for repo in REPOSITORIES:
        _ensure_repo_seed(repo, seed_now)
        if event_time < repo["_seed_created_at"]:
            continue
        for workflow in WORKFLOWS:
            workflow_created_at, _ = _workflow_reference_dates(workflow, seed_now)
            available_from = max(repo["_seed_pipeline_requested_at"], workflow_created_at)
            if event_time >= available_from:
                valid_pairs.append((repo, workflow))
    if not valid_pairs:
        fallback_repo = random.choice(REPOSITORIES)
        _ensure_repo_seed(fallback_repo, seed_now)
        return fallback_repo, random.choice(WORKFLOWS)
    return random.choice(valid_pairs)


def generate_document(run_number: int, event_time: datetime) -> dict:
    repo, workflow = _pick_valid_repo_and_workflow(event_time)
    sender = _random_user()
    actor = _random_user()
    branch = random.choice(BRANCHES)
    event = random.choice(workflow["events"])
    conclusion = _workflow_conclusion(workflow, repo)
    check_name = _pick_check_name(workflow, conclusion)
    pending_approval = workflow["kind"] in {"deploy", "rollback"} and random.random() < 0.06

    run_started_at = event_time - timedelta(minutes=random.randint(1, 30))
    workflow_updated_at = run_started_at + timedelta(milliseconds=int(workflow["base_duration_ms"] * random.uniform(0.8, 1.4)))
    check_started_at = run_started_at + timedelta(seconds=random.randint(5, 60))
    check_completed_at = workflow_updated_at - timedelta(seconds=random.randint(5, 45))

    if pending_approval:
        workflow_status = "in_progress"
        conclusion = None
        check_status = "waiting"
        check_conclusion = None
        check_completed_at = None
    else:
        workflow_status = "completed" if conclusion in {"success", "failure", "timed_out", "cancelled"} else "in_progress"
        check_conclusion = "success" if conclusion == "success" else random.choice(["failure", "failure", "timed_out", "cancelled"])
        check_status = "completed"

    doc = {
        "_index": _document_index_name(event_time),
        "_id": str(uuid.uuid4()),
        "_source": {
            "@timestamp": _iso(event_time),
            "action": random.choice(["completed", "created", "requested"]),
            "enterprise": ENTERPRISE,
            "organization": ORGANIZATION,
            "repository": _repository_doc(repo, event_time),
            "sender": sender,
            "workflow": {
                "id": random.randint(100_000_000, 999_999_999),
                "name": workflow["name"],
                "path": workflow["path"],
                "state": "active",
                "created_at": _iso(_workflow_reference_dates(workflow, SEED_NOW or event_time)[0]),
                "updated_at": _iso(_workflow_reference_dates(workflow, SEED_NOW or event_time)[1]),
            },
            "workflow_run": {
                "id": str(random.randint(20_000_000_000, 29_999_999_999)),
                "node_id": f"WFR_kwLO{uuid.uuid4().hex[:16]}",
                "workflow_id": random.randint(100_000_000, 999_999_999),
                "name": workflow["name"],
                "display_title": fake.sentence(nb_words=6),
                "path": workflow["path"],
                "event": event,
                "status": workflow_status,
                "conclusion": conclusion,
                "head_branch": branch,
                "head_sha": uuid.uuid4().hex + uuid.uuid4().hex[:8],
                "run_attempt": 1 if conclusion == "success" else random.choice([1, 1, 2]),
                "run_number": run_number,
                "created_at": _iso(run_started_at),
                "updated_at": _iso(workflow_updated_at),
                "run_started_at": _iso(run_started_at),
                "actor": actor,
                "triggering_actor": sender,
            },
            "check_run": {
                "id": str(random.randint(70_000_000_000, 79_999_999_999)),
                "name": check_name,
                "head_sha": uuid.uuid4().hex + uuid.uuid4().hex[:8],
                "status": check_status,
                "conclusion": check_conclusion,
                "started_at": _iso(check_started_at),
                "completed_at": _iso(check_completed_at) if check_completed_at else None,
            },
        },
    }

    doc["_source"]["pipeline_enablement"] = {
        "requested_at": _iso(repo["_seed_pipeline_requested_at"]),
        "requester_email": repo["_seed_requester"]["email"],
        "requester_login": repo["_seed_requester"]["login"],
        "ticket": f"PIPE-{random.randint(10000, 99999)}",
    }

    if workflow["kind"] in {"deploy", "rollback"}:
        env = random.choice(DEPLOY_ENVS)
        deployment_created_at = run_started_at + timedelta(seconds=20)
        deployment_updated_at = workflow_updated_at
        deployment_status_created_at = deployment_updated_at - timedelta(seconds=15)
        deployment_state = "waiting" if pending_approval else _deployment_state(conclusion)

        doc["_source"]["deployment"] = {
            "id": random.randint(4_000_000_000, 4_999_999_999),
            "environment": env,
            "original_environment": env,
            "production_environment": env == "PRD",
            "transient_environment": False,
            "task": "rollback" if workflow["kind"] == "rollback" else "deploy",
            "ref": branch,
            "sha": doc["_source"]["workflow_run"]["head_sha"],
            "url": f"https://api.github.com/repos/{repo['full_name']}/deployments/{random.randint(4_000_000_000, 4_999_999_999)}",
            "created_at": _iso(deployment_created_at),
            "updated_at": _iso(deployment_updated_at),
            "creator": sender,
            "performed_via_github_app": GITHUB_APP,
        }
        doc["_source"]["deployment_status"] = {
            "id": random.randint(12_000_000_000, 12_999_999_999),
            "state": deployment_state,
            "environment": env,
            "description": "" if deployment_state == "success" else "Deployment falhou na etapa final",
            "environment_url": "",
            "url": f"https://api.github.com/repos/{repo['full_name']}/deployments/statuses/{random.randint(12_000_000_000, 12_999_999_999)}",
            "created_at": _iso(deployment_status_created_at),
            "updated_at": _iso(deployment_updated_at),
            "creator": sender,
        }

    return doc


def main():
    global SEED_NOW
    es = Elasticsearch(
        ES_URL,
        basic_auth=(ES_USER, ES_PASSWORD),
        verify_certs=False,
        request_timeout=ES_REQUEST_TIMEOUT,
    )

    print(f"📡 Conectando ao Elasticsearch em {ES_URL}...")
    info = es.info()
    print(f"✅ Conectado — Elasticsearch {info['version']['number']}")

    now = datetime.now(timezone.utc)
    SEED_NOW = now
    for repo in REPOSITORIES:
        _ensure_repo_seed(repo, now)
    documents = []

    print(f"🔧 Gerando {TARGET_DOCS} documentos em indices {INDEX_PREFIX}-YYYY.MM.DD ...")

    for run_number in range(1, TARGET_DOCS + 1):
        days_ago = random.uniform(0, DAYS)
        hours_ago = random.uniform(0, 23)
        event_time = now - timedelta(days=days_ago, hours=hours_ago)
        documents.append(generate_document(run_number, event_time))

    print("📤 Indexando no Elasticsearch...")
    success, failed = helpers.bulk(
        es,
        documents,
        raise_on_error=False,
        chunk_size=50,
        refresh="wait_for",
        request_timeout=ES_REQUEST_TIMEOUT,
    )

    print("")
    print("══════════════════════════════════════")
    print("✅ Seed concluído!")
    print(f"   Documentos indexados: {success}")
    if failed:
        print(f"   ⚠️  Falhas:           {len(failed)}")
    print(f"   Padrão de índice:    {INDEX_PREFIX}-*")
    print("══════════════════════════════════════")


if __name__ == "__main__":
    main()

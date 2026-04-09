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
DAYS = 90
TARGET_DOCS = 500

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
    "login": "",
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
    {"login": "leonardo-l-lotaif_nada", "type": "User"},
    {"login": "maria.souza_nada", "type": "User"},
    {"login": "joao.silva_nada", "type": "User"},
    {"login": "github-actions[bot]", "type": "Bot"},
]

REPOSITORIES = [
    {
        "name": "ochb-api-cash-cambio-contatos-ext",
        "full_name": nada/ochb-api-cash-cambio-contatos-ext",
        "description": "[CASHHUB - OPEN CASH HUB]",
        "language": "java",
        "topics": ["api", "cashhub", "cloud", "ochb", "oas31"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "nexus",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.12,
    },
    {
        "name": "core-credit-engine",
        "full_name": nada/core-credit-engine",
        "description": "[CREDIT - CORE ENGINE]",
        "language": "java",
        "topics": ["java", "spring-boot", "credit", "api"],
        "private": True,
        "custom_properties": {
            "api-publish": "true",
            "registry": "nexus",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.18,
    },
    {
        "name": "frontend-pix-web",
        "full_name": nada/frontend-pix-web",
        "description": "[PIX - WEB FRONTEND]",
        "language": "typescript",
        "topics": ["frontend", "react", "pix", "web"],
        "private": False,
        "custom_properties": {
            "api-publish": "false",
            "registry": "npm",
            "self-update": "true",
            "self-update-workflows": "true",
            "copilot-review": "true",
        },
        "failure_bias": 0.08,
    },
    {
        "name": "data-risk-pipeline",
        "full_name": nada/data-risk-pipeline",
        "description": "[RISK - DATA PIPELINE]",
        "language": "python",
        "topics": ["python", "data", "risk", "etl"],
        "private": True,
        "custom_properties": {
            "api-publish": "false",
            "registry": "pypi",
            "self-update": "true",
            "self-update-workflows": "false",
            "copilot-review": "false",
        },
        "failure_bias": 0.15,
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
    },
    {
        "name": "Axway Deploy Release",
        "path": ".github/workflows/api-deploy-release.yaml",
        "kind": "deploy",
        "events": ["push", "workflow_dispatch"],
        "check_names": ["call-deploy-prd / axway-deploy", "deploy-release", "smoke-test"],
        "base_duration_ms": 420_000,
    },
    {
        "name": "Deploy Staging",
        "path": ".github/workflows/deploy-staging.yaml",
        "kind": "deploy",
        "events": ["push"],
        "check_names": ["call-deploy-hml / axway-deploy", "deploy-staging", "smoke-test"],
        "base_duration_ms": 300_000,
    },
    {
        "name": "Security Scan",
        "path": ".github/workflows/security-scan.yaml",
        "kind": "security",
        "events": ["schedule"],
        "check_names": ["dependency-scan", "sast"],
        "base_duration_ms": 240_000,
    },
]

BRANCHES = ["main", "develop", "release/v2.1", "feature/pix-ui", "feature/credit-limit"]
DEPLOY_ENVS = ["PRD", "HML", "STG"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", ".000Z")


def _random_user() -> dict:
    base = random.choice(USERS)
    return {
        "id": random.randint(100_000, 999_999_999),
        "login": base["login"],
        "node_id": f"U_kgDO{uuid.uuid4().hex[:8]}",
        "site_admin": False,
        "type": base["type"],
        "user_view_type": "public",
    }


def _repository_doc(repo: dict, now: datetime) -> dict:
    created_at = now - timedelta(days=random.randint(20, 180))
    pushed_at = now - timedelta(hours=random.randint(1, 48))
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
        return random.choice(["build", "compile", "docker-build"])
    if workflow["kind"] == "deploy" and conclusion in {"failure", "timed_out"}:
        return random.choice(["call-deploy-prd / axway-deploy", "deploy-release", "deploy-staging", "smoke-test"])
    return random.choice(workflow["check_names"])


def _document_index_name(event_time: datetime) -> str:
    return f"{INDEX_PREFIX}-{event_time.strftime('%Y.%m.%d')}"


def generate_document(run_number: int, event_time: datetime) -> dict:
    repo = random.choice(REPOSITORIES)
    workflow = random.choice(WORKFLOWS)
    sender = _random_user()
    actor = _random_user()
    branch = random.choice(BRANCHES)
    event = random.choice(workflow["events"])
    conclusion = _workflow_conclusion(workflow, repo)
    check_name = _pick_check_name(workflow, conclusion)

    run_started_at = event_time - timedelta(minutes=random.randint(1, 30))
    workflow_updated_at = run_started_at + timedelta(milliseconds=int(workflow["base_duration_ms"] * random.uniform(0.8, 1.4)))
    check_started_at = run_started_at + timedelta(seconds=random.randint(5, 60))
    check_completed_at = workflow_updated_at - timedelta(seconds=random.randint(5, 45))

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
                "created_at": _iso(event_time - timedelta(days=random.randint(10, 100))),
                "updated_at": _iso(event_time - timedelta(days=random.randint(1, 9))),
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
                "completed_at": _iso(check_completed_at),
            },
        },
    }

    if workflow["kind"] == "deploy":
        env = random.choice(DEPLOY_ENVS)
        deployment_created_at = run_started_at + timedelta(seconds=20)
        deployment_updated_at = workflow_updated_at
        deployment_status_created_at = deployment_updated_at - timedelta(seconds=15)
        deployment_state = _deployment_state(conclusion)

        doc["_source"]["deployment"] = {
            "id": random.randint(4_000_000_000, 4_999_999_999),
            "environment": env,
            "original_environment": env,
            "production_environment": env == "PRD",
            "transient_environment": False,
            "task": "deploy",
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
    es = Elasticsearch(
        ES_URL,
        basic_auth=(ES_USER, ES_PASSWORD),
        verify_certs=False,
    )

    print(f"📡 Conectando ao Elasticsearch em {ES_URL}...")
    info = es.info()
    print(f"✅ Conectado — Elasticsearch {info['version']['number']}")

    now = datetime.now(timezone.utc)
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
        chunk_size=100,
        refresh="wait_for",
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

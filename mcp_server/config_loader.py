import os
import yaml
from dotenv import load_dotenv

load_dotenv()


def load_config(config_path: str = None) -> dict:
    """
    Carrega o config.yaml resolvendo o caminho de forma inteligente:
    1. Se o caminho for absoluto, usa diretamente.
    2. Se for relativo, tenta resolver a partir do diretório do arquivo
       que chamou (mcp_server/) e depois a partir da raiz do projeto.
    """
    if config_path is None:
        config_path = "config.yaml"

    # Tenta caminhos candidatos em ordem de prioridade
    candidates = []

    if os.path.isabs(config_path):
        candidates.append(config_path)
    else:
        # 1. Relativo ao diretório do config_loader.py (mcp_server/../)
        this_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(this_dir, config_path))
        candidates.append(os.path.join(this_dir, "..", config_path))

        # 2. Relativo ao cwd
        candidates.append(os.path.abspath(config_path))

        # 3. Raiz do projeto (dois níveis acima do arquivo atual)
        project_root = os.path.abspath(os.path.join(this_dir, ".."))
        candidates.append(os.path.join(project_root, "config.yaml"))

    resolved = None
    for candidate in candidates:
        normalized = os.path.normpath(candidate)
        if os.path.isfile(normalized):
            resolved = normalized
            break

    if not resolved:
        checked = "\n  ".join(set(os.path.normpath(c) for c in candidates))
        raise FileNotFoundError(
            f"config.yaml não encontrado. Caminhos verificados:\n  {checked}"
        )

    with open(resolved, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Substitui variáveis de ambiente nos valores
    config = _resolve_env_vars(config)
    config = _apply_environment_overrides(config)

    return config


def _resolve_env_vars(obj):
    """Substitui ${VAR} pelos valores das variáveis de ambiente."""
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    elif isinstance(obj, str):
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')
        def replacer(match):
            var_name = match.group(1)
            value = os.getenv(var_name, "")
            return value
        return pattern.sub(replacer, obj)
    return obj


def _apply_environment_overrides(config: dict) -> dict:
    es_cfg = config.setdefault("elasticsearch", {})
    agent_cfg = config.setdefault("agent", {})
    if os.getenv("ELASTICSEARCH_URL"):
        es_cfg["url"] = os.getenv("ELASTICSEARCH_URL")
    if os.getenv("ELASTICSEARCH_USERNAME"):
        es_cfg["username"] = os.getenv("ELASTICSEARCH_USERNAME")
    if os.getenv("ELASTIC_PASSWORD"):
        es_cfg["password"] = os.getenv("ELASTIC_PASSWORD")
    if os.getenv("ELASTICSEARCH_INDEX"):
        es_cfg["index"] = os.getenv("ELASTICSEARCH_INDEX")
    if os.getenv("ELASTICSEARCH_API_KEY"):
        es_cfg["api_key"] = os.getenv("ELASTICSEARCH_API_KEY")
    if os.getenv("ELASTICSEARCH_AUTH_MODE"):
        es_cfg["auth_mode"] = os.getenv("ELASTICSEARCH_AUTH_MODE")
    if os.getenv("ELASTICSEARCH_CA_CERTS"):
        es_cfg["ca_certs"] = os.getenv("ELASTICSEARCH_CA_CERTS")
    if os.getenv("ELASTICSEARCH_CLIENT_CERT"):
        es_cfg["client_cert"] = os.getenv("ELASTICSEARCH_CLIENT_CERT")
    if os.getenv("ELASTICSEARCH_CLIENT_KEY"):
        es_cfg["client_key"] = os.getenv("ELASTICSEARCH_CLIENT_KEY")
    if os.getenv("ELASTICSEARCH_SSL_FINGERPRINT"):
        es_cfg["ssl_assert_fingerprint"] = os.getenv("ELASTICSEARCH_SSL_FINGERPRINT")

    if os.getenv("AGENT_PROVIDER"):
        agent_cfg["provider"] = os.getenv("AGENT_PROVIDER")
    if os.getenv("OLLAMA_API_BASE"):
        agent_cfg["api_base"] = os.getenv("OLLAMA_API_BASE")
    if os.getenv("OLLAMA_MODEL"):
        agent_cfg["ollama_model"] = os.getenv("OLLAMA_MODEL")
        if not os.getenv("LLM_MODEL"):
            agent_cfg["model"] = os.getenv("OLLAMA_MODEL")
    if os.getenv("GROQ_API_KEY"):
        agent_cfg["api_key"] = os.getenv("GROQ_API_KEY")
    if os.getenv("LLM_MODEL"):
        agent_cfg["model"] = os.getenv("LLM_MODEL")

    verify_ssl = os.getenv("ELASTICSEARCH_VERIFY_SSL")
    if verify_ssl is not None and verify_ssl != "":
        es_cfg["verify_ssl"] = verify_ssl.strip().lower() in {"1", "true", "yes", "on"}

    skip_tls = os.getenv("ELASTICSEARCH_SKIP_TLS_VERIFY")
    if skip_tls is not None and skip_tls != "":
        es_cfg["skip_tls_verify"] = skip_tls.strip().lower() in {"1", "true", "yes", "on"}
        if es_cfg["skip_tls_verify"]:
            es_cfg["verify_ssl"] = False

    assert_hostname = os.getenv("ELASTICSEARCH_SSL_ASSERT_HOSTNAME")
    if assert_hostname is not None and assert_hostname != "":
        es_cfg["ssl_assert_hostname"] = assert_hostname.strip().lower() in {"1", "true", "yes", "on"}

    timeout = os.getenv("ELASTICSEARCH_TIMEOUT")
    if timeout:
        es_cfg["timeout"] = int(timeout)

    ollama_timeout = os.getenv("OLLAMA_TIMEOUT")
    if ollama_timeout:
        agent_cfg["ollama_timeout"] = int(ollama_timeout)

    openai_cfg = agent_cfg.setdefault("openai_compatible", {})
    if os.getenv("LLM_API_BASE"):
        openai_cfg["api_base"] = os.getenv("LLM_API_BASE")
    if os.getenv("LLM_API_KEY"):
        openai_cfg["api_key"] = os.getenv("LLM_API_KEY")
    if os.getenv("LLM_MODEL"):
        openai_cfg["model"] = os.getenv("LLM_MODEL")
    if os.getenv("LLM_TIMEOUT"):
        openai_cfg["timeout"] = int(os.getenv("LLM_TIMEOUT"))
    if os.getenv("LLM_AUTH_HEADER"):
        openai_cfg["auth_header"] = os.getenv("LLM_AUTH_HEADER")
    if os.getenv("LLM_AUTH_SCHEME") is not None:
        openai_cfg["auth_scheme"] = os.getenv("LLM_AUTH_SCHEME")

    service_cfg = agent_cfg.setdefault("service", {})
    if os.getenv("AGENT_HTTP_HOST"):
        service_cfg["host"] = os.getenv("AGENT_HTTP_HOST")
    if os.getenv("AGENT_HTTP_PORT"):
        service_cfg["port"] = int(os.getenv("AGENT_HTTP_PORT"))
    if os.getenv("AGENT_HTTP_REQUEST_TIMEOUT"):
        service_cfg["request_timeout_seconds"] = int(os.getenv("AGENT_HTTP_REQUEST_TIMEOUT"))
    if os.getenv("AGENT_HTTP_JSON_LOGS") is not None:
        service_cfg["json_logs"] = os.getenv("AGENT_HTTP_JSON_LOGS").strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("AGENT_HTTP_LOG_LEVEL"):
        service_cfg["log_level"] = os.getenv("AGENT_HTTP_LOG_LEVEL")

    auth_cfg = service_cfg.setdefault("auth", {})
    if os.getenv("AGENT_HTTP_AUTH_ENABLED") is not None:
        auth_cfg["enabled"] = os.getenv("AGENT_HTTP_AUTH_ENABLED").strip().lower() in {"1", "true", "yes", "on"}
    if os.getenv("AGENT_HTTP_AUTH_HEADER"):
        auth_cfg["header_name"] = os.getenv("AGENT_HTTP_AUTH_HEADER")
    if os.getenv("AGENT_HTTP_BEARER_TOKEN") is not None:
        auth_cfg["bearer_token"] = os.getenv("AGENT_HTTP_BEARER_TOKEN")

    runtime_cfg = agent_cfg.setdefault("runtime", {})
    if os.getenv("AGENT_SCHEMA_CACHE_TTL_SECONDS"):
        runtime_cfg["schema_cache_ttl_seconds"] = int(os.getenv("AGENT_SCHEMA_CACHE_TTL_SECONDS"))

    return config


def get_es_config(config: dict) -> dict:
    """Retorna apenas a seção do Elasticsearch."""
    return config.get("elasticsearch", {})


def get_agent_config(config: dict) -> dict:
    """Retorna apenas a seção do agente."""
    return config.get("agent", {})


def get_mcp_config(config: dict) -> dict:
    """Retorna apenas a seção do MCP."""
    return config.get("mcp", {})


def get_specialty_config(config: dict) -> dict:
    """Retorna apenas a seção de especialidade."""
    return config.get("specialty", {})

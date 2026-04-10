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

    env_map = {
        ("elasticsearch", "url"): os.getenv("ELASTICSEARCH_URL"),
        ("elasticsearch", "username"): os.getenv("ELASTICSEARCH_USERNAME"),
        ("elasticsearch", "password"): os.getenv("ELASTIC_PASSWORD"),
        ("elasticsearch", "index"): os.getenv("ELASTICSEARCH_INDEX"),
        ("agent", "provider"): os.getenv("AGENT_PROVIDER"),
        ("agent", "api_base"): os.getenv("OLLAMA_API_BASE"),
        ("agent", "model"): os.getenv("OLLAMA_MODEL"),
        ("agent", "ollama_model"): os.getenv("OLLAMA_MODEL"),
        ("agent", "api_key"): os.getenv("GROQ_API_KEY"),
        ("agent", "model"): os.getenv("LLM_MODEL"),
    }

    for (section, key), value in env_map.items():
        if value:
            config.setdefault(section, {})[key] = value

    verify_ssl = os.getenv("ELASTICSEARCH_VERIFY_SSL")
    if verify_ssl is not None and verify_ssl != "":
        es_cfg["verify_ssl"] = verify_ssl.strip().lower() in {"1", "true", "yes", "on"}

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

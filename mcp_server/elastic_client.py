"""
Wrapper do cliente Elasticsearch.
Centraliza conexão e tratamento de erros.
"""

from elasticsearch import Elasticsearch
from config_loader import load_config


def get_client(config: dict | None = None) -> Elasticsearch:
    if config is None:
        config = load_config()

    es_cfg = config["elasticsearch"]
    es_url = str(es_cfg["url"])
    is_https = es_url.lower().startswith("https://")
    verify_ssl = bool(es_cfg.get("verify_ssl", False))
    if es_cfg.get("skip_tls_verify"):
        verify_ssl = False

    kwargs = dict(
        verify_certs=verify_ssl,
        request_timeout=es_cfg.get("timeout", 15),
        max_retries=es_cfg.get("max_retries", 3),
        retry_on_timeout=True,
        ssl_show_warn=False if not verify_ssl else es_cfg.get("ssl_show_warn", True),
    )

    if is_https and es_cfg.get("ca_certs"):
        kwargs["ca_certs"] = es_cfg["ca_certs"]
    if is_https and es_cfg.get("client_cert"):
        kwargs["client_cert"] = es_cfg["client_cert"]
    if is_https and es_cfg.get("client_key"):
        kwargs["client_key"] = es_cfg["client_key"]
    if is_https and es_cfg.get("ssl_assert_hostname") is not None:
        kwargs["ssl_assert_hostname"] = bool(es_cfg.get("ssl_assert_hostname"))
    if is_https and es_cfg.get("ssl_assert_fingerprint"):
        kwargs["ssl_assert_fingerprint"] = es_cfg["ssl_assert_fingerprint"]

    auth_mode = str(es_cfg.get("auth_mode", "auto")).lower()
    has_basic_auth = bool(es_cfg.get("username") and es_cfg.get("password"))
    has_api_key = bool(es_cfg.get("api_key"))

    if has_api_key and auth_mode == "api_key":
        kwargs["api_key"] = es_cfg["api_key"]
    elif has_basic_auth and auth_mode in {"auto", "basic", "basic_auth"}:
        kwargs["basic_auth"] = (es_cfg["username"], es_cfg["password"])
    elif has_api_key:
        kwargs["api_key"] = es_cfg["api_key"]
    elif has_basic_auth:
        kwargs["basic_auth"] = (es_cfg["username"], es_cfg["password"])

    client = Elasticsearch(es_url, **kwargs)
    return client


def get_index(config: dict | None = None) -> str:
    if config is None:
        config = load_config()
    return config["elasticsearch"]["index"]

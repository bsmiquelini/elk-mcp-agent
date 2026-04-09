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

    kwargs = dict(
        verify_certs=es_cfg.get("verify_ssl", False),
        request_timeout=es_cfg.get("timeout", 15),
        max_retries=es_cfg.get("max_retries", 3),
        retry_on_timeout=True,
    )

    if es_cfg.get("api_key"):
        kwargs["api_key"] = es_cfg["api_key"]
    elif es_cfg.get("username") and es_cfg.get("password"):
        kwargs["basic_auth"] = (es_cfg["username"], es_cfg["password"])

    client = Elasticsearch(es_cfg["url"], **kwargs)
    return client


def get_index(config: dict | None = None) -> str:
    if config is None:
        config = load_config()
    return config["elasticsearch"]["index"]

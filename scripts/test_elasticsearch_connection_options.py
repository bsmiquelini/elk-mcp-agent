"""
Valida overrides de conexão com Elasticsearch: HTTPS, CA, API key e skip TLS.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))

from config_loader import load_config
from elastic_client import get_client


def assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main():
    env_updates = {
        "ELASTICSEARCH_URL": "https://elk.example.internal:9243",
        "ELASTICSEARCH_USERNAME": "elastic",
        "ELASTIC_PASSWORD": "secret",
        "ELASTICSEARCH_INDEX": "github-workflows-prod*",
        "ELASTICSEARCH_VERIFY_SSL": "true",
        "ELASTICSEARCH_CA_CERTS": "/etc/ssl/certs/ca.pem",
        "ELASTICSEARCH_CLIENT_CERT": "/etc/ssl/certs/client.pem",
        "ELASTICSEARCH_CLIENT_KEY": "/etc/ssl/private/client.key",
        "ELASTICSEARCH_SSL_ASSERT_HOSTNAME": "true",
        "ELASTICSEARCH_SSL_FINGERPRINT": "AA:BB:CC",
        "ELASTICSEARCH_API_KEY": "base64-api-key",
        "ELASTICSEARCH_AUTH_MODE": "api_key",
    }
    previous = {key: os.environ.get(key) for key in env_updates}
    try:
        os.environ.update(env_updates)
        config = load_config(str(ROOT / "config.yaml"))
        with patch("elastic_client.Elasticsearch") as mocked:
            get_client(config)
            args, kwargs = mocked.call_args

        assert_true(args[0] == "https://elk.example.internal:9243", f"URL incorreta: {args}")
        assert_true(kwargs["verify_certs"] is True, f"verify_certs incorreto: {kwargs}")
        assert_true(kwargs["ca_certs"] == "/etc/ssl/certs/ca.pem", "CA cert ausente")
        assert_true(kwargs["client_cert"] == "/etc/ssl/certs/client.pem", "client_cert ausente")
        assert_true(kwargs["client_key"] == "/etc/ssl/private/client.key", "client_key ausente")
        assert_true(kwargs["ssl_assert_hostname"] is True, "ssl_assert_hostname incorreto")
        assert_true(kwargs["ssl_assert_fingerprint"] == "AA:BB:CC", "fingerprint ausente")
        assert_true(kwargs["api_key"] == "base64-api-key", "api_key ausente")
        assert_true("basic_auth" not in kwargs, "basic_auth nao deveria ser usado quando api_key existe")

        os.environ["ELASTICSEARCH_SKIP_TLS_VERIFY"] = "true"
        config = load_config(str(ROOT / "config.yaml"))
        with patch("elastic_client.Elasticsearch") as mocked:
            get_client(config)
            _, kwargs = mocked.call_args
        assert_true(kwargs["verify_certs"] is False, "skip TLS nao derrubou verify_certs")
        assert_true(kwargs["ssl_show_warn"] is False, "ssl_show_warn deveria ser false com skip TLS")

        print("OK: conexão com Elasticsearch suporta HTTPS, CA, API key e skip TLS.")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.environ.pop("ELASTICSEARCH_SKIP_TLS_VERIFY", None)


if __name__ == "__main__":
    main()

# elk-mcp-agent

Agente de inteligência para análise de esteiras CI/CD com Elasticsearch, MCP e consumo por `CLI` ou `HTTP`.

## Visão geral

O projeto foi organizado para operar em dois modos:

- **modo repositório**: usa `docker-compose.yml`, `infra/` e `scripts/` para testes locais e validação integrada
- **modo imagem**: usa a imagem publicada do agente, sem carregar a infraestrutura local para dentro do container

Detalhes dos modos em [docs/testing-modes.md](/home/bruno/lab_ia/elk-mcp-agent/docs/testing-modes.md).

## Componentes

- `agent/`: CLI, serviço HTTP, respostas diretas, dashboards e relatórios
- `mcp_server/`: tools dinâmicas sobre Elasticsearch
- `scripts/`: bootstrap, seed e suítes de teste
- `config.yaml`: configuração central
- `docker-compose.yml`: stack local de validação
- `ollama/Dockerfile`: imagem customizada do Ollama com preload de modelo

## Teste local pelo repositório

Suba a stack local:

```bash
docker compose up -d elasticsearch kibana ollama openwebui nginx
bash scripts/setup.sh
```

Opcionalmente, suba também os containers do projeto:

```bash
docker compose --profile app up -d --build
```

URLs úteis:

- `http://localhost:3000`: Open WebUI
- `http://localhost`: Open WebUI via Nginx
- `https://localhost`: Kibana via Nginx
- `https://localhost:9243`: Elasticsearch via Nginx

Observação:

- por padrão, o `docker-compose` publica o Ollama em `11435` no host
- para sobrescrever: `OLLAMA_HOST_PORT=11434 docker compose up -d ollama`

## Variáveis de ambiente

As variáveis abaixo podem ser usadas tanto no shell quanto em `--env-file`.

### Elasticsearch

| Variável | Uso |
| --- | --- |
| `ELASTICSEARCH_URL` | URL do Elasticsearch, incluindo `http://` ou `https://` |
| `ELASTICSEARCH_USERNAME` | usuário para `basic_auth` |
| `ELASTIC_PASSWORD` | senha para `basic_auth` |
| `ELASTICSEARCH_AUTH_MODE` | `auto`, `basic_auth` ou `api_key` |
| `ELASTICSEARCH_API_KEY` | API key do Elasticsearch |
| `ELASTICSEARCH_INDEX` | pattern do índice, ex. `github-workflows*` |
| `ELASTICSEARCH_TIMEOUT` | timeout em segundos |
| `ELASTICSEARCH_VERIFY_SSL` | validação TLS do servidor |
| `ELASTICSEARCH_SKIP_TLS_VERIFY` | força `skip TLS` |
| `ELASTICSEARCH_CA_CERTS` | caminho do CA bundle |
| `ELASTICSEARCH_CLIENT_CERT` | caminho do client certificate |
| `ELASTICSEARCH_CLIENT_KEY` | caminho da client key |
| `ELASTICSEARCH_SSL_ASSERT_HOSTNAME` | validação de hostname |
| `ELASTICSEARCH_SSL_FINGERPRINT` | fingerprint TLS opcional |

### Provider do agente

| Variável | Uso |
| --- | --- |
| `AGENT_PROVIDER` | `ollama`, `openai_compatible` ou `groq` |
| `OLLAMA_API_BASE` | endpoint do Ollama |
| `OLLAMA_MODEL` | modelo Ollama |
| `OLLAMA_TIMEOUT` | timeout do provider Ollama |
| `LLM_API_BASE` | endpoint OpenAI-compatible |
| `LLM_MODEL` | modelo do gateway corporativo |
| `LLM_API_KEY` | token/chave do gateway |
| `LLM_AUTH_HEADER` | header de autenticação do gateway |
| `LLM_AUTH_SCHEME` | esquema do header, ex. `Bearer` |
| `GROQ_API_KEY` | chave do provider Groq |

### Serviço HTTP

| Variável | Uso |
| --- | --- |
| `AGENT_HTTP_HOST` | host do serviço |
| `AGENT_HTTP_PORT` | porta do serviço |
| `AGENT_HTTP_REQUEST_TIMEOUT` | timeout por request |
| `AGENT_HTTP_MAX_BODY_BYTES` | limite máximo do payload HTTP |
| `AGENT_HTTP_JSON_LOGS` | logs estruturados JSON |
| `AGENT_HTTP_LOG_LEVEL` | nível de log |
| `AGENT_HTTP_AUTH_ENABLED` | habilita bearer token |
| `AGENT_HTTP_AUTH_HEADER` | nome do header de auth |
| `AGENT_HTTP_BEARER_TOKEN` | token bearer do serviço |
| `AGENT_SCHEMA_CACHE_TTL_SECONDS` | TTL do cache de schema |

Exemplos completos estão em [deploy/env/production.env.example](/home/bruno/lab_ia/elk-mcp-agent/deploy/env/production.env.example) e [.env.example](/home/bruno/lab_ia/elk-mcp-agent/.env.example).

## Elasticsearch via HTTPS, CA e skip TLS

### Exemplo com HTTPS e CA

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=https://elk.intra.example:9243 \
  -e ELASTICSEARCH_USERNAME=elastic \
  -e ELASTIC_PASSWORD=troque-a-senha \
  -e ELASTICSEARCH_VERIFY_SSL=true \
  -e ELASTICSEARCH_CA_CERTS=/app/certs/ca.pem \
  -v $(pwd)/certs:/app/certs:ro \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3 \
  agent/main.py --question "Qual foi o ultimo workflow que falhou em produção?"
```

### Exemplo com API key

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=https://elk.intra.example:9243 \
  -e ELASTICSEARCH_AUTH_MODE=api_key \
  -e ELASTICSEARCH_API_KEY=base64-api-key \
  -e ELASTICSEARCH_VERIFY_SSL=true \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3 \
  agent/main.py --question "Liste os repositorios que ja executaram workflows em algum momento"
```

### Exemplo com skip TLS

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=https://elk.intra.example:9243 \
  -e ELASTICSEARCH_USERNAME=elastic \
  -e ELASTIC_PASSWORD=troque-a-senha \
  -e ELASTICSEARCH_SKIP_TLS_VERIFY=true \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3 \
  agent/main.py --question "Quais arquiteturas executaram deploy no ultimo mes?"
```

## Uso da imagem do agente

Imagem de exemplo:

```bash
ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3
```

### CLI

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=http://host.docker.internal:9200 \
  -e ELASTICSEARCH_USERNAME=elastic \
  -e ELASTIC_PASSWORD=changeme123 \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE=http://host.docker.internal:11435 \
  -e OLLAMA_MODEL=qwen2.5:7b \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3
```

### CLI com overrides adicionais

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=https://elk.intra.example:9243 \
  -e ELASTICSEARCH_AUTH_MODE=api_key \
  -e ELASTICSEARCH_API_KEY=base64-api-key \
  -e ELASTICSEARCH_SKIP_TLS_VERIFY=true \
  -e AGENT_PROVIDER=openai_compatible \
  -e LLM_API_BASE=https://llm-gateway.intra.example/v1 \
  -e LLM_MODEL=qwen2.5-72b-instruct \
  -e LLM_API_KEY=token-interno \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3 \
  agent/main.py --question "Qual a porcentagem de falha e sucesso em esteiras de api?"
```

### Serviço HTTP

```bash
docker run --rm -p 8787:8787 \
  --env-file deploy/env/production.env.example \
  -e ELASTICSEARCH_URL=http://host.docker.internal:9200 \
  -e ELASTICSEARCH_USERNAME=elastic \
  -e ELASTIC_PASSWORD=changeme123 \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE=http://host.docker.internal:11435 \
  -e OLLAMA_MODEL=qwen2.5:7b \
  -e AGENT_HTTP_AUTH_ENABLED=true \
  -e AGENT_HTTP_BEARER_TOKEN=troque-este-token \
  ghcr.io/bsmiquelini/elk-mcp-agent-agent:sha-441fbf3 \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

Pergunta via API:

```bash
curl -s http://localhost:8787/v1/ask \
  -H 'Authorization: Bearer troque-este-token' \
  -H 'Content-Type: application/json' \
  -d '{"question":"Qual foi o ultimo workflow que falhou em produção?"}'
```

Relatório executivo via API:

```bash
curl -s http://localhost:8787/v1/report \
  -H 'Authorization: Bearer troque-este-token' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt":"Quero um resumo executivo de CI/CD com foco em risco operacional e PRD",
    "time_range":"30d",
    "include":"overview,risk,success,lead_time,approvals,prd",
    "title":"Resumo Executivo CI/CD"
  }'
```

## Healthcheck do serviço HTTP

O `http_service.py` agora sobe com logs estruturados e os endpoints:

- `GET /healthz`
- `GET /readyz`
- `POST /v1/ask`
- `POST /v1/report`

O `healthcheck` informa se:

- o Elasticsearch está acessível
- o provider/modelo de inferência está acessível

Semântica operacional:

- `GET /healthz` retorna `200` quando o processo HTTP está vivo, mesmo se alguma dependência estiver degradada.
- `GET /readyz` retorna `200` somente quando Elasticsearch e provider/modelo estão acessíveis.
- `GET /readyz` retorna `503` com `status: not_ready` quando o serviço ainda não deve receber tráfego.
- Payloads maiores que `AGENT_HTTP_MAX_BODY_BYTES` retornam `413 payload_too_large`.

Exemplo:

```bash
curl -s http://localhost:8787/healthz | python3 -m json.tool
```

## Imagem customizada do Ollama

Imagem prevista para publicação:

```bash
ghcr.io/bsmiquelini/elk-mcp-agent-ollama:sha-441fbf3
```

Ela usa [ollama/Dockerfile](/home/bruno/lab_ia/elk-mcp-agent/ollama/Dockerfile) e [entrypoint.sh](/home/bruno/lab_ia/elk-mcp-agent/ollama/entrypoint.sh), com preload configurável do modelo.

Exemplo:

```bash
docker run --rm -p 11434:11434 \
  -e OLLAMA_PRELOAD_MODEL=qwen2.5:7b \
  ghcr.io/bsmiquelini/elk-mcp-agent-ollama:sha-441fbf3
```

Observação:

- na primeira subida, a imagem tenta baixar o modelo se ele ainda não estiver disponível
- para produção corporativa, o recomendado continua sendo `AGENT_PROVIDER=openai_compatible`

## Relatórios executivos

```bash
python3 scripts/generate_director_report.py \
  --prompt "Quero um resumo executivo de CI/CD com foco em risco operacional, sucesso em PRD, lead time e aprovacoes pendentes" \
  --time-range 30d \
  --include overview,risk,success,lead_time,approvals,prd
```

O HTML é salvo em `artifacts/reports/`.

## Testes

Validações rápidas:

```bash
python3 -m compileall agent mcp_server scripts
python3 scripts/test_llm_provider_gateway.py
python3 scripts/test_elasticsearch_connection_options.py
python3 scripts/test_ui_rendering.py
python3 scripts/test_mvp_queries.py
python3 scripts/test_http_service.py
python3 scripts/test_http_service_auth.py
python3 scripts/test_http_readiness_degraded.py
python3 scripts/test_http_report_service.py
python3 scripts/test_executive_report_prompts.py
```

Suíte completa:

```bash
python3 scripts/test_full_300_validated.py
```

Em máquinas mais lentas ou sob carga, a suíte da CLI permite aumentar o timeout por pergunta sem reduzir a validação de conteúdo:

```bash
CLI_TEST_TIMEOUT_SECONDS=120 python3 scripts/test_full_300_validated.py
```

Teste de build das imagens:

```bash
docker buildx build --load -t elk-mcp-agent:test -f agent/Dockerfile .
docker run --rm elk-mcp-agent:test agent/main.py --help
docker run --rm elk-mcp-agent:test agent/http_service.py --help

docker buildx build --load -t elk-mcp-server:test -f mcp_server/Dockerfile .
docker run --rm elk-mcp-server:test -m compileall mcp_server

docker buildx build --load -t elk-mcp-ollama:test -f ollama/Dockerfile .
docker run --rm --entrypoint ollama elk-mcp-ollama:test --version
```

Validação local de segurança:

```bash
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect --source=/repo --redact --no-banner

docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.69.3 image --scanners vuln --exit-code 1 --ignore-unfixed --severity CRITICAL,HIGH --pkg-types os,library elk-mcp-agent:test
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.69.3 image --scanners vuln --exit-code 1 --ignore-unfixed --severity CRITICAL,HIGH --pkg-types os,library elk-mcp-server:test
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.69.3 image --scanners vuln --exit-code 1 --ignore-unfixed --severity CRITICAL,HIGH --pkg-types os elk-mcp-ollama:test
```

Os workflows de build/push no GitHub Actions executam Gitleaks antes dos builds e Trivy Action `v0.35.0` com Trivy `v0.69.3` nas imagens antes do push para o GHCR. A baseline [.gitleaksignore](/home/bruno/lab_ia/elk-mcp-agent/.gitleaksignore) registra apenas achados históricos já removidos do estado atual.

## Outras referências

- [deploy/README.md](/home/bruno/lab_ia/elk-mcp-agent/deploy/README.md)
- [docs/testing-modes.md](/home/bruno/lab_ia/elk-mcp-agent/docs/testing-modes.md)
- [docs/production-plan.md](/home/bruno/lab_ia/elk-mcp-agent/docs/production-plan.md)
- [docs/production-readiness-plan.md](/home/bruno/lab_ia/elk-mcp-agent/docs/production-readiness-plan.md)

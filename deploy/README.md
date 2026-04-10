# Deploy

Esta pasta concentra os artefatos práticos de publicação do projeto.

## Estrutura

- `docker-bake.hcl`: build/push das imagens do `agent` e do `mcp_server`
- `env/production.env.example`: exemplo de variáveis para produção
- `k8s/`: manifests Kubernetes prontos para adaptação
- `helm/`: exemplos de `values.yaml` para Helm

## Build com buildx bake

Build local:

```bash
docker buildx bake -f deploy/docker-bake.hcl images
```

Build e push:

```bash
docker buildx bake -f deploy/docker-bake.hcl release --push
```

Com override de registry/tag:

```bash
REGISTRY=registry.exemplo.intra \
IMAGE_NAMESPACE=observability \
VERSION=v1.0.0 \
docker buildx bake -f deploy/docker-bake.hcl release --push
```

## Build e push via GitHub Actions

O workflow [build-agent-image.yml](/home/bruno/lab_ia/elk-mcp-agent/.github/workflows/build-agent-image.yml) publica a imagem do agente no GHCR usando o `GITHUB_TOKEN` do repositório.

Imagem publicada:

```bash
ghcr.io/<owner>/elk-mcp-agent-agent
```

Tags geradas:
- nome da branch
- tag Git
- `sha-<commit>`
- `latest` na branch padrão

Uso em CLI:

```bash
docker run --rm -it ghcr.io/<owner>/elk-mcp-agent-agent:develop
```

Uso como serviço HTTP:

```bash
docker run --rm -p 8787:8787 \
  ghcr.io/<owner>/elk-mcp-agent-agent:develop \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

## CI antes do publish

O workflow [ci-agent.yml](/home/bruno/lab_ia/elk-mcp-agent/.github/workflows/ci-agent.yml) valida:
- compilacao e testes rapidos do agente
- integracao com Elasticsearch seeded
- smoke do modo CLI
- smoke do modo HTTP
- smoke do modo HTTP com bearer token

Recomendacao operacional:
- exigir `Agent CI` como check obrigatorio antes de merge
- deixar o workflow de build/push publicar apenas a partir de branches protegidas

## Kubernetes

Para produção interna, o caminho recomendado deixa o modelo atrás de um gateway
OpenAI-compatible corporativo. O `Ollama` pode continuar existindo como
laboratório, benchmark ou fallback controlado, mas não deve ser dependência do
desktop do usuário final.

Arquivos principais:

- `k8s/namespace.yaml`
- `k8s/configmap.yaml`
- `k8s/secret.example.yaml`
- `k8s/ollama.yaml`
- `k8s/agent.yaml`
- `k8s/mcp-server.yaml`
- `k8s/agent-question-job.yaml`

Aplicação base:

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/ollama.yaml
kubectl apply -f deploy/k8s/agent.yaml
kubectl apply -f deploy/k8s/mcp-server.yaml
```

Execução de pergunta via Job:

```bash
kubectl apply -f deploy/k8s/agent-question-job.yaml
kubectl -n observability-ai logs -f job/elk-mcp-agent-question
```

## Helm

Arquivos principais:

- `helm/ollama-values.yaml`
- `helm/agent-values.yaml`
- `helm/README.md`

Os exemplos usam charts externos para Ollama e um chart hipotético para o `agent`, servindo como base de parametrização.

## Provider recomendado para produção

Exemplo de variáveis:

```bash
AGENT_PROVIDER=openai_compatible
LLM_API_BASE=https://llm-gateway.exemplo.intra/v1
LLM_MODEL=qwen2.5-72b-instruct
LLM_API_KEY=
LLM_AUTH_HEADER=Authorization
LLM_AUTH_SCHEME=Bearer
```

Esse modo é o mais indicado quando:

- o usuário não pode instalar `Ollama`
- o acesso a modelos é centralizado pela empresa
- o cliente não deve depender de chaves individuais
- a camada de inferência precisa escalar separadamente do agente/MCP

## API HTTP interna

O agente tambem pode ser publicado como um servico HTTP interno para evitar o
uso exclusivo da CLI.

Execucao local:

```bash
python3 agent/http_service.py --host 0.0.0.0 --port 8787
```

Healthcheck:

```bash
curl -s http://localhost:8787/healthz
```

Pergunta via API:

```bash
curl -s http://localhost:8787/v1/ask \
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
    "include":"overview,risk,prd",
    "title":"Resumo Executivo CI/CD"
  }'
```

Em container:

```bash
docker run --rm -p 8787:8787 \
  --env-file deploy/env/production.env.example \
  <imagem-agent> \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

Recursos operacionais recomendados:

- autenticação bearer via `AGENT_HTTP_AUTH_ENABLED=true`
- logs JSON via `AGENT_HTTP_JSON_LOGS=true`
- cache de schema via `AGENT_SCHEMA_CACHE_TTL_SECONDS=300`
- provider corporativo via `AGENT_PROVIDER=openai_compatible`

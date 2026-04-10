# Modos de Teste e Operação

Este projeto pode ser usado de duas formas complementares:

1. pelo próprio repositório, com `docker compose`, `infra/` e utilitários locais
2. pela imagem do agente, em modo `CLI` ou `HTTP`, apontando para serviços já existentes

Essa separação é intencional:

- `docker-compose.yml` e `infra/` ficam versionados para facilitar testes reais, demos e troubleshooting no repositório
- esses arquivos **não** entram na imagem final do agente
- a imagem carrega apenas o runtime necessário para `agent`, `mcp_server`, `scripts`, `config.yaml`, `README.md` e `.env.example`

## Modo 1. Teste pelo repositório

Esse é o melhor caminho para desenvolvimento local e validação integrada.

O stack versionado no repositório pode subir:

- `elasticsearch`
- `kibana`
- `ollama`
- `openwebui`
- `nginx`
- `agent`
- `mcp_server`

Exemplo:

```bash
docker compose up -d elasticsearch kibana ollama openwebui nginx
bash scripts/setup.sh
python3 agent/main.py --question "Qual foi o ultimo workflow que falhou em produção?"
python3 agent/http_service.py --host 0.0.0.0 --port 8787
```

Por padrão, o `Ollama` do `docker-compose` é publicado em `11435` no host. Isso
evita colisão com um `Ollama` desktop já rodando em `11434`.

Se quiser sobrescrever:

```bash
OLLAMA_HOST_PORT=11434 docker compose up -d ollama
```

Quando quiser validar a stack completa do repositório:

```bash
docker compose --profile app up -d --build
python3 scripts/test_http_service.py
python3 scripts/test_http_service_auth.py
python3 scripts/test_http_report_service.py
```

Esse modo é útil para:

- desenvolvimento e debugging
- validação visual com Open WebUI e Nginx
- testes locais de integração
- troubleshooting de conectividade com Elasticsearch e Ollama

## Modo 2. Teste pela imagem

Esse é o modo mais próximo da publicação de produção do agente.

Exemplo de build local:

```bash
docker buildx build --load -t elk-mcp-agent:test -f agent/Dockerfile .
```

Uso em CLI:

```bash
docker run --rm -it \
  --env-file deploy/env/production.env.example \
  elk-mcp-agent:test
```

Uso como serviço HTTP:

```bash
docker run --rm -p 8787:8787 \
  --env-file deploy/env/production.env.example \
  elk-mcp-agent:test \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

Esse modo é útil para:

- smoke test da imagem publicada
- validação em ambientes remotos
- execução centralizada em VM ou Kubernetes
- garantir que a imagem não dependa dos artefatos de infraestrutura do repositório

## O que entra e o que não entra na imagem

Entram na imagem:

- `agent/`
- `mcp_server/`
- `scripts/`
- `config.yaml`
- `README.md`
- `.env.example`

Não entram na imagem:

- `docker-compose.yml`
- `infra/`
- `artifacts/`
- `.github/`
- arquivos locais como `ideia`
- segredos e overrides locais

Essa proteção acontece em duas camadas:

- o [Dockerfile do agente](/home/bruno/lab_ia/elk-mcp-agent/agent/Dockerfile) copia apenas os diretórios e arquivos necessários
- o [.dockerignore](/home/bruno/lab_ia/elk-mcp-agent/.dockerignore) exclui explicitamente `docker-compose.yml`, `infra/` e outros artefatos de desenvolvimento

## Recomendação prática

Use assim:

- no dia a dia do time: teste pelo repositório
- para homologação de publicação: teste pela imagem
- para produção: publique a imagem e aponte para serviços centrais de `Elasticsearch` e `LLM`

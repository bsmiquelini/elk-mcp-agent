# 🤖 elk-mcp-agent

Agente de inteligência artificial local para análise de pipelines CI/CD. Combina Elasticsearch, Ollama (LLM local) e um servidor MCP (Model Context Protocol) para permitir consultas em linguagem natural sobre execuções de workflows do GitHub Actions.

## 🎯 Objetivo

Responder perguntas como "quais repositórios tiveram mais falhas esta semana?" sem que o usuário precise escrever queries Elasticsearch manualmente.

## 🏗️ Arquitetura

```plaintext
Usuário (linguagem natural)
  ↓
   agent/main.py          ← CLI interativa
  ↓
   Ollama (LLM local)     ← qwen2.5:3b ou mistral
  ↓
   MCP Server (stdio)     ← mcp_server/main.py
  ↓
   Elasticsearch 8.x      ← índice github-pipeline-executions
```

### Componentes

- **agent/** — CLI, session management, system prompt dinâmico
- **mcp_server/** — servidor MCP com 4 tools: discover_schema, explore_field, aggregate, search
- **mcp_server/tools/** — implementação das tools: aggregate.py, searcher.py, explore_field.py, discover_schema.py
- **config.yaml** — configuração central: conexão ES, domínio de negócio, vocabulário, thresholds
- **docker-compose.yml** — Elasticsearch 8.13 + Kibana

## ⚙️ Pré-requisitos

- Docker + Docker Compose
- Python 3.11+
- Ollama com modelo baixado (qwen2.5:3b ou mistral)

### Instalar dependências Python

```bash
pip install -r mcp_server/requirements.txt
```

### Subir o stack ELK

```bash
docker compose up -d elasticsearch

# Acompanhar startup (~1 min)
docker logs -f elk_elasticsearch 2>&1 | grep -E "started|error|warn"

# Subir Kibana (opcional)
docker compose up -d kibana
docker logs -f elk_kibana 2>&1 | grep -E "ready|error|warn"
```

## 🔧 Configuração

### .env

```plaintext
ELASTIC_PASSWORD=changeme123
KIBANA_SYSTEM_PASSWORD=changeme456
```

### config.yaml — seção Elasticsearch

```yaml
elasticsearch:
  url:        "http://localhost:9200"
  username:   "elastic"
  password:   "changeme123"
  verify_ssl: false
  timeout:    30
  index:      "github-pipeline-executions"
  time_field: "workflow_run.started_at"
  default_time_range: "7d"
```

⚠️ **Importante**: O índice `github-pipeline-executions` usa campos `jobs.*` como objetos planos (não nested). Não configure `nested_paths` no config — isso fará as queries retornarem `doc_count: 0`.

## 🚀 Rodar o agente

```bash
python3 agent/main.py
```

### Rodar como API HTTP interna

```bash
python3 agent/http_service.py --host 0.0.0.0 --port 8787
```

Endpoints:
- `GET /healthz`
- `POST /v1/ask`

Configurações importantes em [config.yaml](/home/bruno/lab_ia/elk-mcp-agent/config.yaml):
- `agent.service.auth.enabled`
- `agent.service.auth.bearer_token`
- `agent.service.json_logs`
- `agent.runtime.schema_cache_ttl_seconds`

Exemplo:

```bash
curl -s http://localhost:8787/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Qual foi o ultimo workflow que falhou em produção?"}'
```

Exemplo com autenticação bearer:

```bash
export AGENT_HTTP_AUTH_ENABLED=true
export AGENT_HTTP_BEARER_TOKEN=troque-este-token
python3 agent/http_service.py

curl -s http://localhost:8787/v1/ask \
  -H 'Authorization: Bearer troque-este-token' \
  -H 'Content-Type: application/json' \
  -d '{"question":"Qual foi o ultimo workflow que falhou em produção?"}'
```

### Provider corporativo recomendado

Para produção interna, prefira um gateway central OpenAI-compatible:

```bash
export AGENT_PROVIDER=openai_compatible
export LLM_API_BASE=https://llm-gateway.exemplo.intra/v1
export LLM_MODEL=qwen2.5-72b-instruct
python3 agent/main.py
```

Isso evita depender de `Ollama` na máquina do usuário final.

## 🧪 Regressão e refinamento

```bash
# Smoke rápido
python3 scripts/test_mvp_queries.py

# Bateria ampliada de linguagem natural
OLLAMA_API_BASE=http://127.0.0.1:11435 python3 scripts/test_cli_300_refinement.py

# Validação cruzada CLI x Elasticsearch
python3 scripts/test_cli_cross_validated.py

# Suíte completa do MVP
# 300 perguntas validadas contra o Elasticsearch + 20 relatórios executivos
OLLAMA_API_BASE=http://127.0.0.1:11435 python3 scripts/test_full_300_validated.py

# Smoke da API HTTP interna
python3 scripts/test_http_service.py

# Smoke da API HTTP com auth bearer
python3 scripts/test_http_service_auth.py
```

## 📈 Relatório executivo

```bash
python3 scripts/generate_director_report.py \
  --prompt "Quero um resumo executivo de CI/CD com foco em risco operacional, sucesso em PRD, lead time e aprovacoes pendentes"
```

O relatório consolidado é salvo em `artifacts/reports/` e referencia os dashboards HTML gerados em `artifacts/dashboards/`.

Também é possível customizar período, seções e título:

```bash
python3 scripts/generate_director_report.py \
  --prompt "Quero uma visão executiva das esteiras de api em produção" \
  --time-range 30d \
  --include overview,risk,success,prd,lead_time,approvals \
  --title "Resumo Executivo - APIs em Produção"
```

Seções disponíveis em `--include`:
- `overview`
- `risk`
- `success`
- `lead_time`
- `approvals`
- `analysts`
- `prd`
- `hml`
- `api`
- `srv`
- `bff`
- `java`
- `teams`

## 🎨 Personalização visual

O tema visual da CLI, dos dashboards HTML e dos relatórios executivos pode ser ajustado no bloco `ui` do [config.yaml](/home/bruno/lab_ia/elk-mcp-agent/config.yaml).

Exemplos suportados:
- `ui.branding.header_logo_png`: caminho para um PNG de logotipo exibido no cabeçalho do dashboard/relatório
- `ui.branding.favicon_png` ou `ui.branding.favicon_emoji`: favicon do HTML
- `ui.theme.accent`, `ui.theme.accent_2`, `ui.theme.background`: cores-base
- `ui.theme.page_background_image` e `ui.theme.panel_background_image`: imagens opcionais
- `ui.theme.custom_css_file`: CSS extra para customizações mais profundas
- `ui.cli.assistant_icon`, `ui.cli.user_icon`, `ui.cli.thinking_icon`: ícones da experiência no terminal

Teste rápido da camada visual:

```bash
python3 scripts/test_ui_rendering.py
```

## 💬 Perguntas de exemplo

Use estas perguntas diretamente na CLI do agente para interagir com os dados do Elasticsearch:

- Quantos tipos de jobs diferentes rodaram nos últimos 30 dias?
- Qual a taxa de falha por repositório nos últimos 90 dias?
- Quais os jobs com maior duração média?
- Quanto tempo em média leva o deploy-prod?
- Quais repositórios tiveram mais falhas na última semana?
- Liste os repositórios que já executaram workflows em algum momento
- Quais workflows da arquitetura de api foram executados no último mês?
- Qual foi o último workflow que falhou em produção?
- Liste os últimos projetos que tiveram deploy com falha
- Quais arquiteturas executaram deploy em PRD no último mês?
- Qual a porcentagem de falha e sucesso em deploys do time de devops?
- Quais os últimos deploys das esteiras de bff?

### Como escrever bons prompts

Perguntas mais objetivas tendem a gerar respostas melhores e mais rápidas. Tente combinar:
- métrica: `quantos`, `quais`, `qual a porcentagem`, `qual foi o ultimo`
- recorte: `ultimo dia`, `ultima semana`, `ultimo mes`, `ultimos 90 dias`, `ate hoje`
- dimensão: `workflow`, `job`, `repositorio`, `time`, `arquitetura`, `analista`
- filtro de negócio: `PRD`, `HML`, `DEV`, `api`, `srv`, `bff`, `apim`, `java`, `node`, `deploy`, `build`

Exemplos:
- `python3 agent/main.py --question "Qual foi o ultimo workflow que falhou em produção?"`
- `python3 agent/main.py --question "Liste os repositorios que falharam na ultima semana"`
- `python3 agent/main.py --question "Quais workflows da arquitetura de api mais falharam nos ultimos 90 dias?"`
- `python3 agent/main.py --question "Qual a porcentagem de falha e sucesso em deploys do time de ia?"`
- `python3 agent/main.py --question "Quais os ultimos deploys das esteiras de apim?"`
- `python3 agent/main.py --question "Quanto tempo leva a execucao media de esteiras de rollback?"`
- `python3 agent/main.py --question "Qual foi o tempo entre a abertura do chamado do repositorio nada/arch-api-cash-cambio-contatos-ext e a primeira entrega em PRD?"`
- `python3 agent/main.py --question "Qual foi o tempo entre a solicitacao de habilitacao da esteira do repositorio nada/devops-bff-pix-web e a primeira entrega em HML?"`
- `python3 agent/main.py --question "Qual e a frequencia de deploy da arquitetura api?"`
- `python3 agent/main.py --question "Quanto tempo leva em media entre o primeiro deploy em DEV e o primeiro deploy em PRD?"`
- `python3 agent/main.py --question "Em media quantos deploys em DEV ocorrem para o deploy em PRD?"`
- `python3 agent/main.py --question "Quais o email dos analistas incluidos nos deploys da arquitetura api?"`
- `python3 agent/main.py --question "Qual o email do analista que engatilhou o ultimo deploy em PRD da esteira Deploy Staging?"`
- `python3 agent/main.py --question "Quais os analistas que estao trabalhando na esteira Deploy Staging?"`

### Prompts gerenciais

Use o relatório executivo quando quiser consolidar vários indicadores em um HTML:

- `python3 scripts/generate_director_report.py --prompt "Quero uma visão executiva semanal de risco operacional em PRD" --time-range 7d --include overview,risk,prd,approvals`
- `python3 scripts/generate_director_report.py --prompt "Qual seria o relatorio gerencial para as arquiteturas api e srv nos ultimos 7 dias?" --time-range 7d --include overview,risk,success,lead_time,api,srv`
- `python3 scripts/generate_director_report.py --prompt "Quero um resumo executivo de CI/CD com foco em risco operacional, sucesso em PRD, lead time e aprovacoes pendentes" --time-range 30d --include overview,risk,success,lead_time,approvals,prd`

### Operacao em container

CLI:

```bash
docker run --rm -it --env-file deploy/env/production.env.example <imagem-agent>
```

API HTTP:

```bash
docker run --rm -p 8787:8787 \
  --env-file deploy/env/production.env.example \
  <imagem-agent> \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

### Build e push automatizados no GitHub

O workflow [build-agent-image.yml](/home/bruno/lab_ia/elk-mcp-agent/.github/workflows/build-agent-image.yml) faz o build da imagem do agente com MCP embutido e publica no GHCR.

Comportamento:
- `pull_request`: faz apenas build de validação
- `push` em `main` e `develop`: faz build e push
- `push` de tag `v*`: faz build e push
- `workflow_dispatch`: execução manual

A mesma imagem pode ser usada nos dois modos:
- CLI: `python3 agent/main.py` como comando padrão
- serviço HTTP: sobrescrevendo o comando para `agent/http_service.py`

Exemplos com GHCR:

```bash
docker run --rm -it ghcr.io/<owner>/elk-mcp-agent-agent:develop
```

```bash
docker run --rm -p 8787:8787 \
  ghcr.io/<owner>/elk-mcp-agent-agent:develop \
  agent/http_service.py --host 0.0.0.0 --port 8787
```

## 🔍 Troubleshooting

### Autenticação no Elasticsearch

```bash
# Carregar credenciais do .env
source .env

# Testar conectividade
curl -s -u elastic:${ELASTIC_PASSWORD} http://localhost:9200/_cluster/health | python3 -m json.tool

# Listar índices
curl -s -u elastic:${ELASTIC_PASSWORD} http://localhost:9200/_cat/indices?v
```

### Verificar mapeamento do índice

```bash
source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  "http://localhost:9200/github-pipeline-executions/_mapping" \
  | python3 -m json.tool | grep -A3 '"jobs"'
```

### Contar documentos

```bash
source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  "http://localhost:9200/github-pipeline-executions/_count" \
  | python3 -m json.tool
```

### Explorar valores de um campo

```bash
source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  -X POST "http://localhost:9200/github-pipeline-executions/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "job_names": {
  "terms": {"field": "jobs.name.keyword", "size": 20}
      }
    }
  }' | python3 -m json.tool
```

### Contar tipos distintos de jobs (cardinality)

```bash
source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  -X POST "http://localhost:9200/github-pipeline-executions/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "tipos_de_jobs": {
  "cardinality": {"field": "jobs.name.keyword"}
      }
    }
  }' | python3 -m json.tool
```

### ❌ Armadilha: nested query em índice flat

Os campos `jobs.*` não são nested no mapping real. A query abaixo retorna `doc_count: 0`:

```bash
# ❌ ERRADO — jobs não é nested neste índice
curl ... -d '{
  "aggs": {
    "job_types": {
      "nested": {"path": "jobs"},
      "aggs": {...}
    }
  }
}'

# ✅ CORRETO — query flat direto no campo
curl ... -d '{
  "aggs": {
    "job_names": {
      "terms": {"field": "jobs.name.keyword", "size": 20}
    }
  }
}'
```

### Verificar e filtrar campos no config

```bash
# Ver nested_paths configurado (deve estar vazio ou ausente)
grep -A3 "nested_paths" config.yaml

# Remover nested_paths se existir
python3 - << 'PYEOF'
with open('config.yaml', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if 'nested_paths:' in line:
  skip = True
  continue
    if skip and line.strip().startswith('- '):
  continue
    skip = False
    new_lines.append(line)

with open('config.yaml', 'w') as f:
    f.writelines(new_lines)

print("nested_paths removido")
PYEOF
```

### Corrigir autenticação no `elastic_client.py`

O cliente original usa `api_key` fixo. Versão corrigida que suporta `basic_auth` com `username/password`:

```python
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
```

### Verificar modelos disponíveis no Ollama

```bash
ollama list

# Testar resposta do modelo
curl -s http://localhost:11434/api/generate \
  -d '{"model": "qwen2.5:3b", "prompt": "responda só: ok", "stream": false}' \
  | python3 -m json.tool | grep response
```

### Verificar se o MCP server inicia corretamente

```bash
cd mcp_server
python3 main.py
# Ctrl+C para sair — se não der erro de import, está ok
```

## 📁 Estrutura do projeto

```plaintext
elk-mcp-agent/
├── agent/
│   ├── main.py           # CLI principal
│   ├── prompts.py        # System prompt dinâmico
│   └── session.py        # Gerenciamento de contexto
├── mcp_server/
│   ├── main.py           # Servidor MCP (stdio)
│   ├── elastic_client.py # Wrapper do cliente Elasticsearch
│   ├── config_loader.py  # Leitura do config.yaml
│   └── tools/
│       ├── __init__.py
│       ├── aggregate.py
│       ├── discover_schema.py
│       ├── explore_field.py
│       └── searcher.py
├── config.yaml           # Configuração central
├── docker-compose.yml    # ELK Stack
├── .env                  # Credenciais (não versionar)
└── README.md
```

## 🧠 Notas sobre o modelo LLM

O `qwen2.5:3b` é um modelo pequeno e pode cometer erros de raciocínio ao escolher a tool correta ou formatar parâmetros. Comportamentos conhecidos:

- Usar `time_range='LAST_30_DAYS'` em vez do formato correto `'30d'`
- Chamar `nested_filter` mesmo com campos flat
- Simular chamadas de tool em vez de executá-las de verdade

Para melhor qualidade de respostas, prefira modelos maiores como `qwen2.5:7b` ou `mistral:7b` se houver recursos disponíveis.

```bash
ollama pull qwen2.5:7b
# Alterar model em config.yaml
```
🤖 elk-mcp-agent

Agente de inteligência artificial local para análise de pipelines CI/CD. Combina Elasticsearch, Ollama (LLM local) e um servidor MCP (Model Context Protocol) para permitir consultas em linguagem natural sobre execuções de workflows do GitHub Actions.

🎯 Objetivo

Responder perguntas como "quais repositórios tiveram mais falhas esta semana?" sem que o usuário precise escrever queries Elasticsearch manualmente.

🏗️ Arquitetura

Usuário (linguagem natural)
        ↓
   agent/main.py          ← CLI interativa
        ↓
   Ollama (LLM local)     ← qwen2.5:3b ou mistral
        ↓
   MCP Server (stdio)     ← mcp_server/main.py
        ↓
   Elasticsearch 8.x      ← índice github-pipeline-executions
Componentes


agent/ — CLI, session management, system prompt dinâmico
mcp_server/ — servidor MCP com 4 tools: discover_schema, explore_field, aggregate, search
mcp_server/tools/ — implementação das tools: aggregate.py, searcher.py, explore_field.py, discover_schema.py
config.yaml — configuração central: conexão ES, domínio de negócio, vocabulário, thresholds
docker-compose.yml — Elasticsearch 8.13 + Kibana


⚙️ Pré-requisitos


Docker + Docker Compose
Python 3.11+
Ollama com modelo baixado (qwen2.5:3b ou mistral)
Instalar dependências Python

pip install -r mcp_server/requirements.txt
Subir o stack ELK

docker compose up -d elasticsearch

# Acompanhar startup (~1 min)
docker logs -f elk_elasticsearch 2>&1 | grep -E "started|error|warn"

# Subir Kibana (opcional)
docker compose up -d kibana
docker logs -f elk_kibana 2>&1 | grep -E "ready|error|warn"


🔧 Configuração

.env

ELASTIC_PASSWORD=changeme123
KIBANA_SYSTEM_PASSWORD=changeme456
config.yaml — seção Elasticsearch

elasticsearch:
  url:        "http://localhost:9200"
  username:   "elastic"
  password:   "changeme123"
  verify_ssl: false
  timeout:    30
  index:      "github-pipeline-executions"
  time_field: "workflow_run.started_at"
  default_time_range: "7d"

  ⚠️ Importante: O índice github-pipeline-executions usa campos jobs.* como objetos planos (não nested). Não configure nested_paths no config — isso fará as queries retornarem doc_count: 0.


🚀 Rodar o agente

python3 agent/main.py


💬 Perguntas de exemplo

Use estas perguntas diretamente na CLI do agente para interagir com os dados do Elasticsearch:quantos tipos de jobs diferentes rodaram nos últimos 30 dias?
qual a taxa de falha por repositório nos últimos 90 dias?
quais os jobs com maior duração média?
quanto tempo em média leva o deploy-prod?
quais repositórios tiveram mais falhas na última semana?


🔍 Troubleshooting

Autenticação no Elasticsearch

# Carregar credenciais do .env
source .env

# Testar conectividade
curl -s -u elastic:${ELASTIC_PASSWORD} http://localhost:9200/_cluster/health | python3 -m json.tool

# Listar índices
curl -s -u elastic:${ELASTIC_PASSWORD} http://localhost:9200/_cat/indices?v
Verificar mapeamento do índice

source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  "http://localhost:9200/github-pipeline-executions/_mapping" \
  | python3 -m json.tool | grep -A3 '"jobs"'
Contar documentos

source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  "http://localhost:9200/github-pipeline-executions/_count" \
  | python3 -m json.tool
Explorar valores de um campo

source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  -X POST "http://localhost:9200/github-pipeline-executions/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "job_names": {
        "terms": {"field": "jobs.name.keyword", "size": 20}
      }
    }
  }' | python3 -m json.tool
Contar tipos distintos de jobs (cardinality)

source .env

curl -s -u elastic:${ELASTIC_PASSWORD} \
  -X POST "http://localhost:9200/github-pipeline-executions/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "tipos_de_jobs": {
        "cardinality": {"field": "jobs.name.keyword"}
      }
    }
  }' | python3 -m json.tool
❌ Armadilha: nested query em índice flat

Os campos jobs.* não são nested no mapping real. A query abaixo retorna doc_count: 0:# ❌ ERRADO — jobs não é nested neste índice
curl ... -d '{
  "aggs": {
    "job_types": {
      "nested": {"path": "jobs"},
      "aggs": {...}
    }
  }
}'

# ✅ CORRETO — query flat direto no campo
curl ... -d '{
  "aggs": {
    "job_names": {
      "terms": {"field": "jobs.name.keyword", "size": 20}
    }
  }
}'
Verificar e filtrar campos no config

# Ver nested_paths configurado (deve estar vazio ou ausente)
grep -A3 "nested_paths" config.yaml

# Remover nested_paths se existir
python3 - << 'PYEOF'
with open('config.yaml', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if 'nested_paths:' in line:
        skip = True
        continue
    if skip and line.strip().startswith('- '):
        continue
    skip = False
    new_lines.append(line)

with open('config.yaml', 'w') as f:
    f.writelines(new_lines)

print("nested_paths removido")
PYEOF
Corrigir autenticação no elastic_client.py

O cliente original usa api_key fixo. Versão corrigida que suporta basic_auth com username/password:def get_client(config: dict | None = None) -> Elasticsearch:
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
Verificar modelos disponíveis no Ollama

ollama list

# Testar resposta do modelo
curl -s http://localhost:11434/api/generate \
  -d '{"model": "qwen2.5:3b", "prompt": "responda só: ok", "stream": false}' \
  | python3 -m json.tool | grep response
Verificar se o MCP server inicia corretamente

cd mcp_server
python3 main.py
# Ctrl+C para sair — se não der erro de import, está ok


📁 Estrutura do projeto

elk-mcp-agent/
├── agent/
│   ├── main.py           # CLI principal
│   ├── prompts.py        # System prompt dinâmico
│   └── session.py        # Gerenciamento de contexto
├── mcp_server/
│   ├── main.py           # Servidor MCP (stdio)
│   ├── elastic_client.py # Wrapper do cliente Elasticsearch
│   ├── config_loader.py  # Leitura do config.yaml
│   └── tools/
│       ├── __init__.py
│       ├── aggregate.py
│       ├── discover_schema.py
│       ├── explore_field.py
│       └── searcher.py
├── config.yaml           # Configuração central
├── docker-compose.yml    # ELK Stack
├── .env                  # Credenciais (não versionar)
└── README.md


🧠 Notas sobre o modelo LLM

O qwen2.5:3b é um modelo pequeno e pode cometer erros de raciocínio ao escolher a tool correta ou formatar parâmetros. Comportamentos conhecidos:
Usar time_range='LAST_30_DAYS' em vez do formato correto '30d'
Chamar nested_filter mesmo com campos flat
Simular chamadas de tool em vez de executá-las de verdade
Para melhor qualidade de respostas, prefira modelos maiores como qwen2.5:7b ou mistral:7b se houver recursos disponíveis.ollama pull qwen2.5:7b
# Alterar model em config.yaml


## Para a stack subir, rodar:

# Permite masquerading (essencial para rede docker)
sudo firewall-cmd --permanent --zone=public --add-masquerade

# Adiciona a interface do docker à zona de confiança
sudo firewall-cmd --permanent --zone=trusted --add-interface=docker0

# Se o Docker criou uma interface específica para a rede elk-net (ex: br-xxxx), adicione-a também:
# Você descobre o nome com: ip link show
# sudo firewall-cmd --permanent --zone=trusted --add-interface=br-NOME_DA_REDE

# Recarrega o firewall
sudo firewall-cmd --reload

# Reinicie o serviço do docker para garantir
sudo systemctl restart docker

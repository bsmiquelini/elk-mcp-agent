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

## 💬 Perguntas de exemplo

Use estas perguntas diretamente na CLI do agente para interagir com os dados do Elasticsearch:

- Quantos tipos de jobs diferentes rodaram nos últimos 30 dias?
- Qual a taxa de falha por repositório nos últimos 90 dias?
- Quais os jobs com maior duração média?
- Quanto tempo em média leva o deploy-prod?
- Quais repositórios tiveram mais falhas na última semana?

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


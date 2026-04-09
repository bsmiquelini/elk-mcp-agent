#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

echo ""
echo "🚀 ELK MCP Agent — Setup"
echo "══════════════════════════════════════"

COMPOSE=$(detect_compose)
info "Docker Compose detectado: $COMPOSE"

# ── Pré-requisitos ───────────────────────────────────────────
command -v docker  >/dev/null 2>&1 || fail "Docker não encontrado"
command -v mkcert  >/dev/null 2>&1 || fail "mkcert não encontrado. Execute: make deps"
command -v python3 >/dev/null 2>&1 || fail "Python3 não encontrado"

# ── .env ─────────────────────────────────────────────────────
load_env_file
OLLAMA_API_BASE=${OLLAMA_API_BASE:-http://127.0.0.1:11434}

# ── Certificados TLS ─────────────────────────────────────────
log "Gerando certificados TLS com mkcert..."
mkdir -p infra/nginx/certs
mkcert -install 2>/dev/null || true
mkcert \
  -cert-file infra/nginx/certs/cert.pem \
  -key-file  infra/nginx/certs/key.pem \
  localhost 127.0.0.1 ::1
log "Certificados gerados em infra/nginx/certs/"

# ── Subir stack ──────────────────────────────────────────────
log "Subindo containers Docker..."
$COMPOSE up -d
log "Containers iniciados"

# ── Aguardar Elasticsearch ───────────────────────────────────
log "Aguardando Elasticsearch ficar saudável..."
attempt=0
max_attempts=40
until curl -s -u "elastic:${ELASTIC_PASSWORD}" \
  http://localhost:9200/_cluster/health 2>/dev/null \
  | grep -q '"status":"green"\|"status":"yellow"'; do
  attempt=$((attempt + 1))
  [ $attempt -ge $max_attempts ] && fail "Elasticsearch não respondeu após ${max_attempts} tentativas"
  info "Tentativa ${attempt}/${max_attempts} — aguardando..."
  sleep 6
done
log "Elasticsearch está saudável"

# ── Configurar senha do kibana_system ────────────────────────
log "Configurando usuário kibana_system..."
RESP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -u "elastic:${ELASTIC_PASSWORD}" \
  -H "Content-Type: application/json" \
  http://localhost:9200/_security/user/kibana_system/_password \
  -d "{\"password\":\"${KIBANA_SYSTEM_PASSWORD}\"}")

if [ "$RESP" = "200" ]; then
  log "Usuário kibana_system configurado"
else
  warn "Resposta inesperada ao configurar kibana_system: HTTP $RESP (pode já estar configurado)"
fi

# ── Criar API Key ─────────────────────────────────────────────
log "Criando API Key para o MCP Server..."
API_KEY_RESPONSE=$(curl -s -X POST \
  -u "elastic:${ELASTIC_PASSWORD}" \
  -H "Content-Type: application/json" \
  http://localhost:9200/_security/api_key \
  -d '{
    "name": "mcp-server-key",
    "role_descriptors": {
      "mcp_role": {
        "cluster": ["monitor"],
        "indices": [{
          "names": ["github-workflows", "github-workflows-*"],
          "privileges": ["read", "view_index_metadata", "create_index", "write"]
        }]
      }
    }
  }')

API_KEY=$(echo "$API_KEY_RESPONSE" | python3 -c "
import sys, json, base64
try:
    r = json.load(sys.stdin)
    encoded = base64.b64encode(f\"{r['id']}:{r['api_key']}\".encode()).decode()
    print(encoded)
except Exception as e:
    print('ERRO: ' + str(e), file=sys.stderr)
    sys.exit(1)
")

# Salvar no .env (compatível com macOS e Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' "s|ELASTICSEARCH_API_KEY=.*|ELASTICSEARCH_API_KEY=${API_KEY}|" .env
else
  sed -i "s|ELASTICSEARCH_API_KEY=.*|ELASTICSEARCH_API_KEY=${API_KEY}|" .env
fi
log "API Key criada e salva no .env"

# ── Criar template de índice ──────────────────────────────────
log "Criando template github-workflows..."
INDEX_RESP=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
  -u "elastic:${ELASTIC_PASSWORD}" \
  -H "Content-Type: application/json" \
  http://localhost:9200/_index_template/github-workflows-template \
  -d '{
    "index_patterns": ["github-workflows-*"],
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
      },
      "mappings": {
        "dynamic_date_formats": [
          "strict_date_optional_time"
        ],
        "dynamic_templates": [
          {
            "strings_as_text_and_keyword": {
              "match_mapping_type": "string",
              "mapping": {
                "type": "text",
                "fields": {
                  "keyword": {
                    "type": "keyword",
                    "ignore_above": 256
                  }
                }
              }
            }
          }
        ]
      }
    }
  }')

if [ "$INDEX_RESP" = "200" ]; then
  log "Template criado com sucesso"
else
  warn "Resposta inesperada ao criar template: HTTP $INDEX_RESP"
fi

# ── Aguardar Kibana ───────────────────────────────────────────
log "Aguardando Kibana ficar disponível (pode demorar ~60s)..."
attempt=0
max_attempts=20
until curl -s http://localhost:5601/api/status 2>/dev/null \
  | grep -q '"level":"available"'; do
  attempt=$((attempt + 1))
  [ $attempt -ge $max_attempts ] && warn "Kibana ainda não respondeu — continue com o seed normalmente" && break
  info "Tentativa ${attempt}/${max_attempts} — aguardando Kibana..."
  sleep 8
done
[ $attempt -lt $max_attempts ] && log "Kibana disponível"

# ── Seed de dados ─────────────────────────────────────────────
log "Instalando dependências do seed..."
pip3 install -q -r scripts/requirements-seed.txt

log "Populando Elasticsearch com dados simulados..."
python3 scripts/seed_data.py

# ── Validar e configurar Ollama ───────────────────────────────
log "Verificando Ollama..."

OLLAMA_MODEL=$(python3 - <<'PY'
import yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
agent = cfg.get("agent", {})
print(agent.get("ollama_model") or agent.get("model") or "qwen2.5:7b")
PY
)
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5:7b}

# Aguarda Ollama responder (pode demorar no primeiro start)
attempt=0
max_attempts=15
until curl -s "${OLLAMA_API_BASE}/api/tags" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  [ $attempt -ge $max_attempts ] && fail "Ollama não respondeu após ${max_attempts} tentativas. Verifique o container."
  info "Tentativa ${attempt}/${max_attempts} — aguardando Ollama..."
  sleep 4
done
log "Ollama disponível"

# Verifica se o modelo já está baixado
MODEL_EXISTS=$(curl -s "${OLLAMA_API_BASE}/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('models', [])
full_names = [m['name'] for m in models]
base_names = [m['name'].split(':')[0] for m in models]
target = '${OLLAMA_MODEL}'
target_base = target.split(':')[0]
print('yes' if target in full_names or target_base in base_names else 'no')
" 2>/dev/null)

if [ "$MODEL_EXISTS" = "yes" ]; then
  log "Modelo '${OLLAMA_MODEL}' já disponível no Ollama"
else
  warn "Modelo '${OLLAMA_MODEL}' não encontrado. Baixando agora (pode demorar)..."
  docker exec elk_ollama ollama pull "${OLLAMA_MODEL}"
  log "Modelo '${OLLAMA_MODEL}' baixado com sucesso"
fi

echo ""
echo "══════════════════════════════════════════════"
echo -e "${GREEN}🎉 Setup concluído com sucesso!${NC}"
echo ""
echo "  📊 Kibana:         https://localhost"
echo "  🔍 Elasticsearch:  https://localhost:9243"
echo "  🤖 Ollama:         ${OLLAMA_API_BASE}"
echo ""
echo "  👤 Login Kibana:   elastic / ${ELASTIC_PASSWORD}"
echo ""
echo "  Próximo passo:     make run-agent"
echo "══════════════════════════════════════════════"

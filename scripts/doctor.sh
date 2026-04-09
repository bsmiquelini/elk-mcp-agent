#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

echo ""
echo "🩺 ELK MCP Agent — Doctor"
echo "══════════════════════════════════════"

command -v docker >/dev/null 2>&1 || fail "Docker não encontrado"
command -v python3 >/dev/null 2>&1 || fail "Python3 não encontrado"
command -v curl >/dev/null 2>&1 || fail "curl não encontrado"

COMPOSE=$(detect_compose)
info "Docker Compose detectado: $COMPOSE"

load_env_file
OLLAMA_API_BASE=${OLLAMA_API_BASE:-http://127.0.0.1:11434}

if command -v mkcert >/dev/null 2>&1; then
  log "mkcert disponível"
else
  warn "mkcert não encontrado. O proxy TLS local não poderá ser regenerado automaticamente."
fi

if $COMPOSE ps >/dev/null 2>&1; then
  log "Stack Docker acessível"
else
  warn "Não foi possível consultar o estado do compose"
fi

if curl -s -u "elastic:${ELASTIC_PASSWORD}" http://localhost:9200/_cluster/health >/dev/null 2>&1; then
  CLUSTER=$(curl -s -u "elastic:${ELASTIC_PASSWORD}" http://localhost:9200/_cluster/health | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))")
  log "Elasticsearch acessível (${CLUSTER})"
else
  warn "Elasticsearch indisponível em http://localhost:9200"
fi

if curl -s "${OLLAMA_API_BASE}/api/tags" >/dev/null 2>&1; then
  MODEL_COUNT=$(curl -s "${OLLAMA_API_BASE}/api/tags" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('models', [])))")
  log "Ollama acessível (${MODEL_COUNT} modelos visíveis)"
else
  warn "Ollama indisponível em ${OLLAMA_API_BASE}"
fi

INDEX_COUNT="0"
if curl -s -u "elastic:${ELASTIC_PASSWORD}" "http://localhost:9200/_cat/indices/github-workflows*?format=json" >/dev/null 2>&1; then
  INDEX_COUNT=$(curl -s -u "elastic:${ELASTIC_PASSWORD}" "http://localhost:9200/_cat/indices/github-workflows*?format=json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data))")
fi
info "Índices github-workflows*: ${INDEX_COUNT}"

echo ""
echo "Sugestões rápidas:"
echo "  make setup        # bootstrap local"
echo "  make smoke-test   # regressão local"
echo "  make smoke-test-docker   # regressão via container"
echo "══════════════════════════════════════"

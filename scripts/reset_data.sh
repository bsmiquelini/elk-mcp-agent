#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"

echo ""
echo "♻️  ELK MCP Agent — Reset de Dados"
echo "══════════════════════════════════════"

command -v curl >/dev/null 2>&1 || fail "curl não encontrado"
command -v python3 >/dev/null 2>&1 || fail "Python3 não encontrado"

load_env_file

info "Removendo índices github-workflows*..."
INDICES=$(curl -s \
  -u "elastic:${ELASTIC_PASSWORD}" \
  "http://localhost:9200/_cat/indices/github-workflows*?h=index" | tr '\n' ',' | sed 's/,$//')

if [ -z "$INDICES" ]; then
  log "Nenhum índice github-workflows* encontrado"
else
  HTTP_CODE=$(curl -s -o /tmp/reset_data_response.txt -w "%{http_code}" \
    -u "elastic:${ELASTIC_PASSWORD}" \
    -X DELETE "http://localhost:9200/${INDICES}")

  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
    log "Índices removidos com sucesso"
  else
    cat /tmp/reset_data_response.txt
    fail "Falha ao remover índices github-workflows* (HTTP ${HTTP_CODE})"
  fi
fi

rm -f /tmp/reset_data_response.txt

info "Recriando dados simulados..."
pip3 install -q -r scripts/requirements-seed.txt
python3 scripts/seed_data.py

log "Seed recriado com sucesso"
echo "══════════════════════════════════════"

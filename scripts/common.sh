#!/bin/bash

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
info() { echo -e "${BLUE}ℹ  $1${NC}"; }

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif docker-compose version >/dev/null 2>&1; then
    echo "docker-compose"
  else
    fail "Docker Compose não encontrado. Instale o plugin ou o docker-compose standalone."
  fi
}

ensure_env_file() {
  if [ ! -f .env ]; then
    cp .env.example .env
    warn ".env criado a partir do .env.example. Revise as senhas se necessário."
  fi
}

load_env_file() {
  ensure_env_file
  set -a
  source .env
  set +a
}

wait_for_url() {
  local url="$1"
  local pattern="$2"
  local attempts="$3"
  local sleep_seconds="$4"
  local curl_args="${5:-}"
  local attempt=0

  until eval "curl -s ${curl_args} ${url}" 2>/dev/null | grep -q "$pattern"; do
    attempt=$((attempt + 1))
    [ "$attempt" -ge "$attempts" ] && return 1
    info "Tentativa ${attempt}/${attempts} — aguardando ${url}..."
    sleep "${sleep_seconds}"
  done
}

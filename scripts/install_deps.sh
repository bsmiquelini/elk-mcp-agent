#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
info() { echo -e "${BLUE}ℹ  $1${NC}"; }

echo ""
echo "📦 ELK MCP Agent — Instalação de Dependências"
echo "══════════════════════════════════════════════"

# ── Detecta distro ────────────────────────────────────────────
detect_distro() {
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "$ID"
  else
    echo "unknown"
  fi
}

DISTRO=$(detect_distro)
info "Sistema detectado: $DISTRO"

# ── Define gerenciador de pacotes ─────────────────────────────
case "$DISTRO" in
  ubuntu|debian|linuxmint|pop)
    PKG_UPDATE="sudo apt-get update -qq"
    PKG_INSTALL="sudo apt-get install -y -qq"
    ;;
  fedora|nobara)
    PKG_UPDATE="sudo dnf check-update -q || true"
    PKG_INSTALL="sudo dnf install -y -q"
    ;;
  rhel|centos|rocky|almalinux)
    PKG_UPDATE="sudo yum check-update -q || true"
    PKG_INSTALL="sudo yum install -y -q"
    ;;
  arch|manjaro)
    PKG_UPDATE="sudo pacman -Sy --noconfirm"
    PKG_INSTALL="sudo pacman -S --noconfirm"
    ;;
  *)
    warn "Distro '$DISTRO' não mapeada explicitamente. Tentando com dnf/apt..."
    if command -v dnf >/dev/null 2>&1; then
      PKG_UPDATE="sudo dnf check-update -q || true"
      PKG_INSTALL="sudo dnf install -y -q"
    elif command -v apt-get >/dev/null 2>&1; then
      PKG_UPDATE="sudo apt-get update -qq"
      PKG_INSTALL="sudo apt-get install -y -qq"
    else
      fail "Nenhum gerenciador de pacotes suportado encontrado."
    fi
    ;;
esac

# ── Atualiza repositórios ─────────────────────────────────────
info "Atualizando repositórios..."
$PKG_UPDATE 2>/dev/null || true

# ── curl ──────────────────────────────────────────────────────
if command -v curl >/dev/null 2>&1; then
  log "curl já instalado"
else
  info "Instalando curl..."
  $PKG_INSTALL curl
  log "curl instalado"
fi

# ── make ──────────────────────────────────────────────────────
if command -v make >/dev/null 2>&1; then
  log "make já instalado"
else
  info "Instalando make..."
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop) $PKG_INSTALL build-essential ;;
    fedora|nobara|rhel|centos|rocky|almalinux) $PKG_INSTALL make ;;
    arch|manjaro) $PKG_INSTALL base-devel ;;
    *) $PKG_INSTALL make ;;
  esac
  log "make instalado"
fi

# ── Docker ────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  log "Docker já instalado: $(docker --version)"
else
  info "Instalando Docker via script oficial..."
  curl -fsSL https://get.docker.com | bash
  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
  warn "Usuário adicionado ao grupo docker. Faça logout/login para aplicar."
  log "Docker instalado: $(docker --version)"
fi

# ── Docker Compose ────────────────────────────────────────────
install_docker_compose() {
  if docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin já disponível: $(docker compose version)"
    return
  fi

  if docker-compose version >/dev/null 2>&1; then
    log "docker-compose standalone já disponível: $(docker-compose version)"
    return
  fi

  info "Instalando Docker Compose plugin..."
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop)
      sudo apt-get install -y docker-compose-plugin
      ;;
    fedora|nobara)
      sudo dnf install -y docker-compose-plugin 2>/dev/null || \
      sudo dnf install -y docker-compose 2>/dev/null || {
        info "Instalando Docker Compose via binário oficial..."
        COMPOSE_VERSION="2.27.0"
        sudo curl -SL \
          "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
          -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
      }
      ;;
    centos|rhel|rocky|alma)
      sudo yum install -y docker-compose-plugin 2>/dev/null || {
        COMPOSE_VERSION="2.27.0"
        sudo curl -SL \
          "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
          -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
      }
      ;;
    arch|manjaro)
      sudo pacman -Sy --noconfirm docker-compose
      ;;
    *)
      COMPOSE_VERSION="2.27.0"
      sudo curl -SL \
        "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
        -o /usr/local/bin/docker-compose
      sudo chmod +x /usr/local/bin/docker-compose
      ;;
  esac

  if docker compose version >/dev/null 2>&1 || docker-compose version >/dev/null 2>&1; then
    log "Docker Compose instalado com sucesso"
  else
    fail "Falha ao instalar Docker Compose"
  fi
}

install_docker_compose

# ── Python3 ───────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  log "Python3 já instalado: $(python3 --version)"
else
  info "Instalando Python3..."
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop) $PKG_INSTALL python3 python3-pip python3-venv ;;
    fedora|nobara|rhel|centos|rocky|almalinux) $PKG_INSTALL python3 python3-pip ;;
    arch|manjaro) $PKG_INSTALL python python-pip ;;
    *) $PKG_INSTALL python3 ;;
  esac
  log "Python3 instalado: $(python3 --version)"
fi

# ── pip3 ──────────────────────────────────────────────────────
if command -v pip3 >/dev/null 2>&1; then
  log "pip3 disponível: $(pip3 --version)"
else
  info "Instalando pip3..."
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop) $PKG_INSTALL python3-pip ;;
    fedora|nobara|rhel|centos|rocky|almalinux) $PKG_INSTALL python3-pip ;;
    *) curl -sS https://bootstrap.pypa.io/get-pip.py | python3 ;;
  esac
  log "pip3 instalado"
fi

# ── mkcert ────────────────────────────────────────────────────
if command -v mkcert >/dev/null 2>&1; then
  log "mkcert já instalado: $(mkcert --version)"
else
  info "Instalando mkcert via binário oficial..."

  MKCERT_VERSION="1.4.4"
  ARCH=$(uname -m)
  case "$ARCH" in
    x86_64)  MKCERT_ARCH="amd64" ;;
    aarch64) MKCERT_ARCH="arm64" ;;
    armv7l)  MKCERT_ARCH="arm" ;;
    *)       fail "Arquitetura $ARCH não suportada pelo mkcert" ;;
  esac

  # Instala dependências do nss (para Firefox/Chrome reconhecerem o cert)
  info "Instalando nss-tools..."
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop)
      $PKG_INSTALL libnss3-tools 2>/dev/null || true
      ;;
    fedora|nobara|rhel|centos|rocky|almalinux)
      $PKG_INSTALL nss-tools 2>/dev/null || true
      ;;
    arch|manjaro)
      $PKG_INSTALL nss 2>/dev/null || true
      ;;
  esac

  MKCERT_URL="https://github.com/FiloSottile/mkcert/releases/download/v${MKCERT_VERSION}/mkcert-v${MKCERT_VERSION}-linux-${MKCERT_ARCH}"
  info "Baixando mkcert v${MKCERT_VERSION} para ${MKCERT_ARCH}..."
  curl -fsSL "$MKCERT_URL" -o /tmp/mkcert
  sudo install /tmp/mkcert /usr/local/bin/mkcert
  rm /tmp/mkcert

  if command -v mkcert >/dev/null 2>&1; then
    mkcert -install 2>/dev/null || warn "CA local não instalada (não crítico para o MVP)"
    log "mkcert instalado: $(mkcert --version)"
  else
    fail "Falha ao instalar mkcert"
  fi
fi

echo ""
echo "══════════════════════════════════════════════"
echo -e "${GREEN}🎉 Todas as dependências instaladas com sucesso!${NC}"
echo ""
echo "  Versões instaladas:"
echo "    Docker:          $(docker --version)"
echo "    Docker Compose:  $(docker compose version 2>/dev/null || docker-compose --version)"
echo "    Python3:         $(python3 --version)"
echo "    mkcert:          $(mkcert --version)"
echo ""
echo "  Próximo passo: make setup"
echo "══════════════════════════════════════════════"

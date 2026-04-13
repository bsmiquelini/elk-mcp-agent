#!/bin/sh
set -eu

ollama serve &
pid="$!"

cleanup() {
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

i=0
until curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; do
  i=$((i+1))
  if [ "$i" -ge 120 ]; then
    echo "Ollama não ficou pronto no startup" >&2
    exit 1
  fi
  sleep 1
done

# Garante que o modelo exista localmente.
# Em teoria já veio da imagem, mas isso protege contra corrupção ou troca de tag.
if ! ollama list | awk '{print $1}' | grep -Fxq "$OLLAMA_PRELOAD_MODEL"; then
  ollama pull "$OLLAMA_PRELOAD_MODEL"
fi

# Aquece o modelo em memória.
curl -fsS http://127.0.0.1:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${OLLAMA_PRELOAD_MODEL}\",\"prompt\":\"\",\"stream\":false,\"keep_alive\":\"${OLLAMA_KEEP_ALIVE}\"}" \
  >/dev/null || true

wait "$pid"

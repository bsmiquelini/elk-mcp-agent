#!/bin/sh
set -eu

cleanup() {
  if [ -n "${OLLAMA_PID:-}" ]; then
    kill "${OLLAMA_PID}" >/dev/null 2>&1 || true
    wait "${OLLAMA_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup INT TERM EXIT

echo "[ollama-entrypoint] starting ollama server on ${OLLAMA_HOST:-0.0.0.0}:11434"
ollama serve &
OLLAMA_PID="$!"

for attempt in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [ -n "${OLLAMA_PRELOAD_MODEL:-}" ]; then
  if ! ollama list | awk 'NR>1 {print $1}' | grep -Fx "${OLLAMA_PRELOAD_MODEL}" >/dev/null 2>&1; then
    echo "[ollama-entrypoint] preloading model ${OLLAMA_PRELOAD_MODEL}"
    ollama pull "${OLLAMA_PRELOAD_MODEL}"
  else
    echo "[ollama-entrypoint] model ${OLLAMA_PRELOAD_MODEL} already present"
  fi
fi

wait "${OLLAMA_PID}"

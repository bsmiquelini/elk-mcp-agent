# syntax=docker/dockerfile:1.7

############################
# Stage 1: baixa o modelo #
############################
FROM ollama/ollama:latest AS model-fetch

ARG OLLAMA_PRELOAD_MODEL=qwen2.5:7b

ENV OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_MODELS=/root/.ollama/models

SHELL ["/bin/sh", "-ceu"]

RUN mkdir -p /root/.ollama/models && \
    ollama serve >/tmp/ollama-build.log 2>&1 & \
    pid="$!" && \
    i=0 && \
    until curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; do \
      i=$((i+1)); \
      [ "$i" -ge 120 ] && echo "Ollama não subiu no build" && cat /tmp/ollama-build.log && exit 1; \
      sleep 1; \
    done && \
    ollama pull "${OLLAMA_PRELOAD_MODEL}" && \
    curl -fsS http://127.0.0.1:11434/api/generate \
      -H 'Content-Type: application/json' \
      -d "{\"model\":\"${OLLAMA_PRELOAD_MODEL}\",\"prompt\":\"\",\"stream\":false}" >/dev/null && \
    kill "$pid" && \
    wait "$pid" || true

############################
# Stage 2: imagem final    #
############################
FROM ollama/ollama:latest

ARG OLLAMA_PRELOAD_MODEL=qwen2.5:7b

ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_ORIGINS=* \
    OLLAMA_KEEP_ALIVE=24h \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_NUM_CTX=8192 \
    OLLAMA_MODELS=/root/.ollama/models \
    OLLAMA_PRELOAD_MODEL=${OLLAMA_PRELOAD_MODEL}

COPY --from=model-fetch /root/.ollama /root/.ollama
COPY ollama/entrypoint.sh /usr/local/bin/ollama-entrypoint.sh

RUN chmod 0755 /usr/local/bin/ollama-entrypoint.sh

EXPOSE 11434

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:11434/api/tags >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/ollama-entrypoint.sh"]

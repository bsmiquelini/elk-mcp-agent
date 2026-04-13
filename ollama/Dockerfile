# syntax=docker/dockerfile:1.7

FROM ollama/ollama:latest AS model-fetch

ARG OLLAMA_PRELOAD_MODEL=qwen2.5:7b

ENV OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_MODELS=/root/.ollama/models

SHELL ["/bin/sh", "-ceu"]

RUN mkdir -p /root/.ollama/models && \
    ollama serve >/tmp/ollama-build.log 2>&1 & \
    pid="$!" && \
    i=0 && \
    until ollama list >/dev/null 2>&1; do \
      i=$((i+1)); \
      [ "$i" -ge 120 ] && echo "Ollama não ficou pronto no build" && cat /tmp/ollama-build.log && exit 1; \
      sleep 1; \
    done && \
    ollama pull "${OLLAMA_PRELOAD_MODEL}" && \
    kill "$pid" && \
    wait "$pid" || true

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

ENTRYPOINT ["/usr/local/bin/ollama-entrypoint.sh"]

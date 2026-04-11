FROM ollama/ollama:latest

ARG OLLAMA_PRELOAD_MODEL=qwen2.5:7b

ENV OLLAMA_HOST=0.0.0.0 \
    OLLAMA_ORIGINS=* \
    OLLAMA_KEEP_ALIVE=24h \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_NUM_CTX=8192 \
    OLLAMA_PRELOAD_MODEL=${OLLAMA_PRELOAD_MODEL}

COPY ollama/entrypoint.sh /usr/local/bin/ollama-entrypoint.sh

RUN chmod 0755 /usr/local/bin/ollama-entrypoint.sh

EXPOSE 11434

ENTRYPOINT ["/usr/local/bin/ollama-entrypoint.sh"]

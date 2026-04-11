FROM cgr.dev/chainguard/python:latest-dev AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/tmp/venv

WORKDIR /build

RUN python -m venv "${VENV_PATH}"

COPY agent/requirements.txt /tmp/agent-requirements.txt
COPY mcp_server/requirements.txt /tmp/mcp-requirements.txt

RUN "${VENV_PATH}/bin/pip" install --upgrade pip setuptools wheel && \
    "${VENV_PATH}/bin/pip" install \
      -r /tmp/agent-requirements.txt \
      -r /tmp/mcp-requirements.txt


FROM cgr.dev/chainguard/python:latest AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/tmp/venv/bin:$PATH

WORKDIR /app

COPY --from=builder /tmp/venv /tmp/venv
COPY --chown=65532:65532 agent ./agent
COPY --chown=65532:65532 mcp_server ./mcp_server
COPY --chown=65532:65532 scripts ./scripts
COPY --chown=65532:65532 config.yaml README.md .env.example ./

EXPOSE 8787

USER 65532

ENTRYPOINT ["python"]
CMD ["agent/main.py"]

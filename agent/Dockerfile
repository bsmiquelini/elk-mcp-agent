FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VENV_PATH=/opt/venv

WORKDIR /build

RUN python -m venv "${VENV_PATH}"

COPY agent/requirements.txt /tmp/agent-requirements.txt
COPY mcp_server/requirements.txt /tmp/mcp-requirements.txt
COPY scripts/requirements-seed.txt /tmp/seed-requirements.txt

RUN "${VENV_PATH}/bin/pip" install --upgrade pip setuptools wheel && \
    "${VENV_PATH}/bin/pip" install \
      -r /tmp/agent-requirements.txt \
      -r /tmp/mcp-requirements.txt \
      -r /tmp/seed-requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && \
    useradd --system --gid app --create-home --home-dir /home/app app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app agent ./agent
COPY --chown=app:app mcp_server ./mcp_server
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app config.yaml README.md .env.example ./

EXPOSE 8787

USER app

ENTRYPOINT ["python3"]
CMD ["agent/main.py"]

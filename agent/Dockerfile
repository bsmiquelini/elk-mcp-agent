FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

EXPOSE 8787

COPY agent/requirements.txt /tmp/agent-requirements.txt
COPY mcp_server/requirements.txt /tmp/mcp-requirements.txt
COPY scripts/requirements-seed.txt /tmp/seed-requirements.txt

RUN pip install --no-cache-dir \
    -r /tmp/agent-requirements.txt \
    -r /tmp/mcp-requirements.txt \
    -r /tmp/seed-requirements.txt

COPY agent ./agent
COPY mcp_server ./mcp_server
COPY scripts ./scripts
COPY config.yaml README.md .env.example ./

ENTRYPOINT ["python3"]
CMD ["agent/main.py"]

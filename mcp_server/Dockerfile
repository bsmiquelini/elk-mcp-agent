FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY mcp_server/requirements.txt /tmp/mcp-requirements.txt
RUN pip install --no-cache-dir -r /tmp/mcp-requirements.txt

COPY mcp_server ./mcp_server
COPY config.yaml README.md .env.example ./

ENTRYPOINT ["python3"]
CMD ["mcp_server/main.py"]

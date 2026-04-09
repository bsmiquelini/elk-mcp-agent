# Plano de Operação em Produção

Este documento descreve como publicar o MVP em produção com LLM local via Ollama, como parametrizar a conexão com Elasticsearch e como operar o agente e o MCP em ambiente remoto.

## Estado atual do projeto

Hoje o projeto funciona assim:

- o `agent` é a interface principal de execução
- o `mcp_server` usa transporte `stdio`
- o próprio `agent` sobe `mcp_server/main.py` como processo filho
- o Elasticsearch e o Ollama podem estar em máquinas diferentes, desde que o `agent` consiga alcançá-los

Implicação importante:

- para uso remoto, o caminho mais simples e mais fiel ao código atual é rodar o container do `agent`
- o container isolado de `mcp_server` é útil para debug, inspeção ou futura evolução, mas hoje ele não expõe um endpoint HTTP para clientes remotos

Se no futuro você quiser um MCP realmente remoto, o próximo passo é migrar para um transporte HTTP/streamable HTTP.

## Variáveis principais

Use estas variáveis para parametrizar a operação:

| Variável | Uso |
| --- | --- |
| `ELASTICSEARCH_URL` | URL base do Elasticsearch |
| `ELASTICSEARCH_USERNAME` | usuário do Elasticsearch |
| `ELASTIC_PASSWORD` | senha do usuário |
| `ELASTICSEARCH_INDEX` | pattern do índice, ex. `github-workflows*` |
| `ELASTICSEARCH_VERIFY_SSL` | `true` ou `false` |
| `AGENT_PROVIDER` | `ollama` ou `groq` |
| `OLLAMA_API_BASE` | URL do servidor Ollama publicado |
| `OLLAMA_MODEL` | modelo usado pelo agente, ex. `qwen2.5:7b` |
| `OLLAMA_HOST_PORT` | porta publicada do container local do Ollama no host |
| `GROQ_API_KEY` | opcional, só se usar Groq |

Exemplo para produção:

```bash
export ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200"
export ELASTICSEARCH_USERNAME="elastic"
export ELASTIC_PASSWORD="sua-senha"
export ELASTICSEARCH_INDEX="github-workflows*"
export ELASTICSEARCH_VERIFY_SSL=true

export AGENT_PROVIDER=ollama
export OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434"
export OLLAMA_MODEL="qwen2.5:7b"
```

## Build e Push das imagens

Exemplo usando registry privado:

```bash
export REGISTRY="registry.exemplo.intra"
export IMAGE_PREFIX="${REGISTRY}/observability/elk-mcp-agent"
export TAG="v1.0.0"

docker build -f agent/Dockerfile -t "${IMAGE_PREFIX}-agent:${TAG}" .
docker build -f mcp_server/Dockerfile -t "${IMAGE_PREFIX}-mcp:${TAG}" .

docker push "${IMAGE_PREFIX}-agent:${TAG}"
docker push "${IMAGE_PREFIX}-mcp:${TAG}"
```

Se quiser também marcar `latest`:

```bash
docker tag "${IMAGE_PREFIX}-agent:${TAG}" "${IMAGE_PREFIX}-agent:latest"
docker tag "${IMAGE_PREFIX}-mcp:${TAG}" "${IMAGE_PREFIX}-mcp:latest"

docker push "${IMAGE_PREFIX}-agent:latest"
docker push "${IMAGE_PREFIX}-mcp:latest"
```

## Cenário 1: VM com Docker

### Topologia recomendada

- VM 1: Ollama, preferencialmente com GPU
- VM 2: agent, opcionalmente com Elasticsearch acessível pela rede
- Elasticsearch: cluster já existente

Se quiser simplificar o MVP:

- Ollama e agent podem rodar na mesma VM

### Subindo Ollama em uma VM

Opção com Docker:

```bash
docker run -d \
  --name ollama \
  --restart unless-stopped \
  -p 11434:11434 \
  -v ollama-data:/root/.ollama \
  ollama/ollama:latest
```

Depois carregue o modelo:

```bash
docker exec -it ollama ollama pull qwen2.5:7b
```

Para expor o serviço atrás de reverse proxy, a documentação do Ollama indica que a API fica em `http://localhost:11434/api` e que o serviço pode ser exposto em rede ajustando `OLLAMA_HOST` ou usando proxy reverso. Exemplo simples com Nginx:

```nginx
server {
  listen 80;
  server_name ollama-prod.exemplo.intra;

  location / {
    proxy_pass http://127.0.0.1:11434;
    proxy_set_header Host localhost:11434;
  }
}
```

### Rodando o agente remotamente em container

Exemplo:

```bash
docker run --rm -it \
  -e ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200" \
  -e ELASTICSEARCH_USERNAME="elastic" \
  -e ELASTIC_PASSWORD="sua-senha" \
  -e ELASTICSEARCH_INDEX="github-workflows*" \
  -e ELASTICSEARCH_VERIFY_SSL=true \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -v $(pwd)/artifacts:/app/artifacts \
  "${IMAGE_PREFIX}-agent:${TAG}" \
  agent/main.py --question "Qual foi o ultimo workflow que rodou?"
```

### Rodando em modo interativo

```bash
docker run --rm -it \
  -e ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200" \
  -e ELASTICSEARCH_USERNAME="elastic" \
  -e ELASTIC_PASSWORD="sua-senha" \
  -e ELASTICSEARCH_INDEX="github-workflows*" \
  -e ELASTICSEARCH_VERIFY_SSL=true \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -v $(pwd)/artifacts:/app/artifacts \
  "${IMAGE_PREFIX}-agent:${TAG}"
```

### MCP server em VM

Como o MCP atual é `stdio`, o uso remoto mais prático continua sendo através do `agent`. Ainda assim, você pode subir o container do `mcp_server` para debug:

```bash
docker run --rm -it \
  -e ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200" \
  -e ELASTICSEARCH_USERNAME="elastic" \
  -e ELASTIC_PASSWORD="sua-senha" \
  -e ELASTICSEARCH_INDEX="github-workflows*" \
  "${IMAGE_PREFIX}-mcp:${TAG}" \
  mcp_server/main.py
```

## Cenário 2: Kubernetes

## Estratégia recomendada

- namespace `observability-ai`
- Ollama em Deployment com PVC
- agent em Deployment simples para `kubectl exec` ou Job sob demanda
- artifacts HTML montados em PVC ou exportados para object storage

## Exemplo com manifests puros

### Ollama

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: observability-ai
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-data
  namespace: observability-ai
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: observability-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
        - name: ollama
          image: ollama/ollama:latest
          ports:
            - containerPort: 11434
          env:
            - name: OLLAMA_HOST
              value: "0.0.0.0:11434"
            - name: OLLAMA_KEEP_ALIVE
              value: "24h"
          volumeMounts:
            - name: ollama-data
              mountPath: /root/.ollama
      volumes:
        - name: ollama-data
          persistentVolumeClaim:
            claimName: ollama-data
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: observability-ai
spec:
  selector:
    app: ollama
  ports:
    - name: http
      port: 11434
      targetPort: 11434
```

Depois de subir:

```bash
kubectl -n observability-ai exec -it deploy/ollama -- ollama pull qwen2.5:7b
```

### Agent

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elk-mcp-agent
  namespace: observability-ai
spec:
  replicas: 1
  selector:
    matchLabels:
      app: elk-mcp-agent
  template:
    metadata:
      labels:
        app: elk-mcp-agent
    spec:
      containers:
        - name: agent
          image: registry.exemplo.intra/observability/elk-mcp-agent-agent:v1.0.0
          command: ["sleep", "infinity"]
          env:
            - name: ELASTICSEARCH_URL
              value: "https://elk-prod.exemplo.intra:9200"
            - name: ELASTICSEARCH_USERNAME
              value: "elastic"
            - name: ELASTIC_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: elk-mcp-agent-secrets
                  key: elastic-password
            - name: ELASTICSEARCH_INDEX
              value: "github-workflows*"
            - name: ELASTICSEARCH_VERIFY_SSL
              value: "true"
            - name: AGENT_PROVIDER
              value: "ollama"
            - name: OLLAMA_API_BASE
              value: "http://ollama.observability-ai.svc.cluster.local:11434"
            - name: OLLAMA_MODEL
              value: "qwen2.5:7b"
          volumeMounts:
            - name: dashboards
              mountPath: /app/artifacts
      volumes:
        - name: dashboards
          emptyDir: {}
```

### Execução remota do agente no cluster

Interação ad-hoc:

```bash
kubectl -n observability-ai exec -it deploy/elk-mcp-agent -- \
  python3 agent/main.py --question "Quantos deploys ocorreram no ultimo dia?"
```

### Coleta do dashboard HTML

```bash
kubectl -n observability-ai cp \
  deploy/elk-mcp-agent:/app/artifacts/dashboards/last_dashboard.html \
  ./last_dashboard.html
```

## Charts Helm

Eu não encontrei um chart oficial do Ollama mantido pela equipe do produto nas fontes consultadas. O que encontrei foram charts comunitários:

- `feiskyer/ollama-kubernetes`
- `otwld/ollama-helm`

Exemplo com `feiskyer/ollama-kubernetes`:

```bash
helm repo add ollama https://feisky.xyz/ollama-kubernetes
helm repo update
helm upgrade --install ollama ollama/ollama \
  --namespace ollama \
  --create-namespace
```

Exemplo com `otwld/ollama-helm`:

```bash
helm repo add otwld https://helm.otwld.com/
helm repo update
helm install ollama otwld/ollama \
  --namespace ollama \
  --create-namespace
```

Recomendação prática:

- se quiser previsibilidade total para o MVP, comece com manifests próprios
- se quiser acelerar bootstrap em cluster, use um chart comunitário, mas trate-o como dependência externa não oficial

## Como interagir remotamente

Hoje você tem três formas práticas:

### 1. `docker run` com uma pergunta direta

```bash
docker run --rm -it \
  -e ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200" \
  -e ELASTICSEARCH_USERNAME="elastic" \
  -e ELASTIC_PASSWORD="sua-senha" \
  -e ELASTICSEARCH_INDEX="github-workflows*" \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -v $(pwd)/artifacts:/app/artifacts \
  "${IMAGE_PREFIX}-agent:${TAG}" \
  agent/main.py --question "Qual a taza de sucesso e falha nos deploys de workflows java?"
```

### 2. `kubectl exec` em um pod do agent

```bash
kubectl -n observability-ai exec -it deploy/elk-mcp-agent -- \
  python3 agent/main.py --question "Quais os problemas mais recorrebtes que acontecem nas falhas de jobs de build?"
```

### 3. entrar no container e usar modo interativo

```bash
docker run --rm -it \
  -e ELASTICSEARCH_URL="https://elk-prod.exemplo.intra:9200" \
  -e ELASTICSEARCH_USERNAME="elastic" \
  -e ELASTIC_PASSWORD="sua-senha" \
  -e ELASTICSEARCH_INDEX="github-workflows*" \
  -e AGENT_PROVIDER=ollama \
  -e OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434" \
  -e OLLAMA_MODEL="qwen2.5:7b" \
  -v $(pwd)/artifacts:/app/artifacts \
  "${IMAGE_PREFIX}-agent:${TAG}"
```

## Dashboards HTML

As perguntas principais do MVP agora geram dashboard HTML em:

- `/app/artifacts/dashboards/last_dashboard.html`
- `/app/artifacts/dashboards/latest_workflow.html`
- `/app/artifacts/dashboards/deploys_last_day.html`
- `/app/artifacts/dashboards/java_deploy_success_rate.html`
- `/app/artifacts/dashboards/build_failures_recurrence.html`

Para persistir isso em produção:

- em Docker: monte um volume host em `/app/artifacts`
- em Kubernetes: monte `emptyDir`, PVC ou escreva em object storage por etapa posterior

## Parametrizações recomendadas

### Publicando Ollama em outro host

Quando o Ollama estiver em outro host, basta ajustar:

```bash
export OLLAMA_API_BASE="http://ollama-prod.exemplo.intra:11434"
export OLLAMA_MODEL="qwen2.5:7b"
```

### Apontando para outro cluster Elasticsearch

```bash
export ELASTICSEARCH_URL="https://novo-elk.exemplo.intra:9200"
export ELASTICSEARCH_INDEX="github-workflows*"
export ELASTICSEARCH_VERIFY_SSL=true
```

### Mudando o pattern do índice

```bash
export ELASTICSEARCH_INDEX="github-workflows-prod-*"
```

## Checklist de produção

- publicar imagens do `agent` e do `mcp_server`
- provisionar Ollama com persistência e, se possível, GPU
- garantir que o modelo `qwen2.5:7b` está baixado no host ou pod do Ollama
- configurar `ELASTICSEARCH_URL`, credenciais e index pattern
- montar volume para `/app/artifacts`
- validar com as quatro perguntas principais
- coletar o HTML gerado em `artifacts/dashboards`

## Fontes consultadas

- Ollama docs: https://docs.ollama.com/
- FAQ do Ollama, incluindo `OLLAMA_HOST`, exposição em rede e proxy: https://docs.ollama.com/faq
- API do Ollama e base URL: https://docs.ollama.com/api/introduction
- Repositório oficial do Ollama e imagem Docker oficial: https://github.com/ollama/ollama
- Chart comunitário `feiskyer/ollama-kubernetes`: https://github.com/feiskyer/ollama-kubernetes
- Chart comunitário `otwld/ollama-helm`: https://github.com/otwld/ollama-helm

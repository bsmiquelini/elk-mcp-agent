# Deploy

Esta pasta concentra os artefatos práticos de publicação do projeto.

## Estrutura

- `docker-bake.hcl`: build/push das imagens do `agent` e do `mcp_server`
- `env/production.env.example`: exemplo de variáveis para produção
- `k8s/`: manifests Kubernetes prontos para adaptação
- `helm/`: exemplos de `values.yaml` para Helm

## Build com buildx bake

Build local:

```bash
docker buildx bake -f deploy/docker-bake.hcl images
```

Build e push:

```bash
docker buildx bake -f deploy/docker-bake.hcl release --push
```

Com override de registry/tag:

```bash
REGISTRY=registry.exemplo.intra \
IMAGE_NAMESPACE=observability \
VERSION=v1.0.0 \
docker buildx bake -f deploy/docker-bake.hcl release --push
```

## Kubernetes

Arquivos principais:

- `k8s/namespace.yaml`
- `k8s/configmap.yaml`
- `k8s/secret.example.yaml`
- `k8s/ollama.yaml`
- `k8s/agent.yaml`
- `k8s/mcp-server.yaml`
- `k8s/agent-question-job.yaml`

Aplicação base:

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/configmap.yaml
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/secret.yaml
kubectl apply -f deploy/k8s/ollama.yaml
kubectl apply -f deploy/k8s/agent.yaml
kubectl apply -f deploy/k8s/mcp-server.yaml
```

Execução de pergunta via Job:

```bash
kubectl apply -f deploy/k8s/agent-question-job.yaml
kubectl -n observability-ai logs -f job/elk-mcp-agent-question
```

## Helm

Arquivos principais:

- `helm/ollama-values.yaml`
- `helm/agent-values.yaml`
- `helm/README.md`

Os exemplos usam charts externos para Ollama e um chart hipotético para o `agent`, servindo como base de parametrização.

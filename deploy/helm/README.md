# Helm

Esta pasta traz exemplos de `values.yaml` para dois cenários:

- `ollama-values.yaml`: uso com chart comunitário do Ollama
- `agent-values.yaml`: base para um chart do `agent`, ou para adaptar em um chart interno da sua plataforma

## Ollama com Helm

Exemplo com o chart comunitário `feiskyer/ollama-kubernetes`:

```bash
helm repo add ollama https://feisky.xyz/ollama-kubernetes
helm repo update
helm upgrade --install ollama ollama/ollama \
  --namespace observability-ai \
  --create-namespace \
  -f deploy/helm/ollama-values.yaml
```

Exemplo com `otwld/ollama-helm`:

```bash
helm repo add otwld https://helm.otwld.com/
helm repo update
helm upgrade --install ollama otwld/ollama \
  --namespace observability-ai \
  --create-namespace \
  -f deploy/helm/ollama-values.yaml
```

## Agent com Helm

Você pode usar `deploy/helm/agent-values.yaml` como base para um chart interno simples, com:

- image repository/tag
- env vars do Elasticsearch
- endereço do Ollama publicado
- volume para `artifacts/dashboards`

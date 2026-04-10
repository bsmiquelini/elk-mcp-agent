# Plano Production-Ready

## Objetivo

Evoluir o projeto de um MVP funcional para um produto interno pronto para
produção, com foco em:

- confiabilidade operacional
- segurança e governança
- escalabilidade da inferência
- observabilidade
- ergonomia para usuários internos
- acurácia validada contra o Elasticsearch

## Nota alvo

Situação atual estimada:

- arquitetura: `8.3/10`
- funcionalidade: `8.0/10`

Meta de produção:

- arquitetura: `9.5+`
- funcionalidade: `9.3+`
- operação: `9.5+`

## Decisão arquitetural principal

### Recomendado

Usar um **gateway central de inferência OpenAI-compatible** para abstrair o
modelo do agente.

Isso atende melhor às restrições:

- o usuário não precisa instalar `Ollama`
- o cliente não precisa conhecer chave individual
- a empresa pode trocar o backend de inferência sem reescrever o agente
- a escalabilidade do modelo fica desacoplada do CLI/MCP

### Não recomendado como caminho principal

Depender de `Ollama` na estação do usuário final.

Use `Ollama` apenas para:

- laboratório
- benchmark local
- homologação técnica
- fallback controlado

## Arquitetura alvo

### Camadas

1. `CLI` ou `UI` interna
2. `Agent API` centralizada
3. `MCP/Query Service`
4. `Elasticsearch`
5. `LLM Gateway OpenAI-compatible`
6. `Inference backend`

### Backends possíveis para inferência

- `vLLM`
- `SGLang`
- `Ollama` apenas como fallback/lab

## Roadmap

### Fase 1. Estabilização do core

- fechar a suíte `300/300` cross-validated no seed novo
- colocar a suíte executiva em CI
- transformar regressões semânticas em testes fixos
- padronizar métricas de negócio em um módulo dedicado

### Fase 2. Produto de serviço

- expor o agente por HTTP/gRPC além de CLI
- status atual:
  - API HTTP inicial entregue em `agent/http_service.py`
  - endpoint `POST /v1/ask`
  - endpoint `GET /healthz`
- desacoplar o relatório executivo da CLI via chamada interna
- transformar o MCP em serviço remoto opcional
- suportar multiusuário e sessões persistidas

### Fase 3. Inference gateway

- operar com `provider=openai_compatible`
- configurar autenticação por SSO, service account ou gateway interno
- mover seleção de modelo para o gateway
- aplicar rate limit, quotas e circuit breaker

### Fase 4. Segurança e governança

- autenticação corporativa
- autorização por perfil
- trilha de auditoria de perguntas e relatórios
- mascaramento de dados sensíveis
- políticas de retenção

### Fase 5. Observabilidade

- logs estruturados por correlação
- métricas de:
  - latência por pergunta
  - acurácia por tipo de consulta
  - falhas por provider
  - cache hit ratio
  - tempo de geração de relatório
- tracing entre `agent`, `MCP`, `ELK` e gateway LLM

### Fase 6. Escalabilidade

- cache de schema
- cache de perguntas frequentes
- materialização de agregados críticos
- filas para relatórios grandes
- execução assíncrona para relatórios gerenciais

### Fase 7. UX interna

- catálogo guiado de perguntas
- sugestões por contexto
- relatórios parametrizáveis por time, arquitetura, período e ambiente
- exportação PDF/HTML
- dashboards comparativos

## Recomendações imediatas

### 1. Provider de produção

Usar `openai_compatible` como provider padrão da empresa.

### 2. Backend de inferência

Priorizar `vLLM` ou outro servidor com API OpenAI-compatible para carga
concorrente. `Ollama` pode permanecer como fallback de laboratório.

### 3. Modelo de consumo

O usuário final deve consumir:

- `CLI` apontando para serviços centrais, ou
- interface web interna

O desktop não deve carregar o runtime do modelo.

### 4. Topologia recomendada

- `agent-api`
- `mcp-query-service`
- `llm-gateway`
- `elasticsearch`
- `cache`
- `queue`

## Sobre OpenCode

`OpenCode` pode fazer sentido como ferramenta de desenvolvimento ou consumo
assistido por login do ecossistema Copilot, mas não como dependência central do
produto.

Para o produto interno, o melhor caminho é:

- manter o agente falando com uma API OpenAI-compatible
- deixar o gateway corporativo resolver autenticação, roteamento e modelo

## Critérios de pronto

O produto pode ser considerado próximo de `10` quando:

- a suíte funcional e executiva roda em CI sem intervenção manual
- o tempo de resposta é previsível
- o serviço não depende de `Ollama` na máquina do usuário
- a autenticação é corporativa
- há observabilidade completa
- relatórios executivos são reproduzíveis
- a troca de backend/modelo é transparente para o agente

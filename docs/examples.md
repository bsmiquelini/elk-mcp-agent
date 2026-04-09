# Exemplos de Perguntas e Respostas Esperadas

Este arquivo documenta o comportamento esperado do MVP. Como os dados podem ser recriados e o agente descobre o schema dinamicamente, o mais importante aqui é a estrutura e a coerência da resposta com o Elasticsearch.

## Perguntas principais

### 1. Último workflow

Pergunta:

```text
Qual foi o ultimo workflow que rodou?
```

Resposta esperada:

```text
O ultimo workflow encontrado foi `<nome do workflow>` no repositorio `<org/repo>`, com status `<status>` [no ambiente <ambiente>], em `<timestamp>`.
```

Validação:

- deve conter o nome do workflow mais recente
- deve conter o repositório
- deve conter status
- deve conter timestamp

### 2. Deploys no último dia

Pergunta:

```text
Quantos deploys ocorreram no ultimo dia?
```

Resposta esperada:

```text
Foram encontrados <N> deploys no ultimo dia.
```

ou

```text
Nenhum deploy ocorreu no ultimo dia.
```

Validação:

- o número precisa bater com a agregação do Elasticsearch para o período de `1d`

### 3. Taxa de sucesso e falha em deploys Java

Pergunta:

```text
Qual a taza de sucesso e falha nos deploys de workflows java?
```

Resposta esperada:

```text
Taxa dos deploys Java nos ultimos 30 dias: Sucesso: <A> (<P1>) | Falha: <B> (<P2>) | Outros estados: <C> (<P3>).
```

Validação:

- as contagens precisam bater com os buckets agregados por `deployment_status.state`
- os percentuais precisam ser coerentes com o total encontrado

### 4. Falhas recorrentes de build

Pergunta:

```text
Quais os problemas mais recorrebtes que acontecem nas falhas de jobs de build?
```

Resposta esperada:

```text
Nos ultimos 90 dias, os checks/jobs de build com mais falhas foram: <job1> (<n1>), <job2> (<n2>), <job3> (<n3>).
```

Validação:

- a resposta deve refletir o ranking agregado por nome de `check_run` ou `job`
- a ordenação precisa acompanhar o volume de falhas

## Como validar

Os testes em [scripts/test_mvp_queries.py](/home/bruno/lab_ia/elk-mcp-agent/scripts/test_mvp_queries.py) calculam a baseline diretamente no Elasticsearch e comparam as respostas do agente com esses resultados, evitando dependência em nomes de campos pré-configurados.

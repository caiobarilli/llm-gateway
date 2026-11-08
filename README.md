# llm-gateway

[![CI](https://github.com/caiobarilli/llm-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/caiobarilli/llm-gateway/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)

Proxy fechado entre um app e um LLM local, no formato da API da OpenAI.

## Por que existe

O PHParrot gera textos de treino com um modelo que roda no Ollama, numa máquina com GPU. Em vez de abrir o Ollama na rede, o app fala com este gateway. O gateway pede um token, aceita só os modelos da lista, atende um pedido por vez e confere a saída contra o JSON Schema do pedido. Só ele chama o Ollama. Trocar o motor muda o gateway, não o app.

```mermaid
flowchart LR
    app["App consumidor"]
    gw["llm-gateway<br/>token, allowlist, um pedido por vez,<br/>saída validada por JSON Schema"]
    ollama["Ollama<br/>POST /api/chat"]

    app -- "API da OpenAI<br/>Bearer" --> gw
    gw -- "stream false" --> ollama
```

## Recursos

- Token Bearer lido de um arquivo, relido a cada pedido, comparado em tempo constante. Sem token configurado, nada passa.
- Allowlist de modelos: o que não está na lista nunca chega ao Ollama.
- Um pedido por vez, sem fila: ocupado responde 503 com `Retry-After`.
- Saída validada por um subconjunto de JSON Schema (Draft 2020-12): sem `$ref`, `pattern` nem combinadores. Saída inválida ou cortada vira erro 502, sem o texto.
- Uma linha de métricas por pedido, sem prompt, resposta, schema nem token.
- Imagem endurecida: bases por digest, usuário 10002, sem `pip`, `zlib1g` atualizado, e sobe com o sistema de arquivos só leitura.

## Quickstart

### Docker

```bash
docker build -t llm-gateway .

TOKEN_ARQUIVO="$(mktemp)" && printf 'exemplo-nao-use-em-producao-0123456789' > "$TOKEN_ARQUIVO" && chmod 644 "$TOKEN_ARQUIVO"

docker run --rm -p 127.0.0.1:8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -v "$TOKEN_ARQUIVO:/token:ro" \
  -e GATEWAY_TOKEN_ARQUIVO=/token \
  -e GATEWAY_MODELOS=llama3.2:3b \
  -e GATEWAY_CONCORRENCIA=1 \
  -e GATEWAY_OLLAMA_URL=http://host.docker.internal:11434 \
  llm-gateway
```

```bash
curl http://127.0.0.1:8000/health
curl -H "Authorization: Bearer exemplo-nao-use-em-producao-0123456789" http://127.0.0.1:8000/v1/models
```

### uv

```bash
uv sync --locked --no-dev

TOKEN_ARQUIVO="$(mktemp)" && printf 'exemplo-nao-use-em-producao-0123456789' > "$TOKEN_ARQUIVO"

GATEWAY_TOKEN_ARQUIVO="$TOKEN_ARQUIVO" GATEWAY_MODELOS=llama3.2:3b GATEWAY_CONCORRENCIA=1 \
GATEWAY_OLLAMA_URL=http://127.0.0.1:11434 \
uv run uvicorn --factory llm_gateway.app:criar_app --host 127.0.0.1 --port 8000
```

As quatro variáveis `GATEWAY_*` são obrigatórias (`docs/configuracao.md`).

## API

| Rota | Autenticação | O que faz |
|---|---|---|
| `GET /health` | nenhuma | `200` com `{"status":"ok"}`. |
| `GET /v1/models` | Bearer | Lista os modelos da allowlist. |
| `POST /v1/chat/completions` | Bearer | Chat sem stream, com `response_format` do tipo `json_schema` opcional. |

Erros saem no formato da OpenAI, com um `code` estável. Corpo, limites, tabela de erros e exemplos em [docs/api.md](docs/api.md). O contrato em OpenAPI está em [docs/openapi.json](docs/openapi.json).

## Segurança

- Rotas fechadas por token: só o `/health` é pública.
- Corpo de até 64 KiB, 8 mensagens, 8000 caracteres, `max_tokens` até 1024 e campos desconhecidos recusados.
- `/docs`, `/redoc` e `/openapi.json` ficam desligados em runtime.
- O gateway só chama `POST /api/chat` no endereço configurado. O schema do pedido é um subconjunto de JSON Schema: `$ref` é recusado, então nada no pedido faz o gateway buscar uma URL.
- A porta não é publicada por padrão. Se for, só em `127.0.0.1`.

O modelo de ameaças e o mapa para o OWASP API Top 10 estão em [docs/seguranca.md](docs/seguranca.md).

## Qualidade

O gate é `docker build --target teste .`. Ele roda:

- `ruff`: PEP 8 com linha de 120 (desvio registrado no [ADR 0006](.ai/adr/0006-linha-de-120-desvio-do-pep-8.md)), mais o conjunto `S` de segurança, o `PT` do pytest e o `ASYNC`;
- `mypy --strict`, com `warn_unreachable` e `explicit-override`;
- `pytest`, com o Ollama simulado, sem acesso à rede, aviso como erro e piso de cobertura (linhas e ramos);
- a trava de comentários: só `# type:` e `# noqa` passam.

Dependências com versão exata e `uv.lock`. Imagens base fixadas por digest. O CI roda a trava e o gate em push e em pull request para o `main`.

## Consumidor de referência

O [PHParrot](https://github.com/caiobarilli/PHParrot) usa este gateway para gerar textos de treino. O gateway nasceu em `docker/gateway/` dele, e o [ADR 0013](https://github.com/caiobarilli/PHParrot/blob/main/.ai/adr/0013-gateway-de-ia.md) registra o lado do consumidor.

## Estrutura

```
src/llm_gateway/   o pacote: app, autenticação, chat, Ollama, limitador, erros, log
tests/             pytest, com o Ollama falso
tools/             a trava de comentários e o exportador do OpenAPI
docs/              uso: arquitetura, API, configuração, segurança, operação, desenvolvimento
.ai/               regras, teto, pitfalls e ADRs
.claude/skills/    as skills do projeto
Dockerfile         estágios dependencias, construcao, teste e a imagem final
```

## Documentação

- [Arquitetura](docs/arquitetura.md)
- [API](docs/api.md)
- [Configuração](docs/configuracao.md)
- [Segurança](docs/seguranca.md)
- [Operação](docs/operacao.md)
- [Desenvolvimento](docs/desenvolvimento.md)
- Decisões: [.ai/adr/](.ai/adr/), [regras](.ai/regras.md), [teto](.ai/teto.md) e [pitfalls](.ai/pitfalls.md)

## Licença

MIT. Veja o [LICENSE](LICENSE).

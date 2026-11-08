# Teto

Proxy fechado entre um app e um LLM local, no formato da API da OpenAI.

## Dentro

- `GET /health`, pública.
- `GET /v1/models` e `POST /v1/chat/completions`, com token Bearer.
- O upstream só recebe `POST /api/chat`, sem stream.
- Um pedido por vez. Com o `Limitador` cheio, a resposta é 503 `ocupado`, na hora.
- Allowlist de modelos, limites de corpo, de mensagens e de tokens, saída validada por JSON Schema.
- Uma linha de métricas por pedido ao chat, sem texto.
- Porta não publicada por padrão. Se for publicada, só em `127.0.0.1`.

## Fora do teto

- Operação administrativa no Ollama (baixar, apagar, listar o que existe). Isso é do PHPorto.
- Qualquer outra rota do upstream.

## Fora até o Maintainer mandar

- Stream.
- Fila.
- Motor pago.
- Banco de dados.
- Rota pública nova.
- Documentação interativa em runtime (`/docs`, `/redoc`, `/openapi.json`).

O servidor MCP só entra no teto no PR dele, com ADR.

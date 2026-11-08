# Gateway próprio em FastAPI

## Contexto

O PHParrot gera textos de treino com o `llama3.2:3b` num Ollama local. O ADR 0013 do PHParrot ([`.ai/adr/0013-gateway-de-ia.md`](https://github.com/caiobarilli/PHParrot/blob/main/.ai/adr/0013-gateway-de-ia.md)) decidiu o gateway junto com o resto do app: Terraform, Laravel, segredo montado e Dependabot. O código nasceu em `docker/gateway/` do PHParrot e depois foi separado neste repositório.

## Decisão

Um gateway próprio em Python com FastAPI, pequeno e fechado. O que o consumidor precisa é pouco:

- uma rota de chat no formato da OpenAI e a lista de modelos;
- um token em arquivo;
- uma allowlist de modelos;
- um pedido por vez;
- a saída validada por JSON Schema.

Cada item é código deste repositório e tem teste. A escolha é de escopo. O LiteLLM cobre muitos provedores e recursos de gestão que este caso não usa, e aqui a superfície inteira cabe numa leitura. Não há medição comparando os dois neste repositório.

O ADR 0013 do PHParrot continua valendo para o lado do consumidor. Os ADRs 0002 a 0008 daqui detalham o lado do gateway.

## Consequência

- O gateway é o dono do contrato da API. O consumidor traduz os erros pelo `code` (`docs/api.md`). Mudar um `code` é mudança de contrato.
- Trocar o Ollama por outro motor muda o gateway, não o consumidor (ADR 0013 do PHParrot, item 4).
- O que cresce o teto (stream, fila, motor pago, banco) fica fora até o Maintainer mandar (`.ai/teto.md`).

## Evidência

- PHParrot: `61dff6c` (esqueleto do gateway), `1d10117`, `5c260de` e `f958a5e` (infraestrutura, autenticação e chat).
- Aqui: `src/llm_gateway/app.py:35-66` (a factory `criar_app`).

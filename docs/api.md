# API

Três rotas. Só o `/health` é pública. As outras ficam em `/v1` e exigem `Authorization: Bearer <token>`. Qualquer outro caminho responde 404 `not_found`, inclusive `/docs`, `/redoc` e `/openapi.json`. A barra final também: `/health/` e `/v1/models/` dão 404, sem redirecionamento e sem cabeçalho `Location`.

O contrato em OpenAPI está em [`docs/openapi.json`](openapi.json). Ele é gerado por `tools/exportar_openapi.py` a partir da factory. Como o chat lê o corpo cru, o script acrescenta o schema do `Pedido` e o esquema Bearer ao que o FastAPI declara.

Os exemplos usam o token fictício `exemplo-nao-use-em-producao-0123456789`.

## `GET /health`

- Autenticação: nenhuma.
- Resposta: `200` com `{"status":"ok"}`.
- Não consulta o Ollama. Diz só que o processo está de pé.

```bash
curl http://127.0.0.1:8000/health
```

## `GET /v1/models`

- Autenticação: Bearer.
- Resposta: `200` com a allowlist, na ordem de `GATEWAY_MODELOS`.

```bash
curl -H "Authorization: Bearer exemplo-nao-use-em-producao-0123456789" http://127.0.0.1:8000/v1/models
```

```json
{"object":"list","data":[{"id":"llama3.2:3b","object":"model","created":0,"owned_by":"llm-gateway"}]}
```

O `created` é sempre 0 e o `owned_by` é sempre `llm-gateway`.

## `POST /v1/chat/completions`

- Autenticação: Bearer.
- Corpo: JSON, até 64 KiB.
- Sem stream: `stream: true` dá 400 `stream_nao_suportado`.

### Corpo

| Campo | Tipo | Regra |
|---|---|---|
| `model` | string | Obrigatório, até 100 caracteres (mais que isso dá 400 `invalid_request`), e precisa estar na allowlist. |
| `messages` | lista | De 1 a 8 mensagens. |
| `messages[].role` | string | `system`, `user` ou `assistant`. |
| `messages[].content` | string | Até 8000 caracteres. A soma de todas as mensagens também fica em 8000. |
| `response_format` | objeto | Opcional. `type` só pode ser `json_schema`. |
| `response_format.json_schema.name` | string | De 1 a 64 caracteres, `[A-Za-z0-9_-]`. |
| `response_format.json_schema.schema` | objeto | Subconjunto de JSON Schema Draft 2020-12, validado como schema. Veja a lista abaixo. |
| `response_format.json_schema.description` | string | Opcional, até 512 caracteres. Não é repassada ao Ollama. |
| `response_format.json_schema.strict` | booleano | Opcional. Não é repassado ao Ollama. |
| `temperature` | número | Opcional, de 0 a 2. |
| `max_tokens` | inteiro | Opcional, de 1 a 1024. Padrão: 512. |
| `stream` | booleano | Opcional. `true` é recusado. |

Campo fora desta tabela é recusado com 400, não ignorado. O contexto (`num_ctx`) é fixo em 4096 e não vem do pedido.

### O subconjunto de JSON Schema

O schema vai inteiro para o Ollama (`format`) e valida a saída do modelo. Por isso o gateway aceita só estas palavras-chave: `type`, `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `minLength`, `maxLength`, `minItems`, `maxItems`, `minimum`, `maximum`, `title` e `description`. A lista também está no OpenAPI, em `x-palavras-chave`.

- Qualquer outra chave dá 400 `schema_invalido`: as que começam com `$` (`$ref`, `$defs`, `$schema`, `$id`), `pattern`, `patternProperties`, `format`, os combinadores (`allOf`, `anyOf`, `oneOf`, `not`, `if`), `default`, `examples`. A mensagem não cita a palavra.
- Nomes de campo dentro de `properties`, valores de `enum` e de `const` e itens de `required` são dado: uma propriedade chamada `pattern` vale.
- Tetos: 64 nós de schema, profundidade 6 (a raiz é o nível 1), inteiros de 0 a 4096 em `minLength`, `maxLength`, `minItems` e `maxItems`, e até 64 itens em `enum`. Passar de um teto também dá 400 `schema_invalido`.
- O gateway nunca busca um `$ref`, local ou remoto. O `parse()` do SDK `openai` com modelos Pydantic aninhados gera `$defs` e `$ref`, e por isso dá 400 `schema_invalido`. O mesmo vale para campo com valor padrão (`default`). Modelo plano passa.
- Mudar a lista é mudança de contrato (ADR 0009).

### Resposta 200

```json
{
  "id": "chatcmpl-60ad872223d046e0b390b2e282db4de1",
  "object": "chat.completion",
  "created": 1794103088,
  "model": "llama3.2:3b",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "{\"en\": \"I eat.\", \"pt\": \"Eu como.\"}"},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 63, "completion_tokens": 27, "total_tokens": 90}
}
```

O `finish_reason` é `stop` ou `length`. Sem `response_format`, a saída do modelo vai como veio. Com ele, o gateway valida a saída antes de responder.

### Exemplo

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer exemplo-nao-use-em-producao-0123456789" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "Escreva uma frase A1 sobre comida."}],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "frase",
        "schema": {
          "type": "object",
          "properties": {"en": {"type": "string"}, "pt": {"type": "string"}},
          "required": ["en", "pt"],
          "additionalProperties": false
        }
      }
    },
    "max_tokens": 128
  }'
```

### Limites

| Limite | Valor | Resposta ao passar |
|---|---|---|
| Corpo | 64 KiB (65536 bytes) | 413 `corpo_grande_demais` |
| Mensagens | 8 | 400 `invalid_request` |
| Caracteres por mensagem | 8000 | 400 `invalid_request` |
| Caracteres somados | 8000 | 400 `mensagens_grandes_demais` |
| `max_tokens` | 1024 | 400 `invalid_request` |
| Pedidos ao mesmo tempo | `GATEWAY_CONCORRENCIA` | 503 `ocupado` com `Retry-After: 10` |

## Erros

Todo erro sai no formato da OpenAI:

```json
{"error": {"message": "Token ausente ou inválido.", "type": "invalid_request_error", "param": null, "code": "invalid_api_key"}}
```

As mensagens são em português. O `code` é estável e é por ele que o consumidor decide o que fazer.

| `code` | Status | Quando acontece |
|---|---|---|
| `invalid_api_key` | 401 | Cabeçalho ausente, malformado ou token errado. A resposta leva `WWW-Authenticate: Bearer` e a mesma mensagem para os três casos. |
| `token_indisponivel` | 503 | O arquivo do token está ausente, ilegível, vazio, fora de ASCII ou com menos de 32 caracteres depois do `strip`. Nenhum token passa. |
| `invalid_request` | 400 | Corpo que não é JSON, campo desconhecido, campo fora do limite ou de tipo errado. A mensagem lista até 5 caminhos de campo do schema (`Pedido inválido em: messages.0.role.`). Campo desconhecido aparece só como o caminho até ele e `(campo não permitido)` (`Pedido inválido em: corpo (campo não permitido).`), sem o nome nem o valor que o cliente mandou. |
| `stream_nao_suportado` | 400 | `stream: true`. |
| `mensagens_grandes_demais` | 400 | A soma dos caracteres das mensagens passa de 8000. |
| `schema_invalido` | 400 | O `schema` do `response_format` não é um JSON Schema válido, usa palavra-chave fora do subconjunto ou passa de um teto. |
| `corpo_grande_demais` | 413 | O corpo passa de 64 KiB. |
| `model_not_found` | 404 | O modelo não está na allowlist. A mensagem cita o nome, que tem até 100 caracteres. |
| `not_found` | 404 | Rota inexistente. |
| `method_not_allowed` | 405 | Método não aceito pela rota. |
| `ocupado` | 503 | Sem vaga no `Limitador`. A resposta leva `Retry-After: 10`. |
| `upstream_indisponivel` | 503 | Falha de rede até o Ollama, como conexão recusada. |
| `upstream_timeout` | 504 | O Ollama não conectou em 5 s ou ficou 60 s sem responder. |
| `upstream_erro` | 502 | O Ollama respondeu com status diferente de 200. |
| `upstream_resposta_invalida` | 502 | O corpo do Ollama não tem o formato esperado. |
| `saida_truncada` | 502 | Com `response_format`, o modelo parou pelo `max_tokens`. |
| `saida_invalida` | 502 | Com `response_format`, a saída não é JSON ou não segue o schema. |
| `erro_interno` | 500 | Exceção não prevista. A mensagem é fixa e não leva detalhe. |

Nenhum erro devolve o texto do pedido, o texto do modelo ou o corpo do upstream.

### Ordem das recusas

Na ordem em que o código confere: token, tamanho do corpo, formato do pedido, modelo, schema (subconjunto e validade), vaga, upstream, saída. Um pedido com campo desconhecido e modelo fora da lista recebe 400, não 404.

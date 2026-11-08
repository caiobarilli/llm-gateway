# Subconjunto de JSON Schema no `response_format`

## Contexto

O schema do `response_format` vem do cliente, e o gateway o executa: valida a saída do modelo com ele (`jsonschema`) e o repassa ao Ollama em `format`. Medido na S1 do grilling (`.ai/grilling/2026-11-07-seguranca-codigo.md`), com o Ollama simulado:

- `{"$ref": "http://127.0.0.1:PORTA/segredo-interno"}` fez o `jsonschema` 4.26.0 buscar a URL (`urlopen`, sem timeout). O servidor interno de teste recebeu o `GET`. Com o servidor demorando 3 s, o chat levou 3024 ms e o `/health` ficou parado 3012 ms.
- `pattern: "^(a+)+$"` com saída `"aaaa…!"`: 38 ms com n=20 e 579 ms com n=24, com o `/health` parado em paralelo (a validação é síncrona dentro da rota assíncrona).
- Nesta rodada, o teste do `$ref` remoto sem o filtro ficou pendurado no `urlopen`, sem timeout: o mesmo furo.

Os docs diziam que nenhum campo do pedido escolhe URL ou destino. Isso era falso.

## Decisão

O gateway aceita um subconjunto de JSON Schema (Draft 2020-12), conferido em `preparar_validador` antes de qualquer chamada ao Ollama. Fora do subconjunto: 400 `schema_invalido`, com mensagem fixa que não cita a palavra.

- Palavras-chave permitidas: `type`, `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `minLength`, `maxLength`, `minItems`, `maxItems`, `minimum`, `maximum`, `title` e `description`.
- Qualquer outra chave é recusada: as que começam com `$` (`$ref`, `$defs`, `$schema`, `$id`, `$dynamicRef`), `pattern`, `patternProperties`, `format`, os combinadores (`allOf`, `anyOf`, `oneOf`, `not`, `if`) e também `default` e `examples`.
- A checagem é recursiva sobre os valores de `properties`, o valor de `items` e o de `additionalProperties` quando é objeto. Nomes dentro de `properties`, valores de `enum` e de `const` e itens de `required` são dado, não schema.
- Tetos: 64 nós de schema, profundidade 6 (a raiz é o nível 1), inteiros de 0 a 4096 em `minLength`, `maxLength`, `minItems` e `maxItems`, e no máximo 64 itens em `enum`. Passar de um teto é 400 `schema_invalido`.
- O schema do PHParrot tem 3 nós e profundidade 2, então os tetos cobrem o consumidor com folga. Os tetos numéricos existem porque esses quatro campos vão crus para o Ollama, e o llama.cpp expande repetições limitadas ao montar a gramática. Isso é plausível e não foi medido (não há Ollama neste ambiente).
- Estender a lista é decisão de contrato (docs/api.md): cada palavra nova entra com teste, e a busca remota de `$ref` continua fechada.

## Consequência

- O consumidor manda um schema de objeto simples, e o furo de SSRF e de CPU na validação fica fechado por construção.
- Limite conhecido: o `parse()` do SDK `openai` com modelos Pydantic aninhados gera `$defs` e `$ref`, e é recusado com 400 `schema_invalido`. O mesmo vale para um campo com valor padrão, porque o Pydantic emite `default`. Um `$ref` local pode entrar no futuro, resolvido internamente, sem busca remota, se um consumidor precisar. Isso exige um ADR novo.
- A lista é contrato com o consumidor: um schema que usa uma palavra que sai da lista passa a responder 400. Por isso o OpenAPI publica as palavras em `x-palavras-chave`, e mudar a lista é mudança de minor (`docs/api.md`).
- A mensagem do 400 não ecoa o nome da palavra, porque o nome vem do cliente.
- Não foi medido o `/health` durante um chat com schema depois da correção: o gatilho medido (`$ref` remoto e `pattern`) é recusado antes de qualquer execução.

## Evidência

- `src/llm_gateway/subconjunto.py:5-28` (a lista e os tetos), `:57-86` (a varredura) e `:89-90` (`exigir_subconjunto`). `src/llm_gateway/chat.py:176` (a chamada, antes do `check_schema`).
- `tests/test_subconjunto.py:110` (o schema exato do PHParrot, com `name: "item"` e `strict: true`, chega inteiro ao Ollama), `:123` (cada palavra proibida em quatro posições), `:130` (`$ref` remoto e `ftp://` com zero acessos a um listener de teste), `:148` (`$ref` local e `file://`), `:154` (`pattern`, e uma propriedade chamada `pattern` passa), `:165` e `:178` (nomes, `enum`, `const` e `required` são dado), `:210`, `:219`, `:232` e `:252` (os tetos nos dois lados).

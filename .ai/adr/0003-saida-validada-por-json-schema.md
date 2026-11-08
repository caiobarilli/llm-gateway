# Saída validada por JSON Schema

## Contexto

O Ollama aceita `format` com JSON Schema, mas um modelo de 3B pode devolver texto fora do schema ou cortado. No PHParrot, com `num_predict` baixo, o `done_reason` veio `length` e o JSON saiu cortado e inválido (ADR 0013, `rascunho-ia.md`, rodada 15.5). A saída de um modelo é dado não confiável.

## Decisão

- O schema do `response_format` é validado como schema (`Draft202012Validator.check_schema`, JSON Schema Draft 2020-12). Schema inválido dá 400 `schema_invalido`, antes de chegar ao Ollama.
- O mesmo schema vai ao `format` do Ollama e valida a resposta.
- Resposta que não é JSON ou não segue o schema dá 502 `saida_invalida`. Resposta cortada pelo `max_tokens` dá 502 `saida_truncada`.
- Nenhum desses erros devolve o conteúdo do modelo.
- Uma tentativa só. Tentar de novo é decisão de quem chama.
- Sem `response_format`, a saída não é validada e o `done_reason` vira `finish_reason`.

## Consequência

- O consumidor recebe JSON que segue o schema que ele mandou, ou um erro com `code` estável.
- O gateway não conhece o formato dos dados do consumidor. Validar o conteúdo continua sendo papel dele.
- Os campos `description` e `strict` do schema são aceitos e não são repassados ao Ollama.

## Evidência

- `src/llm_gateway/chat.py:102-112` (`preparar_validador`) e `:132-145` (`conferir_saida`).
- `tests/test_chat.py:202` (schema inválido responde 400) e `:225` (saída fora do schema vira 502 sem o conteúdo).

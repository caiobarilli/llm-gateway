# Um pedido por vez, sem fila

## Contexto

O modelo roda na GPU de um desktop, alcançada por um túnel. No PHParrot, medido em 05/11/2026 (ADR 0013, `rascunho-ia.md`): um texto B2 leva 6,2 s com o modelo carregado, e a carga a frio soma 10,5 s. Uma fila no gateway seria memória e tempo de GPU sem dono, e o consumidor já tem a própria fila.

## Decisão

- O `Limitador` tem `GATEWAY_CONCORRENCIA` vagas. Ele tenta pegar uma vaga sem esperar.
- Sem vaga, a resposta é 503 `ocupado` na hora, com `Retry-After: 10` (`ESPERA_SUGERIDA_EM_SEGUNDOS`). O valor é fixo, não vem de variável.
- A vaga cobre só a chamada ao upstream. Leitura do corpo, validação e formatação ficam fora.
- A vaga volta no `finally`, também depois de erro ou de exceção.
- O consumidor define o número de vagas. O PHParrot usa 1.

## Consequência

- Quem chama trata o 503: espera e tenta de novo. No PHParrot, a agenda roda um pedido por minuto e o Laravel tem o próprio `Cache::lock` (ADR 0013, itens 6 e 12).
- Não existe fila nem prioridade. Fila entra no teto só por decisão do Maintainer.
- A medida de 10 s é o tempo de um texto longo com o modelo carregado. Ela não acompanha o tempo real de cada pedido.

## Evidência

- `src/llm_gateway/concorrencia.py:7` e `:10-38` (o `Limitador`), `src/llm_gateway/chat.py:272-273` (a vaga em volta de `conversar`).
- `tests/test_concorrencia.py:15` (o segundo chat leva 503 na hora), `:65` (a vaga volta com exceção) e `:77` (duas vagas aceitam dois e recusam o terceiro).

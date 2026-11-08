# Log só de métricas

## Contexto

O prompt e a resposta têm texto do usuário e do modelo. O token autoriza o uso da GPU. Nada disso pode ir para um log que alguém vai ler ou arquivar.

## Decisão

- Cada pedido ao chat gera uma linha JSON no stdout, com sucesso ou erro: `modelo`, `status`, `codigo`, `prompt_tokens`, `completion_tokens`, `tokens_por_segundo`, `carga_ms` e `duracao_ms`.
- O `modelo` só é preenchido depois de passar pela allowlist.
- A autenticação registra só o motivo curto da recusa (`sem cabeçalho`, `cabeçalho malformado`, `token errado`) e o tipo do erro (ou `arquivo vazio`, ou `token curto`) quando o arquivo do token falha.
- Nunca entram: prompt, mensagens, resposta, schema, token e cabeçalho `Authorization`.
- O uvicorn sobe com `--no-access-log` e `--no-server-header`.

## Consequência

- Dá para medir uso e latência pelo log, e não dá para depurar o conteúdo de um pedido por ele. É de propósito.
- Campo novo na linha precisa de teste que prove que não leva texto nem segredo.
- O log de inicialização do uvicorn sai em texto, no stderr. A linha JSON é só a do gateway.

## Evidência

- `src/llm_gateway/chat.py:183-191` e `:216-218` (as métricas), `src/llm_gateway/registro.py:10-18` (`FormatoJson`) e `:40-41` (`registrar_metricas`).
- `src/llm_gateway/autenticacao.py:19`, `:23`, `:27` e `:38` (o que a autenticação registra).
- `tests/test_chat.py:305` (uma linha por pedido), `:332` (JSON numa linha só) e `:354` (prompt, resposta, schema e token nunca vão para o log).
- `tests/test_autenticacao.py:131` (o token não aparece no log nem na resposta).
- `Dockerfile:60` (as flags do uvicorn).

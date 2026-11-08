# Log só de métricas

## Contexto

O prompt e a resposta têm texto do usuário e do modelo. O token autoriza o uso da GPU. Nada disso pode ir para um log que alguém vai ler ou arquivar.

## Decisão

- Cada pedido ao chat gera uma linha JSON no stdout, com sucesso ou erro: `modelo`, `status`, `codigo`, `erro`, `prompt_tokens`, `completion_tokens`, `tokens_por_segundo`, `carga_ms` e `duracao_ms`.
- `erro` é só o nome da classe da exceção (`type(erro).__name__`), nunca a mensagem. Só uma exceção que o gateway não previa, dentro da rota do chat, preenche o campo, e a resposta é 500 `erro_interno`. Nos outros pedidos ele é `null`.
- Uma exceção inesperada na rota do chat não escapa para o uvicorn: `completar` a captura e devolve `ErroOpenAI`. Assim o traceback, que traria a mensagem da exceção com o schema ou o prompt do cliente, nunca é impresso.
- O `modelo` só é preenchido depois de passar pela allowlist.
- A autenticação registra só o motivo curto da recusa (`sem cabeçalho`, `cabeçalho malformado`, `token errado`) e o tipo do erro (ou `arquivo vazio`, ou `token curto`) quando o arquivo do token falha.
- Nunca entram: prompt, mensagens, resposta, schema, token e cabeçalho `Authorization`.
- O uvicorn sobe com `--no-access-log` e `--no-server-header`.

## Consequência

- Dá para medir uso e latência pelo log, e não dá para depurar o conteúdo de um pedido por ele. É de propósito.
- Campo novo na linha precisa de teste que prove que não leva texto nem segredo.
- Capturar a exceção apaga o único diagnóstico de um 500: o nome da classe fica no `erro`, e a causa só se acha reproduzindo o pedido.
- Limite conhecido: uma exceção fora de `completar` (por exemplo, na dependência do token) continua com o traceback padrão do uvicorn no stderr. Medido na S1: o Starlette relança a exceção e o uvicorn a imprime.
- O log de inicialização do uvicorn sai em texto, no stderr. A linha JSON é só a do gateway.

## Evidência

- `src/llm_gateway/chat.py:254-264` (as métricas), `:285-291` (os dois `except`) e `:293-295` (o `finally`), `src/llm_gateway/registro.py:10-20` (`FormatoJson`) e `:42-43` (`registrar_metricas`).
- `src/llm_gateway/autenticacao.py:19`, `:23`, `:27` e `:38` (o que a autenticação registra).
- `tests/test_chat.py:404` (uma linha por pedido), `:432` (JSON numa linha só) e `:487` (prompt, resposta, schema e token nunca vão para o log).
- `tests/test_erro_interno.py:49` (o 500 inesperado em três pontos, com valores marcados, sem nada em `out` nem em `err`, a vaga devolvida e `erro` com o nome da classe).
- `tests/test_autenticacao.py:131` (o token não aparece no log nem na resposta).
- `Dockerfile:70` (as flags do uvicorn).

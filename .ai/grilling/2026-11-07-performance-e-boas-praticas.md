# Grilling S4: performance e boas práticas

Alvo: o gateway inteiro em `9db9b3f` (586 linhas em `src/`, 1022 em `tests/` e `tools/`). Trilhas 2 e 3, skills `fastapi-gateway`, `python-313` e `pytest-gateway`.
Método extra: o método do ponytail-audit, lido em `~/code/_ref/ponytail/skills/ponytail-audit/SKILL.md` (clonado só para leitura, nada instalado neste repositório). Foi usado como lente: cada achado é de uma categoria (bug, risco, escala, teste faltando, velocidade, enxuto), tem um caso concreto, a menor correção e o que acontece se não for feito. A convenção de comentário `shortcut:` do método não se aplica: a trava de comentários vale.
Carga assumida: um consumidor (PHParrot), um pedido por vez, geração de 0,5 a cerca de 20 s numa GTX 1650 de 4 GB com `llama3.2:3b` (cerca de 50 tokens/s), carga fria do modelo de cerca de 11 s.
Um revisor cético de robustez e um advogado do consumidor e do código enxuto julgaram os achados, sem ver a opinião um do outro.
Regra de aceite sem o Maintainer: consenso, severidade baixa ou média, dentro do contrato e do teto. O resto fica pendente.
Nada foi implementado.

## O que foi medido

Custo do próprio gateway, em processo, com o Ollama simulado instantâneo e o schema do PHParrot:

| Componente | Custo |
|---|---|
| `ler_token` (arquivo, síncrono) | 5,7 µs |
| `extrair_bearer` e `compare_digest` | 0,4 µs |
| `interpretar` (Pydantic) | 5,1 µs |
| `preparar_validador` (`check_schema`) | **771,4 µs** |
| `montar_corpo` | 1,5 µs |
| `conferir_saida` | 13,1 µs |
| `formatar` | 2,3 µs |
| linha de log JSON | 8,7 µs |
| **pedido inteiro de chat com schema (ASGI)** | **1750 µs** (cerca de 570 por segundo) |
| `/health` (ASGI) | 548 µs |

Contra a geração (27 tokens a 50 tokens/s levam 0,54 s; um texto B2 de 271 tokens leva 6,2 s), o gateway pesa de 0,03% a 0,3% do tempo.
Container (imagem final, 208 MB): partida a frio de 1,22 s (do `docker run` ao primeiro `/health` 200). Memória em repouso entre 40 e 49 MiB. Depois de 1500 pedidos, 40,8 MiB, sem crescimento.
Ressalva da medição: os "17 pedidos por segundo" pela rede vêm do Ollama falso que usei (cerca de 45 ms por resposta, `duracao_ms: 46` na linha de log do próprio gateway), não do gateway. O custo do gateway é o medido em processo.

Toolchain mais estrita, numa cópia descartável:
- `ruff` com `ASYNC`, `PT`, `PERF` e `RET`: 0 achados. Com `PLR2004`: 40; `TRY003`: 15; `ARG001`: 4 (o argumento do tratador em `erros.py:54` e 3 fixtures); `T201`: 4 (os `print` das ferramentas).
- `mypy` com `explicit-override`: exatamente 2 erros (`FormatoJson.format`, `registro.py:11`, e `SaidaPadrao.emit`, `registro.py:21`). `--warn-unreachable`: limpo.
- `pytest -W error`: 94 passed.
- Remover o tratador de `RequestValidationError` (9 linhas de `erros.py`): 94 passed, `ruff` e `mypy` limpos. Nenhuma rota declara parâmetro validado pelo FastAPI.
- Sem o `jsonschema`, o runtime teria 18 pacotes em vez de 23 (saem `jsonschema`, `jsonschema-specifications`, `referencing`, `rpds-py`, `attrs`).

## Decidido pelo Maintainer

Nada novo. Valem F5 (`redirect_slashes`), F6 (lista de palavras-chave do schema), F7 (`except Exception` em `completar`) e F8 (apagar `LIMITE_DO_NOME`).

## Aceito por consenso

### F23 (baixa; boas práticas): o que a toolchain fecha de graça
- Evidência: `.claude/skills/python-313/SKILL.md:65` manda marcar com `typing.override` as subclasses, e `registro.py:11` e `:21` não marcam. O `mypy` com `explicit-override` aponta exatamente esses dois. `pytest -W error` já passa. O aviso do `jsonschema` sobre `$ref` remoto ("will shortly become an error") teria virado falha de teste.
- Lentes: as duas aceitam `@override`, `explicit-override`, `warn_unreachable`, `filterwarnings` e a regra `ASYNC` do `ruff`. As duas rejeitam `PERF`, `RET`, `PLR2004`, `TRY003`, `ARG` e `T20` (ruído, ou estilo que o `mypy --strict` já cobre).
- Proposta:
  - `@override` nos dois métodos de `registro.py`;
  - `enable_error_code = ["explicit-override"]` e `warn_unreachable = true` no `[tool.mypy]`;
  - `filterwarnings = ["error"]` no `[tool.pytest.ini_options]`;
  - `"ASYNC"` no `select` do `ruff`.
- Aceite: `mypy --strict` completo passa depois do `@override` (não só a regra nova), e o gate continua verde.
- Ressalva do cético: a regra `ASYNC` só reconhece uma lista fixa de chamadas bloqueantes (`time.sleep`, `open`, clientes HTTP síncronos, `subprocess`). Não pega o `sys.stdout.write` e o `flush` de `registro.py:23-24`, que rodam dentro da rota assíncrona (custam 8,7 µs, e não vale mexer). Ela não deve ser apresentada como detector de chamada bloqueante.
- Nota: isto toca as regras de lint e de tipos do projeto. Entra no pedido de decisão em lote, mesmo tendo consenso.

### F26 (baixa; escala): o orçamento do timeout de leitura de 60 s
- Conta: 1024 tokens a 50 tokens/s levam 20,5 s; mais a carga fria de 10,5 s, cerca de 31 s contra 60 s (margem de cerca de 1,9 vez). O limite estoura se a velocidade cair abaixo de cerca de 17 tokens/s (1024 dividido por 60). O PHParrot espera 90 s de leitura e 5 s de conexão (`config/phparrot.php:27-28`), então o gateway responde 504 antes de o consumidor desistir.
- Detalhe do cético: o tempo de leitura do `httpx2` (`ollama.py:28`) conta o intervalo entre pedaços da resposta, não o total. Com `stream: false` o Ollama só envia bytes no fim, então na prática ele vira um teto total.
- Proposta: sem código. Um parágrafo em `docs/operacao.md` (tabela de tempos limite) com a conta, o detalhe do intervalo, e a regra de olhar o `tokens_por_segundo` no log (um alerta abaixo de 25 tokens/s deixa o pior caso em cerca de 41 s).
- Como medir: `tokens_por_segundo` já sai na linha de métricas. O tempo de avaliação do prompt não sai (`prompt_eval_duration` não está na linha), então esse trecho fica invisível.

### F27 (baixa; documentação): "sob carga, não testado"
- Evidência: `docs/operacao.md:73` diz que a memória sob carga não foi testada, mas já há medida (acima).
- Proposta: trocar a frase pela medida (40 a 49 MiB em repouso, 40,8 MiB depois de 1500 pedidos, `--memory 128m` com folga de cerca de 3 vezes) e dizer que o upstream era falso e que a duração dos pedidos não era a real.

### F25 (média; velocidade), a parte do gateway: não mexer no código
- Achado: a carga fria do modelo (cerca de 11 s) volta depois de cerca de 5 minutos parado, e o gateway não manda `keep_alive`.
- Evidência: `montar_corpo` (`chat.py:115-129`) envia `model`, `messages`, `stream`, `options` e `format`. `carga_ms` na linha de métricas mede exatamente a carga. O ADR 0013 do PHParrot (linha 21) decidiu "o `keep_alive` padrão" e deixa a política da GPU compartilhada em aberto. A geração é feita pela agenda (`routes/console.php:15` do PHParrot), sem ninguém esperando, e 11 s cabem nos 90 s do consumidor: é lentidão, não erro.
- Lentes: as duas escolhem a mesma opção para o gateway: nenhuma mudança de código. Um `keep_alive` mandado no pedido sobrepõe a configuração do Ollama e passaria a mandar na política de uma GPU de 4 GB compartilhada. Uma variável opcional `GATEWAY_KEEP_ALIVE` seria a quinta variável, quando as quatro atuais são todas obrigatórias e sem padrão.
- Proposta para o gateway: nada. A decisão sobre o host está em "Pendente".

## Rejeitado por consenso

### F24 (média): trocar o `jsonschema` por um validador próprio do subconjunto
As duas lentes rejeitam. O ganho principal (fechar a busca remota de `$ref`) já vem da F6. Sobrariam 5 pacotes e 771 µs, cerca de 0,14% de um pedido de 0,5 s. O custo é código próprio com as armadilhas que são exatamente o que o `jsonschema` já resolve (`bool` contado como `int`, `1 == True` em `enum`, `3.0` aceito como `integer`, comprimento em pontos de código), mais um verificador de schema próprio (o `check_schema` faz isso hoje, e as 50 a 60 linhas estimadas não o incluem), testes para cada armadilha e a reescrita do ADR 0003. `types-jsonschema` (dev) também sairia. Mantém-se o `jsonschema` e a lista da F6.

### Não-achados
Concordados pelas duas lentes: não cachear o `Draft202012Validator` (economiza cerca de 0,77 ms de pedidos de 0,5 a 20 s); não usar mais workers do uvicorn (a concorrência é 1 por decisão, ADR 0002); manter `Limitador.ocupadas` (os testes provam a devolução da vaga com ele); manter `EsquemaJson.strict` e `description` aceitos e não lidos (compatibilidade com o SDK). A reutilização de conexão com o Ollama pelo túnel fica como hipótese, fora dos achados, até haver medida: o padrão do cliente HTTP mantém a conexão por 5 s e a agenda envia um pedido por minuto, então cada chamada abre uma conexão nova, o que custa milissegundos.

## Pendente do Maintainer

### P9. F22 (baixa): apagar o tratador de `RequestValidationError` ou mantê-lo com um teste
- Evidência: o tratador (`erros.py:47-51`, registrado em `:62`) hoje não dispara: nenhuma rota declara parâmetro validado. Removê-lo mantém os 94 testes e o `ruff` e o `mypy` limpos (9 linhas a menos).
- Advogado: apagar. Fica um tratador sem teste e sem caminho de execução, para ser lido e mantido, e quem criar a rota vai ver o 422 no primeiro teste.
- Cético: manter. Sem ele, quem responde é o tratador padrão do FastAPI, e o erro sai fora do contrato.
- Medido para resolver o fato: numa rota de teste com um parâmetro `int`, o gateway com o tratador responde `400 {"error": {"message": "Pedido inválido.", …, "code": "invalid_request"}}`. Com o tratador padrão do FastAPI, responde `422 {"detail": [{"type": "int_parsing", "loc": ["query","n"], …, "input": "VALOR_SECRETO_DO_CLIENTE"}]}`. O 422 devolve ao cliente o valor que ele mandou (`input`), o que contraria "todo erro é `ErroOpenAI`" e "sem eco do conteúdo do pedido" (`fastapi-gateway` §4). A skill §2 manda escrever dependência nova com `Annotated[T, Depends(...)]`, o caminho natural para entrar um parâmetro tipado.
- Recomendação: manter as 9 linhas e acrescentar um teste que pendure no app de `criar_app()` uma rota com parâmetro `int` e confira o 400 `invalid_request` sem `detail`. O motivo é que o tratador é uma garantia de formato e de não-eco, e o custo é um teste. A morte do código hoje não é o que importa: o que importa é a primeira rota tipada.

### P10. F25 (média): a política de `keep_alive` no Ollama
- O gateway não muda. A decisão é do dono do host da GPU, fora deste repositório.
- Opção das duas lentes: `OLLAMA_KEEP_ALIVE` no servidor do Ollama, que é onde mora a política da GPU, e registrar a decisão no ADR 0013 do PHParrot. O cético acrescenta que o ADR 0013 lista `OLLAMA_NUM_PARALLEL` e `OLLAMA_MAX_LOADED_MODELS` junto com `keep_alive`: decidir só uma das três pode estourar os 4 GB de VRAM quando outro modelo pedir a GPU.
- Como medir antes e depois: enviar um pedido, esperar 6 minutos, enviar outro e ler o `carga_ms` da linha de métricas. Antes, cerca de 11000 ms. Depois, esperado abaixo de 200 ms. Não testado aqui: não há Ollama neste ambiente.
- Recomendação: o Maintainer decide `OLLAMA_KEEP_ALIVE` no host junto com as outras duas variáveis. Se não puder mexer no host, a alternativa é uma variável opcional `GATEWAY_KEEP_ALIVE`, ausente significando "não enviar o campo", e nunca um valor fixo no código.

### P11. A regra `PT` do `ruff`
Cético: sim (`PT011` e `PT012` pegam `pytest.raises` largo demais; 0 achados hoje). Advogado: não (só alonga o `select`). Custo zero hoje. Recomendação: sim, uma palavra no `select`.

## Hipóteses refutadas

- `Content-Length` não numérico (`"²".isdigit()` é verdadeiro e `int("²")` falha) causaria 500: refutada. O `h11` do uvicorn responde `400` (`Invalid HTTP request received`) antes de a aplicação ver o cabeçalho, para `\xb2` e para dígitos em UTF-8.
- "O gateway é o gargalo": refutada pelas medidas (de 0,03% a 0,3% do tempo de geração).

## Hipóteses não testadas

- Efeito de `keep_alive` e das outras duas variáveis do Ollama na VRAM compartilhada: não há Ollama aqui.
- O tempo de avaliação do prompt (`prompt_eval_duration`): não aparece na linha de métricas, então não foi medido.
- Memória com payloads reais (8000 caracteres e 1024 tokens): a medida usou um upstream falso com respostas pequenas.
- Reutilização de conexão com o Ollama pelo túnel SSH.
- O custo de nova conexão a cada pedido espaçado (estimado em milissegundos, não medido).

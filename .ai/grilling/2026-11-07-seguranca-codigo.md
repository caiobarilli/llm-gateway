# Grilling S1: segurança, código e contrato

Alvo: o gateway inteiro em `9db9b3f`. Trilha 1, skill `api-security`.
Método: o Maintainer decidiu F1 a F6 numa conversa de uma pergunta por vez. Para os achados novos (F7 a F10 e F6b), dois revisores somente leitura opinaram com lentes opostas: um revisor de segurança cético e um advogado do consumidor (PHParrot, simplicidade, manutenção). Cada um viu os mesmos fatos medidos e não viu a opinião do outro.
Regra de aceite sem o Maintainer: consenso das duas lentes, severidade baixa ou média, dentro do contrato e do teto. O resto fica pendente.
Nada foi implementado.

## Decidido pelo Maintainer

### F1 (baixa): o 400 ecoa nomes de campo vindos do cliente
- Evidência: `chat.py:90-91` junta até 5 caminhos de campo, com até 40 caracteres cada. Medido: um campo extra `x\ny"z<script>` volta na mensagem. A mensagem não vai para o log, e o PHParrot lê só `error.code` (`GeradorGateway.php:135-140`).
- Decisão: caminho de campo conhecido do schema continua no eco. Campo desconhecido mostra só o caminho até ele e "campo não permitido", sem o nome inventado. A regra da skill passa a "nunca valores nem nomes vindos do cliente; só caminhos do schema".
- Aceite: teste de que nome inventado e valor nunca aparecem na mensagem, e o teto de 5 continua.
- Nota de implementação: só o erro `extra_forbidden` carrega nome inventado no `loc`.

### F2 (baixa): identidade de outro projeto no contrato e nos testes
- Evidência: `modelos.py:22` (`owned_by: "phparrot"`), `app.py:37` e `docs/openapi.json:181` (`title`), `tests/test_config.py:8` e `:19` (caminho do segredo do consumidor). O PHParrot não chama `/v1/models`. Os loggers `gateway.*` não aparecem em nenhuma saída, mas o handler está preso a `RAIZ = "gateway"`: um logger `llm_gateway.chat` perde a linha em silêncio (testado).
- Decisão: um PR único, antes da `v0.1.0`. `title` e `owned_by` viram `"llm-gateway"`. `RAIZ = "llm_gateway"` e os loggers via `getLogger(__name__)`. O caminho do segredo nos testes vira `/run/secrets/llm-gateway-token`. README e `docs/` continuam citando o PHParrot como consumidor de referência.
- Aceite: `grep -rni phparrot src tests tools Dockerfile pyproject.toml .github` sem resultado, teste de que um logger `llm_gateway.*` chega ao stdout, `openapi.json` regenerado, ADR 0007 corrigido.

### F3 (baixa): as skills descrevem recursos que não existem
- Evidência: MCP (`fastapi-gateway:83-96`, `api-security:22,31,63,65,85`), teste do MCP, SDK `openai` e cobertura (`pytest-gateway:54-67`), Dependabot, Trivy, SBOM, `pip-audit` e CodeQL (`api-security:78-81`).
- Decisão: `(alvo)` em cada item, uma linha de legenda no topo de cada skill e `(alvo, exige ADR)` no MCP. Sem PR: um commit só de texto, no mesmo branch do F2. Quem entregar o item remove a marca no mesmo commit.

### F4 (média): o gateway aceita token de qualquer tamanho
- Evidência: `autenticacao.py:21-23` só recusa vazio. Medido: token de 1 caractere dá `200`. O PHParrot gera 64 caracteres (`openssl rand -hex 32`, `docs/configuracao.md:116` dele), mas o gateway não garante isso.
- Decisão: token com menos de 32 caracteres (depois do `strip`) dá 503 `token_indisponivel`, fail-closed, com o motivo `token curto` no log e sem o valor. Sem limite de tentativas. Os exemplos do README e de `docs/` passam a usar um fictício de 32 ou mais.
- Aceite: testes com 31 caracteres (503) e 32 (200), mais a prova de que o motivo sai no log sem o token. `docs/seguranca.md` e `docs/operacao.md` dizem como gerar (`openssl rand -hex 32`).

### F5 (baixa): barra final redireciona com `Location` montado pelo `Host`
- Evidência: `GET /health/` dá `307`; com `Host: evil.example`, `location: http://evil.example/health`. `app.py:37` não desliga o `redirect_slashes`. O PHParrot chama sem barra (`GeradorDeTextosTest.php:24`).
- Decisão: `redirect_slashes=False`. A barra final vira `404 not_found` no formato da OpenAI, sem `Location`. Entra junto com o F2.
- Aceite: testes para `/health/` e `/v1/models/`, e o `openapi.json` não muda.

### F6 (alta): o schema do cliente é executado pelo gateway
- Evidência medida, com o Ollama simulado:
  - `{"$ref": "http://127.0.0.1:PORTA/segredo-interno"}`: o servidor interno de teste recebeu `GET /segredo-interno`.
  - O mesmo `$ref` com o servidor demorando 3 s: o chat levou 3024 ms e o `/health` ficou parado 3012 ms (linha de base 53 ms).
  - `$ref` quebrado: `500 erro_interno` depois da resposta do Ollama (`upstream_chamado=1`).
  - `pattern: "^(a+)+$"` com saída `"aaaa…!"`: 38 ms com n=20, 579 ms com n=24. O `/health` em paralelo levou 482 ms.
  - Causa: `jsonschema` 4.26.0 busca `$ref` remoto com `urlopen(request)`, sem timeout (`validators.py`, `_warn_for_remote_retrieve`). A validação é síncrona dentro de `async def completar` (`chat.py:144`, `:208`).
  - Os docs dizem o contrário: `docs/seguranca.md` (API7) e o README afirmam que nenhum campo do pedido escolhe URL ou destino. Isso é falso e entra na correção.
- Decisão (aprovada pelo Maintainer): lista de palavras-chave permitidas, validada em `preparar_validador` antes de qualquer chamada ao Ollama. Fora da lista: 400 `schema_invalido`.
  - Permitidas: `type`, `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `minLength`, `maxLength`, `minItems`, `maxItems`, `minimum`, `maximum`, `title`, `description`.
  - Fora: qualquer chave `$…`, `pattern`, `patternProperties`, `format` e os combinadores.
  - A checagem é recursiva (valores de `properties`, `items`, `additionalProperties` quando objeto). Nomes dentro de `properties` são nomes de campo, não palavras-chave.
  - Teto explícito de profundidade e de nós, com teste (valores em F6b).
  - ADR 0009 registra a lista e diz que estendê-la é decisão de contrato: cada palavra nova entra com teste, e a busca remota continua fechada.
  - Docs: corrigir `docs/seguranca.md` (API7) e o README, e passar a dizer "subconjunto de JSON Schema", com a lista.
- Aceite: `$ref` remoto, local, `file://` e `ftp://` dão 400, sem chamar o upstream e com zero acessos num servidor de teste. `pattern` dá 400. Uma propriedade chamada `pattern` continua valendo. O schema de `PromptDeItem.php:36-47` continua passando. O `/health` não sofre atraso medido durante um chat com schema.
- Acréscimos das lentes, que ficam como critério de aceite (ver F6b para o que ainda é decisão):
  - Um teste usa o schema exato do `PromptDeItem::esquema()` com `name: "item"` e `strict: true` (`GeradorGateway.php:83`), para a lista não quebrar o PHParrot em silêncio. O PHParrot trata 400 como `PedidoRecusado`, sem nova tentativa.
  - A recursão não trata dado como schema: nomes em `properties`, valores de `enum` e `const`, itens de `required`. Teste para cada um.
  - O schema vai inteiro para o `format` do Ollama (`chat.py:127`). A lista de palavras-chave é, portanto, contrato com o consumidor e vai em `docs/api.md` e no ADR 0003.

## Aceito por consenso

### F7 (média): um 500 inesperado escreve o schema do cliente no stderr
- Achado: o caminho de erro inesperado imprime um traceback em texto puro, com a mensagem da exceção.
- Evidência: com `$ref: "#/$defs/REF_DO_CLIENTE"`, o gateway real respondeu 500 e o stderr trouxe `PointerToNowhere: '/$defs/REF_DO_CLIENTE' does not exist within {'$ref': '#/$defs/REF_DO_CLIENTE'}`, o schema do cliente. Prompt e token não apareceram. `erros.py:54-55` devolve o 500, mas o Starlette relança a exceção e o uvicorn imprime o traceback. O `except` de `chat.py:212` só pega `ErroOpenAI`. A linha de métricas sai com `"status": 500, "codigo": null`. O ADR 0004 diz "nunca schema". Nenhum teste cobre esse caminho.
- Lentes: cético, ajustar, média. Advogado, ajustar, baixa (o gatilho medido some com a F6). Convergem na correção mínima.
- Severidade registrada: média (a mais alta das duas). O furo continua para qualquer exceção cuja mensagem leve dado do pedido.
- Proposta: em `completar`, um `except Exception` depois do `except ErroOpenAI`, que preenche `codigo = "erro_interno"` na linha de métricas que já existe e levanta `ErroOpenAI(500, …, "erro_interno")`. O `with limitador.vaga()` continua devolvendo a vaga. O contrato não muda: o PHParrot já trata 500 como `GeradorIndisponivel` (`GeradorGateway.php:100`).
- Aceite: teste com o `TestClient` padrão (`raise_server_exceptions=True`), que injeta uma falha no upstream ou no validador, com valores marcados (schema, prompt, token). O teste confere `capfd` em `out` e `err`: se a exceção escapar, o teste quebra, e isso prova que nada chegou ao uvicorn. Olhar só o `caplog` não prova.
- Limite conhecido: exceções fora de `completar` (por exemplo, na dependência do token) continuam com o traceback padrão do uvicorn.
- Custo que nenhuma lente apontou: capturar a exceção apaga o único diagnóstico de um 500 em produção. A decisão sobre o campo que o devolve está em "Pendente".

### F8 (baixa): código morto e doc imprecisa no nome do modelo
- Evidência: `Pedido.model` tem `max_length=100` (`chat.py:60`). Testado com 300 caracteres: `400 invalid_request`. O corte `modelo[:LIMITE_DO_NOME]` de `modelos.py:13` nunca corta nada. `docs/api.md:135` e `docs/seguranca.md:45` descrevem o corte.
- Lentes: advogado, aceitar. Cético, ajustar (usar uma constante só e corrigir também `docs/configuracao.md:37`). Compatíveis.
- Proposta: `Field(max_length=LIMITE_DO_NOME)` em `Pedido`, apagar o fatiamento, e corrigir os três docs: modelo com mais de 100 caracteres dá 400 `invalid_request`.

## Rejeitado por consenso (informativo)

- **F9, recusas de autenticação sem origem.** O evento não leva IP. As duas lentes rejeitam: atrás do Docker o `request.client.host` seria o IP da bridge ou do PHParrot, dado de rede no log contraria o ADR 0004, e com a F4 adivinhar o token não é risco real. Se um dia houver exposição direta, abrir um ADR.
- **F10, ordem da autenticação revela o estado do servidor.** `exigir_token` lê o arquivo antes do cabeçalho (`autenticacao.py:54-57`). As duas lentes rejeitam: quem manda `Authorization: Bearer x` ainda força a leitura e ainda recebe 503, então reordenar é cosmético, e o 503 fail-closed do ADR 0008 é um sinal útil ao operador.

## Pendente do Maintainer

### P1. F6b (alta): valores dos tetos do schema
- Medido: o schema do PHParrot tem 3 nós de schema e profundidade 2 (raiz = nível 1).
- Proposta original: profundidade máxima 6 e 64 nós, mais o corpo de 64 KiB que já existe.
- Advogado: um contador só, de 64 nós, que aborta durante a recursão. A profundidade é um segundo número a manter, sem risco extra, porque o Pydantic já barra aninhamento absurdo (1000 e 5000 níveis deram 400). Os dois números são aceitáveis, mas o segundo é opcional.
- Cético: 64 nós e profundidade 6 cobrem o consumidor com folga. Acrescenta que `minLength`, `maxLength`, `minItems` e `maxItems` vão crus para o Ollama em `format` (`chat.py:127`), e que a conversão do schema para gramática no llama.cpp expande repetições limitadas, então `minLength: 10000000` pode custar CPU e memória no upstream. Pede inteiros de 0 a 4096 nesses quatro campos e no máximo 64 itens em `enum`. O PHParrot usa `maxLength: 2000`, abaixo do teto.
- Pergunta: um contador só (64 nós) ou os dois (64 nós e profundidade 6)? E os tetos numéricos de 0 a 4096 e de 64 itens em `enum` entram agora ou ficam para quando houver medida? Recomendação: os dois contadores e os tetos numéricos entram na mesma PR da F6, porque o custo é uma comparação por palavra-chave e fecha o furo antes da `v0.1.0`.

### P2. F7: campo com o tipo da exceção na linha de métricas
- Sem esse campo, um 500 vira só `codigo: "erro_interno"` e o operador não sabe a causa. O traceback some, e era o único diagnóstico.
- Advogado: logar `type(erro).__name__` (por exemplo `PointerToNowhere`).
- Cético: não criar campo novo sem necessidade, porque campo novo exige teste (ADR 0004) e a linha muda de contrato. Se entrar, com teste.
- Pergunta: acrescentar o campo `erro` (só o nome da classe, nunca a mensagem) à linha de métricas? Recomendação: sim. O nome da classe não carrega dado do pedido, o teste do F7 já existe e é pequeno, e sem ele a causa de um 500 em produção fica invisível. Atualizar `docs/operacao.md` e o ADR 0004.

## Hipóteses refutadas

- Saída do modelo com 6000 `[` abertos e schema plano: `502 saida_invalida`. O `json.loads` não estoura a recursão.
- Schema aninhado com 1000 e 5000 níveis: `400 invalid_request`, upstream não chamado. O Pydantic já barra.
- O nome do logger vaza no contrato: não. O `FormatoJson` só emite `nivel`, `evento` e as métricas (`registro.py:12`).

## Hipóteses não testadas

- Resposta do upstream sem teto de tamanho: `resposta.content` é lido inteiro (`ollama.py:48-49`). As duas lentes concordam em tratar o upstream como de confiança, e a saída já vem limitada por `num_predict` até 1024. Não testado com uma resposta grande.
- Cabeçalho HTTP de 70 KB passou com `200` no uvicorn (`h11`). Onde corta e o custo em memória não foram medidos. As duas lentes não veem razão para gastar código agora, porque o gateway não é exposto.
- Expansão de gramática do llama.cpp para `minLength` e `maxLength` muito grandes (P1): plausível e barata de fechar, mas não medida, porque não há Ollama neste ambiente.
- Taxa real de respostas 401 por segundo pela rede: o custo por pedido é o que mostra o código, não uma medida.

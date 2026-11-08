---
name: fastapi-gateway
description: Padrões do FastAPI no llm-gateway — app criado pela factory criar_app, estado em app.state, router /v1 com o token como dependência, erros sempre no formato da OpenAI, cliente httpx assíncrono para o Ollama, limites de corpo e de tokens, métricas sem texto e o servidor MCP escrito à mão. Use ao criar ou mudar rota, dependência, tratamento de erro, chamada ao upstream ou ferramenta MCP.
---

# FastAPI no llm-gateway

Itens marcados com `(alvo)` ainda não existem no repositório. Quem entregar o item remove a marca no mesmo commit.

O gateway é um proxy pequeno e fechado entre um app e um modelo local. Cada
regra abaixo existe para que ele continue pequeno e fechado.

## 1. Uma factory, nenhum global

- O app nasce em `criar_app(config, transporte)` (`src/llm_gateway/app.py`).
  O uvicorn sobe com `--factory llm_gateway.app:criar_app`.
- Estado compartilhado vai em `app.state`: `config`, `limitador`,
  `cliente_ollama`. Nada de variável de módulo mutável.
- `transporte` existe para os testes injetarem um `httpx2.MockTransport`.
  Não crie outro jeito de trocar o upstream.
- O cliente HTTP abre na factory e fecha no `lifespan` (`ciclo`).

## 2. Rotas

- Tudo que é API fica no `APIRouter(prefix="/v1", dependencies=[Depends(exigir_token)])`.
  Rota nova em `/v1` herda o token; rota fora de `/v1` é pública e precisa de
  motivo num ADR (hoje só `/health`).
- Dependência nova: `Annotated[T, Depends(funcao)]`, como recomenda a skill
  oficial do FastAPI. Não reescreva as existentes só para isso.
- Prefira o tipo de retorno a `response_model`. Use `response_model` só se o
  esquema público for diferente do valor interno.
- `/docs`, `/redoc` e `/openapi.json` ficam desligados em runtime
  (`docs_url=None, redoc_url=None, openapi_url=None`). O OpenAPI é publicado
  como arquivo em `docs/`, gerado a partir da factory.
- `redirect_slashes=False`: barra final é 404, nunca um `Location` montado pelo
  cabeçalho `Host`.

## 3. Entrada: tudo tem limite

- O corpo é lido com teto (`LIMITE_DO_CORPO`, 64 KiB) antes de virar JSON; acima
  disso, 413 `corpo_grande_demais`.
- Modelos Pydantic de entrada usam `ConfigDict(extra="forbid")` e `Field` com
  limite em todo texto e lista (`max_length`, `le`). Campo novo sem limite é
  recusado na revisão.
- O modelo pedido passa por `exigir_modelo_permitido` antes de qualquer coisa
  chegar ao Ollama. O nome tem até 100 caracteres (`LIMITE_DO_NOME`, 400
  acima disso). Fora da allowlist: 404 `model_not_found`.
- `stream: true` não é suportado: recusa clara, não meia implementação.
- O schema do `response_format` passa por `exigir_subconjunto` antes do
  `check_schema`. Palavra-chave nova na lista é decisão de contrato, com teste
  (ADR 0009).

## 4. Erros no formato da OpenAI

- Todo erro sai como `ErroOpenAI(status, mensagem, tipo, codigo, cabecalhos)`
  e é convertido em `registrar_tratadores` (`erros.py`). Nunca devolva
  `HTTPException` crua nem traceback.
- Mensagens em português, curtas, sem eco do conteúdo do pedido, do token ou
  da resposta do modelo. Nunca valores nem nomes vindos do cliente: só
  caminhos do schema. Campo desconhecido é `<caminho do pai> (campo não
  permitido)`. A exceção documentada é o `model_not_found`, que cita o nome
  do modelo (até 100 caracteres).
- Códigos estáveis (`invalid_api_key`, `model_not_found`, `ocupado`,
  `saida_invalida`, `upstream_timeout`…): o PHParrot traduz por eles. Mudar um
  código é mudança de contrato.

## 5. Upstream (Ollama)

- Só `POST /api/chat`, com `stream: false`, `format` (o schema) e `num_ctx`
  fixo. O gateway não chama nenhuma outra rota do Ollama: baixar, apagar ou
  listar modelos é papel do PHPorto.
- Tempo de conexão 5 s, leitura 60 s, `follow_redirects=False`.
- Falha de rede vira 503 `upstream_indisponivel`; tempo esgotado, 504;
  status diferente de 200 ou corpo fora do esperado, 502. O texto do upstream
  nunca é repassado.
- A saída do modelo é dado não confiável: com schema, ela é validada
  (`Draft202012Validator`) e, se não bater, 502 `saida_invalida`.

## 6. Concorrência

- O `Limitador` tenta pegar uma vaga sem esperar. Cheio: 503 `ocupado` com
  `Retry-After`. Não existe fila, por decisão (ADR).
- A vaga envolve só a chamada ao upstream; validação e formatação ficam fora.

## 7. Métricas sem texto

- Cada pedido ao chat gera uma linha JSON pelo `registrar_metricas`, sucesso ou
  erro: modelo, status, código, erro (só o nome da classe da exceção), tokens,
  tokens por segundo, carga e duração.
- Exceção inesperada dentro de `completar` vira `ErroOpenAI` 500
  `erro_interno`: nunca deixe o traceback chegar ao uvicorn.
- Nunca entram: prompt, resposta, schema, token, cabeçalho de autorização.
  Há teste que prova isso; campo novo na linha precisa de teste também.
- `--no-access-log` e `--no-server-header` no uvicorn continuam.

## 8. MCP (FastMCP) (alvo, exige ADR)

O servidor MCP é escrito à mão, não convertido da API
(`FastMCP.from_fastapi` fica proibido: a própria documentação do FastMCP o
indica só para protótipo).

- Montado em `/mcp` no mesmo app, transporte Streamable HTTP, desligado por
  padrão (`GATEWAY_MCP=false`).
- Duas ferramentas: `gerar_texto` e `listar_modelos`. Nenhuma ferramenta
  administrativa e nenhum repasse direto ao Ollama.
- As mesmas travas do HTTP: o mesmo token, a mesma allowlist, o mesmo
  `Limitador`, os mesmos limites de entrada e a mesma linha de métricas sem
  texto. A ferramenta chama as mesmas funções do chat; não duplica regra.
- FastMCP com versão exata no `pyproject.toml` e no `uv.lock`.

## Checklist de revisão

- [ ] Rota nova está em `/v1` ou tem ADR dizendo por que é pública.
- [ ] Todo campo de entrada tem limite e `extra="forbid"`.
- [ ] Todo erro é `ErroOpenAI` com código estável.
- [ ] Nada do pedido ou da resposta aparece em log ou mensagem de erro, nem
      valor nem nome de campo inventado pelo cliente.
- [ ] O upstream só recebe `/api/chat`.

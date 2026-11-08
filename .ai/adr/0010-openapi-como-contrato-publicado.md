# O `openapi.json` é o contrato publicado

## Contexto

O consumidor monta as respostas do gateway à mão nos testes dele. Medido na S5 do grilling (`.ai/grilling/2026-11-07-desacoplar-do-phparrot.md`): o `docs/openapi.json` declarava para o chat só um `200` com schema vazio. Não havia resposta de erro, schema de erro, enum de `code` nem `Retry-After`. A versão (`info.version`) era o padrão do FastAPI e não acompanhava o pacote. Nenhum teste guardava o arquivo: `gerar()` e o arquivo publicado podiam divergir sem o gate perceber.

## Decisão

- O arquivo é gerado pela factory (`tools/exportar_openapi.py`) e cada resposta vem de um modelo Pydantic, o mesmo que monta a resposta real:
  - `RespostaDoChat` (200 do chat), `ListaDeModelos` (200 de `/v1/models`) e `Saude` (`/health`);
  - `CorpoDeErro` com `DetalheDoErro`, e o `code` é o enum `Codigo` (`StrEnum`). Todo `ErroOpenAI` recebe um membro de `Codigo`, e o mypy recusa uma string solta. Código novo entra no enum e no `docs/api.md`.
- Cada rota declara os status que pode devolver (`responses`). O 503 do chat traz o cabeçalho `Retry-After` (só vem com o `code` `ocupado`), e o 401 traz `WWW-Authenticate`. As respostas comuns do `/v1` (401, 500 e 503 `token_indisponivel`) ficam no router.
- `info.version` é `importlib.metadata.version("llm-gateway")`, a versão do `pyproject.toml`.
- O schema do pedido carrega `x-palavras-chave`, a lista do subconjunto de JSON Schema (ADR 0009), e a descrição dos tetos.
- `tests/test_openapi.py` fixa `gerar() == docs/openapi.json`, e o estágio `teste` do Dockerfile copia só esse arquivo (`COPY docs/openapi.json`). Quem muda rota, modelo, limite ou código regenera o arquivo no mesmo commit, ou o gate falha. O mesmo arquivo de testes afirma os pontos que o consumidor lê: `choices[0].message.content`, `error.code` e o `Retry-After` do 503.
- A imagem carrega o arquivo em `/app/openapi.json` (`.ai/adr/0011`). O consumidor extrai o arquivo da imagem que fixou por digest e afirma só o que usa. Não existe terceira cópia para atualizar à mão.
- Regra de versão enquanto a versão é `0.y`: sobe o minor para qualquer mudança de contrato, e o patch é seguro (`docs/api.md`).

## Consequência

- O contrato mudou? O diff de `docs/openapi.json` aparece no PR. É o ponto de revisão.
- O arquivo não valida o formato do pedido além do que o Pydantic declara. O corpo do chat é lido cru (para ter o teto de 64 KiB), então o `requestBody` vem do `Pedido` acrescentado pelo exportador.
- O enum de `code` vale para todos os status, e a descrição de cada status diz quais códigos cabem nele. O enum não amarra status a código.
- Um `code` novo num caminho existente é mudança de contrato: o PHParrot trata `code` fora da lista como `desconhecido`.

## Evidência

- `src/llm_gateway/erros.py:13-31` (`Codigo`), `:34-42` (`DetalheDoErro` e `CorpoDeErro`). `src/llm_gateway/contrato.py:16-28` (as respostas comuns). `src/llm_gateway/chat.py:58-65` (`RespostaDoChat`) e `:67-82` (`RESPOSTAS_DO_CHAT`). `src/llm_gateway/app.py:20` e `:47` (o router e a versão).
- `tests/test_openapi.py:20` (o arquivo publicado é o que a factory gera) e as demais asserções do arquivo.
- `Dockerfile:34` (`COPY docs/openapi.json` no estágio `teste`) e `:59` (o arquivo em `/app/openapi.json` na imagem final).

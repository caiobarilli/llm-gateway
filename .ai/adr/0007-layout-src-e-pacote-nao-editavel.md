# Layout `src/llm_gateway` e pacote não editável na imagem

## Contexto

O pacote se chamava `gateway` e vivia em `docker/gateway/` do PHParrot. O nome estava no `Dockerfile` (`COPY gateway ./gateway` e `--factory gateway.app:criar_app`) e em 30 linhas `from gateway.`. Com os módulos soltos na raiz do repositório, o import não resolve (`.ai/pitfalls.md`).

## Decisão

- O pacote mora em `src/llm_gateway/`, e os testes em `tests/`. Os imports são absolutos: `from llm_gateway.config import Config`.
- O `pyproject.toml` declara o backend `uv_build`, e o projeto é instalável.
- Na imagem, o estágio `dependencias` instala só as dependências (`--no-install-project`). O estágio `construcao` copia `src/` e instala o pacote não editável (`--no-editable`). A imagem final copia só o `.venv`.
- No estágio `teste`, o pacote entra editável e os testes importam `llm_gateway`.
- O uvicorn sobe com `--factory llm_gateway.app:criar_app`.

## Consequência

- A imagem final não leva `src/`. Medido: `llm_gateway.__file__` aponta para `/app/.venv/lib/python3.13/site-packages/llm_gateway/__init__.py`, e `/app/src` não existe.
- Erro de empacotamento aparece no build da imagem, não em produção.
- Renomear o pacote exige mexer no `Dockerfile`, no `pyproject.toml` e nos imports.
- Os loggers vêm de `logging.getLogger(__name__)` e o handler fica em `RAIZ = "llm_gateway"`. Um logger fora de `llm_gateway.*` perde a linha em silêncio, e o teste prova o caso.

## Evidência

- `pyproject.toml:1-3`, `Dockerfile:19`, `:23-25`, `:58` (`COPY --from=construcao`) e `:70`.
- `src/llm_gateway/app.py:7` (import absoluto), `src/llm_gateway/registro.py:6` (`RAIZ`), `src/llm_gateway/chat.py:21` e `src/llm_gateway/autenticacao.py:9` (`getLogger(__name__)`).
- `tests/test_registro.py:10` (um logger `llm_gateway.*` chega ao stdout) e `:18` (um logger de fora não chega).
- PHParrot, em `864751c`: `docker/gateway/Dockerfile:25`, `:40` e `:51`.

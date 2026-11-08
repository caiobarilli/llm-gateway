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
- Os nomes de logger (`gateway.chat`, `gateway.autenticacao`, `RAIZ = "gateway"`) são texto fixo e não seguem o nome do pacote.

## Evidência

- `pyproject.toml:1-3`, `Dockerfile:19`, `:23-25`, `:49` (`COPY --from=construcao`) e `:60`.
- `src/llm_gateway/app.py:7` (import absoluto), `src/llm_gateway/registro.py:6` e `src/llm_gateway/chat.py:21` (os nomes de logger).
- PHParrot, em `864751c`: `docker/gateway/Dockerfile:25`, `:40` e `:51`.

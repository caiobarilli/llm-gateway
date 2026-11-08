# uv, versões exatas, lock, digest e Python 3.13

## Contexto

O mesmo build precisa dar a mesma imagem. O Dependabot do PHParrot subiu o Python do gateway da 3.13 para a 3.15 num PR de `semver-minor`, e o ajuste foi travar a 3.13 (`.ai/pitfalls.md`). A imagem base do Python traz o `pip`, que não é usado em execução.

## Decisão

- O `uv` é a única ferramenta de ambiente: `uv sync --frozen`, `uv run`.
- Dependências com versão exata no `pyproject.toml`, e o `uv.lock` versionado, com hashes.
- Imagens base por tag e digest: `uv` 0.13.7 e `python:3.13.18-slim`.
- `requires-python = "==3.13.*"`. Subir o minor do Python é uma rodada própria: `requires-python`, `uv.lock`, mypy e o estágio `teste`.
- O backend de build é o `uv_build`, na mesma versão do `uv` da imagem.
- A imagem final sai sem o `pip`. O ADR 0013 do PHParrot registra que o `pip` da base traz CVEs HIGH no `_vendor`. Isso não foi reverificado aqui.
- O ruff ignora só o `N818` (sufixo `Error` em exceção), porque os nomes são em português.

## Consequência

- Atualizar uma dependência é um PR que muda o `pyproject.toml` e o `uv.lock` juntos.
- Sem `uv` local, o lock se gera numa imagem descartável (`docs/desenvolvimento.md`).
- Este repositório não tem `.github/dependabot.yml`. Se ele for criado, o bloco de `docker` precisa ignorar `semver-minor` e `semver-major` do `python`, como no PHParrot.

## Evidência

- `pyproject.toml:2-3` (backend), `:8` (Python), `:9-23` (versões exatas) e `:31` (o `N818`).
- `Dockerfile:1` e `:3` (digests), `:19` e `:25` (`uv sync --frozen`), `:45` (remoção do `pip`).
- `uv.lock`: 175 hashes `sha256` (`grep -c sha256 uv.lock`).
- PHParrot: `f7bc8f7`, `d44c917` e `864751c`.

# uv, versões exatas, lock, digest e Python 3.13

## Contexto

O mesmo build precisa dar a mesma imagem. O Dependabot do PHParrot subiu o Python do gateway da 3.13 para a 3.15 num PR de `semver-minor`, e o ajuste foi travar a 3.13 (`.ai/pitfalls.md`). A imagem base do Python traz o `pip`, que não é usado em execução.

## Decisão

- O `uv` é a única ferramenta de ambiente: `uv sync --locked`, `uv run`. O `--locked` falha se o `pyproject.toml` e o `uv.lock` divergirem. O `--frozen` instalava o lock em silêncio (medido na S2: o `pyproject.toml` pedia `fastapi==0.161.0`, o lock tinha a `0.162.0`, e o `uv sync --frozen` instalou a `0.162.0`). O `uv run --frozen --no-sync` do gate continua, porque o `uv sync --locked` já conferiu.
- Dependências com versão exata no `pyproject.toml`, e o `uv.lock` versionado, com hashes.
- Imagens base por tag e digest: `uv` 0.13.7 e `python:3.13.18-slim`.
- `requires-python = "==3.13.*"`. Subir o minor do Python é uma rodada própria: `requires-python`, `uv.lock`, mypy e o estágio `teste`.
- O backend de build é o `uv_build`, na mesma versão do `uv` da imagem: as duas versões andam juntas. Com as versões iguais, o build funciona sem rede (`uv build --wheel` com `--network none`, medido na S2). Com versões diferentes, não foi testado se o `uv` baixa o backend nem como.
- O estágio final atualiza o `zlib1g` (`apt-get install --only-upgrade zlib1g`) e confere a versão com o `dpkg`. A base fixada traz `1:1.3.dfsg+really1.3.1-1+b1`, com dois HIGH (CVE-2026-76844 e CVE-2026-85091, estouro de heap no `gzwrite`, corrigidos pelo DSA-6613-1 na `+deb13u1`), e a base mais nova ainda não os corrige. A linha sai quando a base trouxer a `+deb13u1`. Rejeitados: um `.trivyignore` para CVE que já tem correção e adiar a release.
- A imagem final sai sem o `pip`. O ADR 0013 do PHParrot registra que o `pip` da base traz CVEs HIGH no `_vendor`. Isso não foi reverificado aqui.
- O ruff ignora só o `N818` (sufixo `Error` em exceção), porque os nomes são em português.

## Consequência

- Atualizar uma dependência é um PR que muda o `pyproject.toml` e o `uv.lock` juntos.
- Sem `uv` local, o lock se gera numa imagem descartável (`docs/desenvolvimento.md`).
- O build deixa de ser hermético: o `apt-get update` do `zlib1g` precisa de rede e do índice do Debian do dia. Foi o mesmo custo que o PHParrot aceitou em `d44c917`.
- O `.github/dependabot.yml` ignora `semver-minor` e `semver-major` do `python` no bloco de `docker`, como no PHParrot (ADR 0011). O Dependabot pode subir o `uv` da imagem sem o `uv_build`: quem revisa o PR sobe os dois juntos.

## Evidência

- `pyproject.toml:2-3` (backend), `:8` (Python), `:9-26` (versões exatas) e `:33` (o `N818`).
- `Dockerfile:1` e `:3` (digests), `:19`, `:25`, `:29` e `:36` (`uv sync --locked`), `:48-52` (o `zlib1g`) e `:54` (remoção do `pip`).
- `uv.lock`: 175 hashes `sha256` (`grep -c sha256 uv.lock`).
- PHParrot: `f7bc8f7`, `d44c917` e `864751c`.

# Pitfalls

Só o que o git, o código ou um comando mostram. Os SHAs de `PHParrot` são da `main` pública dele (`864751c`), onde o gateway nasceu em `docker/gateway/`. Este repositório foi recriado com 1 commit (`c923f58`).

## O Dependabot subiu o Python para 3.15

O PR #12 do PHParrot trocou `python:3.13.18-slim` por `python:3.15.0-slim` no Dockerfile do gateway. O tipo da atualização era `semver-minor`. O projeto trava `requires-python` em `==3.13.*`.

Evidência no PHParrot:

- `f7bc8f7`: o bump (`docker/gateway/Dockerfile`, 1 linha).
- `d44c917`: trava o gateway de volta na 3.13.
- `864751c`: a mensagem diz que o bump do #12 para 3.15 o quebrou. O `.github/dependabot.yml:41-45` passa a ignorar `semver-minor` e `semver-major` do `python` no gateway.

Código atual: `pyproject.toml:8` (`requires-python = "==3.13.*"`) e `Dockerfile:3` (imagem 3.13.18 por digest).

Este repositório não tem `.github/dependabot.yml`. Se ele for criado, o bloco de `docker` precisa do mesmo ignore do `python`. O que exatamente quebrou na 3.15 não foi testado aqui.

## O layout solto na raiz quebra imports e Dockerfile

Com os 10 módulos na raiz do repositório, o import de `gateway.*` não resolve. Medido com os arquivos soltos montados em `/x` na imagem de teste:

```
File "/x/app.py", line 7, in <module>
    from gateway.autenticacao import exigir_token
ModuleNotFoundError: No module named 'gateway'
```

O layout antigo estava amarrado ao nome `gateway` em três lugares. No PHParrot, em `864751c`:

- `docker/gateway/Dockerfile:25` e `:40`: `COPY gateway ./gateway`.
- `docker/gateway/Dockerfile:51`: `--factory gateway.app:criar_app`.
- 30 linhas `from gateway.` em `docker/gateway/` (por exemplo `docker/gateway/gateway/app.py:7`).

Código atual: `src/llm_gateway/app.py:7` (`from llm_gateway.autenticacao import exigir_token`), `Dockerfile:23` (`COPY src ./src`) e `Dockerfile:60` (`--factory llm_gateway.app:criar_app`). Ver o ADR 0007.

## Recriar o `.git` perde o histórico

O `main` daqui tem 1 commit de código (`c923f58`). O histórico real tem 6 commits e foi tirado do PHParrot com `git subtree split --prefix=docker/gateway`. Ele continua em dois lugares:

- No PHParrot, nos commits que tocam `docker/gateway/`: `61dff6c`, `1d10117`, `5c260de`, `f958a5e`, `f7bc8f7` e `d44c917`.
- No branch local `split/llm-gateway` do PHParrot, de `6bcf554` a `6f70077`. Ele não está publicado.

Comando que conta: `git -C <PHParrot> rev-list --count split/llm-gateway` devolve 6. Apagar esse branch antes de publicar o histórico em outro lugar apaga a única cópia com a árvore já separada.

## A imagem do uv sozinha não gera o lock

Sem uv local, `uv lock` na imagem `ghcr.io/astral-sh/uv:0.13.7` não roda. Ela não tem shell nem libc para o uv achar um Python:

```
error: Failed to discover managed Python installations
  cause: Failed to find any common binaries to determine libc from: /bin/sh, /usr/bin/env, /bin/dash, /bin/ls
```

O que funcionou foi copiar o binário `/uv` para uma imagem `python:3.13.18-slim`, as duas por digest (as mesmas do `Dockerfile:1` e `:3`). O passo a passo está em `docs/desenvolvimento.md`.

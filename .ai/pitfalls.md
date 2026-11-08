# Pitfalls

Só o que o git, o código ou um comando mostram. Os SHAs de `PHParrot` são da `main` pública dele (`864751c`), onde o gateway nasceu em `docker/gateway/`. Este repositório foi recriado com 1 commit (`c923f58`).

## O Dependabot subiu o Python para 3.15

O PR #12 do PHParrot trocou `python:3.13.18-slim` por `python:3.15.0-slim` no Dockerfile do gateway. O tipo da atualização era `semver-minor`. O projeto trava `requires-python` em `==3.13.*`.

Evidência no PHParrot:

- `f7bc8f7`: o bump (`docker/gateway/Dockerfile`, 1 linha).
- `d44c917`: trava o gateway de volta na 3.13.
- `864751c`: a mensagem diz que o bump do #12 para 3.15 o quebrou. O `.github/dependabot.yml` do PHParrot (`:41-45`) passa a ignorar `semver-minor` e `semver-major` do `python` no gateway.

Código atual: `pyproject.toml:8` (`requires-python = "==3.13.*"`) e `Dockerfile:3` (imagem 3.13.18 por digest).

Neste repositório, o `.github/dependabot.yml` tem o mesmo ignore do `python` no bloco de `docker` (`:14-18`). O que exatamente quebrou na 3.15 não foi testado aqui.

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

Código atual: `src/llm_gateway/app.py:10` (`from llm_gateway.autenticacao import exigir_token`), `Dockerfile:23` (`COPY src ./src`) e `Dockerfile:70` (`--factory llm_gateway.app:criar_app`). Ver o ADR 0007.

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

## O `zlib1g` da base tem dois HIGH, e subir o digest não corrige

Medido com o Trivy `v0.76.1` (`--severity CRITICAL,HIGH --ignore-unfixed`) sobre a imagem construída da `main` de antes desta rodada: Debian 13.7, `zlib1g 1:1.3.dfsg+really1.3.1-1+b1`, com correção em `1:1.3.dfsg+really1.3.1-1+deb13u1`:

- CVE-2026-76844 (HIGH). O título que o Trivy mostra é `webpack-dev-middleware: Information Disclosure via Path Traversal`, e está errado: a descrição do Trivy e a página do Debian dizem estouro de heap do zlib no `gz_write` depois de uma falha de `write()`.
- CVE-2026-85091 (HIGH). Estouro de heap do zlib no `gz_vacate`, com `gzprintf` depois de um travamento de escrita.

Conferido no rastreador do Debian: os dois estão no DSA-6613-1 (`zlib - security update`), corrigidos em `trixie (security) 1:1.3.dfsg+really1.3.1-1+deb13u1`. O mesmo DSA lista o CVE-2026-27171, que o Trivy não apontou como HIGH.

Código atual: `Dockerfile:48-52` atualiza o `zlib1g` e o `dpkg --compare-versions` falha o build se a versão ficar abaixo da `+deb13u1`. Depois da linha, o Trivy de imagem sai com 0. A linha sai quando a base trouxer a `+deb13u1`: confira com `docker run --rm --entrypoint dpkg-query <base> --show zlib1g`.

## O `uv sync --frozen` instalava um lock desatualizado em silêncio

Medido na S2: com `fastapi==0.161.0` só no `pyproject.toml`, o `uv sync --frozen --no-dev` instalou a `0.162.0` do lock, sem aviso. O `--locked` falha:

```
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
hint: To update the lockfile, run `uv lock`.
```

Repetido nesta rodada com `docker build --target teste .`: o build sai com código 1. O Dockerfile usa `--locked` em todo `uv sync`. O `uv run --frozen --no-sync` fica porque vem depois do `sync` conferido.

## O `pytest-cov` compara o total arredondado, mas imprime `FAIL` sem arredondar

Com a cobertura em 98,988% e `fail_under = 99` (precisão 0), o `pytest` sai com 0 e ainda assim imprime `FAIL Required test coverage of 99.0% not reached. Total coverage: 98.99%`. O código de saída usa o total arredondado (`coverage.results.should_fail_under`), e a mensagem do resumo compara o valor exato. Por isso o piso é um inteiro abaixo do medido (`fail_under = 98`), que não gera a mensagem enganosa. Provado: com `98`, a rodada completa sai com 0 e a rodada de um arquivo só (`tests/test_saude.py`) sai com 1.

## O `imagetools create` troca o digest da imagem que copia

Medido no ensaio local do release, com dois `registry:2` (portas 5000 e 5001), copiando um manifesto de imagem simples:

```
docker buildx imagetools create --tag localhost:5001/llm-gateway:0.0.1-rc localhost:5000/llm-gateway@sha256:c0ab30df…
pushing sha256:5a32ed51… to localhost:5001/llm-gateway:0.0.1-rc
```

O destino ficou com um índice OCI (`application/vnd.oci.image.index.v1+json`) que aponta para o `c0ab30df…`, e o digest da tag virou `5a32ed51…`. Com um único origem, o padrão é gerar o índice (`--prefer-index`). Com `--prefer-index=false` a cópia é fiel e o digest é o mesmo. Código atual: `.github/scripts/publicar.sh:9` usa a flag e `:11-15` confere que o digest publicado é o varrido.

# Desenvolvimento

## Ambiente

O projeto usa só o `uv` (`.claude/skills/python-313/SKILL.md`). O Python é o 3.13.

```bash
uv sync --locked
uv run pytest --cov=llm_gateway --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run python tools/sem_comentario.py
uv run mypy
```

Subir o servidor local, com um token fictício:

```bash
TOKEN_ARQUIVO="$(mktemp)" && printf 'exemplo-nao-use-em-producao-0123456789' > "$TOKEN_ARQUIVO"
GATEWAY_TOKEN_ARQUIVO="$TOKEN_ARQUIVO" GATEWAY_MODELOS=llama3.2:3b GATEWAY_CONCORRENCIA=1 \
GATEWAY_OLLAMA_URL=http://127.0.0.1:11434 \
uv run uvicorn --factory llm_gateway.app:criar_app --host 127.0.0.1 --port 8000
```

## O gate

O gate é o build do estágio `teste` da imagem:

```bash
docker build --target teste .
```

Ele roda, nesta ordem, e para no primeiro que falhar:

1. `ruff check .`
2. `ruff format --check .`
3. `python tools/sem_comentario.py`
4. `mypy src tests tools` (modo `strict`, com `warn_unreachable` e `explicit-override`)
5. `pytest` (com `filterwarnings = ["error"]`: aviso falha o teste), com cobertura de linhas e ramos (`--cov=llm_gateway`). O piso é o `fail_under` do `pyproject.toml` (hoje 98, o medido arredondado para baixo). Ele só sobe: cobertura abaixo do piso reprova o gate.

O `ci.yml` roda a trava de comentários e depois o mesmo build, em push e em pull request para o `main`. Nenhum teste acessa a rede nem o Ollama de verdade: o upstream é um `httpx2.MockTransport` (`tests/conftest.py`).

## A trava de comentários

`tools/sem_comentario.py` falha se achar, em `src/`, `tests/` ou `tools/`, um comentário ou uma docstring. Só `# type:` e `# noqa` passam. Ele usa o `tokenize` e o `ast` da biblioteca padrão, então um `#` dentro de uma string não conta. O porquê vai em `.ai/adr/` e o uso em `docs/`.

## Dependências e o `uv.lock`

Versão exata no `pyproject.toml` e o `uv.lock` no mesmo commit. Com `uv` local, `uv add pacote==X.Y.Z`. O `uv.lock` nunca se edita à mão.

Sem `uv` local, gere o lock numa imagem descartável com as mesmas bases do `Dockerfile` (`:1` e `:3`). A imagem do `uv` sozinha não roda: ela não tem shell nem libc (`.ai/pitfalls.md`).

```bash
docker build -q -t llm-gateway-uv - <<'EOF'
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM python:3.13.18-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 HOME=/tmp
EOF

docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/w -w /w llm-gateway-uv uv lock
```

Confira o diff do `uv.lock` antes de commitar: só as versões que você quis mudar. O build usa `--locked`: se o `pyproject.toml` e o `uv.lock` divergirem, o gate falha com `The lockfile at uv.lock needs to be updated, but --locked was provided`.

## O OpenAPI

`docs/openapi.json` é gerado pela factory e não se edita à mão:

```bash
uv run python tools/exportar_openapi.py
```

Sem `uv` local, use a imagem do estágio `teste`:

```bash
docker build --target teste -t llm-gateway:teste .
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/docs":/app/docs llm-gateway:teste \
  /app/.venv/bin/python tools/exportar_openapi.py
```

Rodar de novo não muda o arquivo. Mudou rota, modelo de entrada, limite ou `code`? Gere de novo e commite o arquivo junto: `tests/test_openapi.py` compara o arquivo com o que a factory gera, e o estágio `teste` copia só o `docs/openapi.json` para isso. Código de erro novo entra no enum `Codigo` (`src/llm_gateway/erros.py`), e o mypy recusa um código que não seja membro dele.

## CI e release

- `ci.yml`: a trava de comentários e o gate (`docker build --target teste .`), em push e em pull request para o `main`.
- `seguranca.yml`: o Trivy da imagem final, do Dockerfile e do `uv.lock` (`CRITICAL,HIGH`, `ignore-unfixed`, `exit-code 1`), quando o PR mexe em `Dockerfile`, `pyproject.toml`, `uv.lock`, `docs/openapi.json` ou no workflow, e toda segunda-feira. Para rodar à mão sem instalar nada: `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.76.1 image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 <imagem>`.
- `release.yml`: uma tag `vX.Y.Z` constrói a imagem final, varre o digest, publica exatamente esse digest em `ghcr.io/caiobarilli/llm-gateway:X.Y.Z` e cria a release com o SBOM e o digest no texto. Antes de tagar `vX.Y.Z`, o `pyproject.toml` já está em `X.Y.Z` (a `info.version` do OpenAPI vem dele). Uma tag `vX.Y.Z-rcN` é ensaio: não confere a versão e vira pré-lançamento.
- Nunca mover nem sobrescrever uma tag, e não existe `latest`. O job recusa publicar uma tag de imagem que já existe. Voltar atrás é apontar o consumidor para o digest da versão anterior.
- Os scripts do release estão em `.github/scripts/` e rodam fora do GitHub: o ensaio local usa dois `registry:2`, um no lugar do registro de varredura e outro no lugar do GHCR.

## Fluxo de branch e commit

Está em `.ai/regras.md`. Em resumo:

- Um branch por tarefa, nunca direto no `main`.
- Gate verde antes de cada commit.
- Mensagem de commit em português, no formato `tipo: resumo` (`feat`, `fix`, `docs`, `build`, `ci`, `refactor`, `chore`).
- Sem linha de coautoria de IA.
- O push e o merge são do Maintainer.

## Testes

- `tests/conftest.py` monta o app pela factory com o `OllamaFalso`, que guarda os pedidos recebidos.
- Toda recusa confere o status, o `code` e que o upstream não foi chamado.
- Campo novo no log precisa de prova de que não leva texto nem segredo.
- Bug novo: o teste que reproduz vem primeiro (`.claude/skills/pytest-gateway/SKILL.md`).

## Skills do projeto

Em `.claude/skills/`. São as regras do trabalho:

| Skill | Para quê |
|---|---|
| `python-313` | Escrever e revisar o código: `uv`, `mypy --strict`, ruff, layout `src/`, sem comentários de prosa. |
| `fastapi-gateway` | Factory, rotas, erros no formato da OpenAI, upstream, concorrência e métricas. |
| `pytest-gateway` | Como testar: Ollama falso, provas de log sem segredo, concorrência. |
| `api-security` | Revisão de segurança no roteiro do OWASP API Top 10. |
| `grilling` | Interrogar o plano ou o gateway, em três trilhas: segurança, performance e boas práticas. No fim, uma lista de achados com evidência e a proposta de PR de cada um. |

O que o gateway é e o limite dele estão em `.ai/teto.md`. Os motivos das decisões, em `.ai/adr/`.

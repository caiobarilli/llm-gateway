---
name: python-313
description: Como escrever e revisar o código do llm-gateway com Python 3.13 como piso — uv como única ferramenta de ambiente, mypy --strict, ruff (PEP 8 com linha de 120), layout src/ e a regra de sem comentários de prosa. Use ao escrever código novo, revisar um diff, mexer em dependências ou no pyproject.toml.
---

# Python 3.13 no llm-gateway

O projeto trava o Python em `==3.13.*` (`pyproject.toml`) e a imagem em
`python:3.13.x-slim` por digest. O Dependabot só traz patches da 3.13
(ADR do PHParrot herdado: minor e major do Python são decisão do Maintainer).
Se o piso é 3.13, o código usa 3.13: nada de compatibilidade com versões que o
projeto não roda.

## 1. Ambiente: só uv

- Tudo passa pelo `uv`: `uv sync --locked`, `uv run pytest`, `uv run mypy`,
  `uv run ruff`. Não use `pip`, `pip install --user`, `venv` à mão nem `poetry`.
- `uv.lock` é versionado e é a fonte da verdade. Dependência nova:
  `uv add pacote==X.Y.Z` (versão exata, como as atuais no `pyproject.toml`),
  e o diff do lock entra no mesmo commit.
- Sem uv local, gere o lock numa imagem descartável com o uv e o Python
  fixados por digest (foi assim no PR do layout `src/`). Nunca edite o
  `uv.lock` à mão.
- O backend de build é o `uv_build`, na mesma versão do uv do Dockerfile.

## 2. Layout src/

- O pacote mora em `src/llm_gateway/`; os testes em `tests/`.
- Imports sempre absolutos: `from llm_gateway.config import Config`.
  Nunca `from gateway.` (layout antigo) nem import relativo.
- A imagem final instala o pacote não editável no `.venv` e não leva `src/`.

## 3. Tipos: mypy --strict

- Toda função tem parâmetros e retorno anotados, inclusive `-> None`.
- Use a sintaxe moderna: `X | None`, `list[str]`, `dict[str, Any]`,
  `collections.abc` para `Iterator`, `AsyncIterator`, `Mapping`, `Callable`.
- `Any` só na borda com JSON externo (corpo do Ollama, schema do pedido) e
  nunca vazando para o resto do código sem validação.
- Dados imutáveis de configuração: `@dataclass(frozen=True, slots=True)`,
  como o `Config`.
- `# type: ignore` só com o código do erro (`# type: ignore[arg-type]`) e só
  se não houver tipo correto possível. Revisor recusa ignore genérico.

## 4. Estilo: PEP 8 pelo ruff

- O ruff é lint e formatador. Regras ativas: `E, F, W, I, B, UP, S, N, SIM, RUF, PT`
  (`S` é o conjunto do bandit, de segurança; `PT` é o do pytest, que pega
  `pytest.raises` largo demais). `S101` só é liberado em `tests/`.
- Linha de 120: desvio consciente do PEP 8 (79), registrado em ADR. Não
  reformate o projeto para 79 nem 88.
- `ruff format --check` e `ruff check` passam antes de qualquer commit.
- Nomes em português, como no resto do código (`criar_app`, `Limitador`,
  `exigir_token`). Inglês só onde o contrato externo pede (campos da API da
  OpenAI e do Ollama: `model`, `messages`, `done_reason`).

## 5. Sem comentários de prosa

- No código, só `# type:` e `# noqa`. O porquê mora em `.ai/adr/`, o uso em
  `docs/`. Mesma regra do PHParrot (hook `check-comentarios`) e do PHPorto.
- Docstring também é prosa: não escreva. O nome da função e o tipo explicam o
  quê; o ADR explica o porquê.

## 6. Recursos da 3.13 que valem aqui

- `typing.override` em subclasses (`FormatoJson.format`, `SaidaPadrao.emit`)
  deixa o mypy pegar assinatura que deixou de bater.
- `TaskGroup` e `asyncio.timeout` se um dia houver mais de uma chamada
  concorrente ao upstream. Hoje não há: a concorrência é 1 por decisão.
- Não use recurso só porque existe. Se não deixa o código mais curto ou mais
  seguro, fica de fora.

## Checklist de revisão

- [ ] `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`,
      `uv run pytest` verdes (ou `docker build --target teste .`).
- [ ] Nenhum import `gateway.` e nenhum import relativo.
- [ ] Nenhum comentário além de `# type:` e `# noqa`.
- [ ] Dependência nova com versão exata e `uv.lock` no mesmo commit.

# Linha de 120, desvio consciente do PEP 8

## Contexto

O PEP 8 recomenda linhas de até 79 caracteres e admite até 99 para equipes que combinem. O projeto escreve nomes e mensagens de erro em português, que ocupam mais espaço (`ESPERA_SUGERIDA_EM_SEGUNDOS`, "O gateway está ocupado. Tente de novo em instantes.").

Medido em `src/` e `tests/` em `c923f58`: 131 linhas passam de 79, 92 passam de 88 (o padrão do ruff), 48 passam de 99 e nenhuma passa de 120.

## Decisão

`line-length = 120` no ruff, para o lint e para o formatador. O resto do PEP 8 vem do ruff, com as regras `E, F, W, I, B, UP, S, N, SIM, RUF, PT, ASYNC`.

É um desvio do PEP 8, e fica registrado aqui. Não reformatar o projeto para 79 nem 88.

## Consequência

- `ruff format --check` e `ruff check` falham se uma linha passar de 120.
- Quem quiser outro limite muda uma linha do `pyproject.toml`, e o formatador reescreve o projeto todo.

## Evidência

- `pyproject.toml:29` (`line-length`), `:32-33` (as regras).
- `Dockerfile:38-39` (`ruff check` e `ruff format --check` no estágio `teste`).

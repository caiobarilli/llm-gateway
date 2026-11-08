# Regras

## Papéis

- **Maintainer:** decide, valida, faz o push e o merge.
- **Session Assistant:** orquestra, revisa o que volta e escreve os prompts. Não executa o projeto, não commita, não dá push.
- **CLI:** mede, escreve, roda o gate e commita. Não decide, não amplia o escopo, não dá push.

## Fluxo

- Um branch por tarefa. Nada direto no `main`.
- Gate verde antes de cada commit: `docker build --target teste .`.
- Commit no nome do Maintainer, sem linha de coautoria de IA. Conferir com `git log -1 --format=%b`.
- Sem push e sem merge pelo CLI.
- Sem nome real de pessoa em `.ai/`, `docs/`, README, código e mensagem de commit. A exceção é o `LICENSE`.
- Sem marca de ferramenta no código. Não criar `CLAUDE.md` nem `AGENTS.md`.
- Achado de segurança sem correção no PR vira item em `.ai/pitfalls.md`, com evidência.

## Código

- Sem comentários de prosa. Fica só `# type:` e `# noqa`. A trava é `tools/sem_comentario.py`.
- Docstring também não. O nome e o tipo dizem o quê; o porquê vai em `.ai/adr/` e o uso em `docs/`.
- Nomes em português. Inglês só onde o contrato externo pede (campos da API da OpenAI e do Ollama).
- Linha de 120, ruff com as regras do `pyproject.toml`, `mypy --strict`.
- Dependência nova entra com versão exata e com o `uv.lock` no mesmo commit.

## Proibições

- Comentário de prosa ou docstring.
- Rodapé de coautoria de IA.
- `# type: ignore` sem o código do erro.
- Rota nova fora de `/v1` sem ADR.
- Texto do pedido, da resposta, schema ou token em log ou em mensagem de erro.
- `pip` na imagem final.

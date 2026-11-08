---
name: grilling
description: Interrogar o Maintainer sem trégua sobre um plano, um PR ou o próprio llm-gateway até chegar a um entendimento comum, nas trilhas de segurança, performance e boas práticas. Use quando o Maintainer quiser testar um plano antes de construir, revisar o gateway a fundo, ou usar qualquer frase com "grill" ou "grilling".
---

# Grilling no llm-gateway

Interrogue o Maintainer sobre cada aspecto do plano até chegar a um
entendimento comum. Percorra cada galho da árvore de decisões, resolvendo as
dependências entre as decisões uma por uma.

## Mecânica

- **Uma pergunta por vez.** Espere a resposta antes da próxima. Várias de uma
  vez confundem.
- **Toda pergunta vem com a resposta recomendada** e o porquê, em uma ou duas
  frases.
- **Se o código responde, não pergunte.** Leia `src/`, `tests/`, `Dockerfile`,
  `pyproject.toml`, `.ai/` e `docs/` antes. Pergunte só o que é decisão.
- **Evidência sempre:** cite `arquivo:linha`, SHA ou saída de comando. Hipótese
  sem evidência é marcada "não testada".
- **Nada é implementado durante o grilling.** Nem um ajuste pequeno.

## Antes da primeira pergunta

1. Defina com o Maintainer o alvo: um plano, um PR, ou o gateway inteiro.
2. Defina a trilha da sessão: segurança, performance ou boas práticas. Uma
   trilha por sessão; se aparecer assunto de outra, anote para a próxima.
3. Leia as skills da trilha e o `.ai/teto.md`. O que estiver fora do teto não
   vira proposta sem o Maintainer pedir.

## Trilha 1 — Segurança

Apoio: skill `api-security` (o roteiro de revisão e o OWASP API Top 10).

Galhos a percorrer:

- Autenticação: token em arquivo, releitura, `compare_digest`, fail-closed,
  mensagens iguais para todo motivo de recusa.
- Superfície: rotas públicas, cabeçalhos, porta publicada, docs em runtime,
  ferramentas MCP.
- Entrada: todo campo com limite e `extra="forbid"`, schema validado como schema.
- Upstream: só `/api/chat`, sem redirect, timeouts, texto do upstream nunca
  repassado.
- Saída do modelo: dado não confiável, validação, o que o consumidor faz com ela.
- Logs: o que entra, o que nunca entra, e se há teste provando.
- Imagem e cadeia: digest, usuário, pacotes na imagem final, versões exatas,
  Dependabot, CI de segurança.

## Trilha 2 — Performance

Apoio: skill `fastapi-gateway` (seções de upstream, concorrência e métricas).

Galhos a percorrer:

- Latência total e onde ela mora: carga fria do modelo (`carga_ms`), geração
  (`tokens_por_segundo`), ida e volta do túnel.
- Tempo de GPU: `max_tokens`, `num_ctx`, tamanho das mensagens, e se os tetos
  fazem sentido para o uso real do consumidor.
- Concorrência: o `Limitador` sem fila, o valor do `Retry-After`, o que o
  consumidor faz com o 503.
- Timeouts: conexão e leitura contra o tempo medido de uma geração longa.
- Cliente HTTP: reutilizado pelo app inteiro e fechado no `lifespan`.
- Custo do próprio gateway: leitura do corpo, validação por schema, o token
  relido a cada pedido, a linha de log.
- Medir antes de propor: toda proposta de performance traz como medir antes e
  depois (comando, métrica e valor esperado).

## Trilha 3 — Boas práticas

Apoio: skills `python-313`, `fastapi-gateway` e `pytest-gateway`.

Galhos a percorrer:

- Tipos: `mypy --strict` sem `ignore` genérico, `Any` só na borda.
- Estilo: ruff, formato, nomes, a trava de comentários.
- Estrutura: factory, `app.state`, routers, erros no formato da OpenAI.
- Testes: recusas conferindo status, `code` e upstream não chamado; provas de
  log sem segredo; concorrência sem `sleep`; cobertura.
- Dependências e empacotamento: `uv`, lock, layout `src/`, imagem.
- Documentação: o que o código faz está em `docs/` e o porquê em `.ai/adr/`.

## Fim da sessão

Entregue ao Maintainer uma lista de achados, cada um com:

1. **O achado**, em uma frase.
2. **Evidência:** `arquivo:linha`, SHA ou saída de comando.
3. **Severidade:** alta, média ou baixa, e por quê.
4. **Proposta de PR:** o que muda, o critério de aceite e como medir
   (performance) ou provar com teste (segurança e comportamento).
5. **Decisão pendente**, se houver, com a resposta recomendada.

O que não tem evidência vai numa seção separada, "hipóteses não testadas".
Nada sai do grilling direto para o código: cada PR proposto passa pelo
Maintainer antes.

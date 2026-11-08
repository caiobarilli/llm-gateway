---
name: api-security
description: Revisão de segurança do llm-gateway no espírito do OWASP API Security Top 10 — autenticação por token em arquivo, allowlist de modelos, limites de recurso, saída do modelo como dado não confiável, superfície mínima, logs sem segredo, imagem e cadeia de dependências. Use ao revisar qualquer PR, ao abrir rota ou ferramenta MCP nova, ao mexer em autenticação, logs, Dockerfile ou dependências.
---

# Segurança da API do llm-gateway

Itens marcados com `(alvo)` ainda não existem no repositório. Quem entregar o item remove a marca no mesmo commit.

O gateway fica entre um app e um modelo que roda na máquina de alguém. O que
ele protege: o token, a GPU (tempo e memória) e a máquina do Ollama, que nunca
pode virar um proxy aberto. Cada seção abaixo cita o risco do OWASP API Top 10
(2023) que ela cobre.

## 1. Autenticação (API2)

- Um token Bearer, lido de um arquivo montado só leitura
  (`GATEWAY_TOKEN_ARQUIVO`). Nunca de variável de ambiente, nunca do repositório.
- O arquivo é relido a cada pedido: trocar o token não exige reiniciar.
- Comparação com `hmac.compare_digest`. Nunca `==`.
- Sem arquivo ou arquivo vazio: 503 `token_indisponivel` (fail-closed).
  Cabeçalho ausente, malformado ou token errado: 401 com `WWW-Authenticate: Bearer`,
  sempre a mesma mensagem, sem dizer qual foi o motivo.
- O MCP usa o mesmo token e a mesma função. Não existe segundo segredo. (alvo, exige ADR)

## 2. Autorização de função e de objeto (API1, API5)

- Não há usuário nem objeto por dono: o token vale para tudo que o gateway
  expõe. Por isso a superfície é mínima e fechada.
- A allowlist de modelos (`GATEWAY_MODELOS`) é a autorização: modelo fora dela
  nunca chega ao Ollama.
- Nenhuma operação administrativa (baixar, apagar, listar o que existe no
  Ollama) passa pelo gateway, nem pelo HTTP nem pelo MCP (alvo, exige ADR).

## 3. Consumo de recursos (API4)

- Corpo com teto (64 KiB, 413), mensagens com teto de quantidade e de
  caracteres, `max_tokens` com teto, contexto fixo (`num_ctx`).
- Um pedido por vez (`GATEWAY_CONCORRENCIA`), sem fila: 503 `ocupado` com
  `Retry-After`. Fila seria memória e tempo de GPU sem dono.
- Tempo de conexão e de leitura no cliente do upstream.
- O container roda com memória limitada, sistema de arquivos só leitura e
  `/tmp` em tmpfs `noexec` (definido pelo consumidor; documentar em `docs/`).

## 4. Propriedades e entrada (API3, API8)

- `extra="forbid"` em todo modelo de entrada: campo desconhecido é recusado,
  não ignorado.
- O schema pedido pelo cliente é validado como schema antes do uso
  (`SchemaError` vira 400).

## 5. Saída do modelo (API10: consumo inseguro de API)

- O Ollama é um upstream como outro qualquer: a resposta é validada com
  Pydantic e, se houver schema, com `jsonschema`.
- Saída fora do formato: 502 `saida_invalida`, sem devolver o texto.
- O gateway não interpreta nem executa nada que o modelo devolve. O consumidor
  trata o conteúdo como dado não confiável (no PHParrot, a validação do pacote e
  a aprovação na gestão).

## 6. Superfície e configuração (API8, API9)

- Rotas públicas: só `/health`. `/docs`, `/redoc` e `/openapi.json` desligados.
- Sem `Server` no cabeçalho e sem access log do uvicorn.
- Porta: o container não publica porta por padrão. Se publicar, só em
  `127.0.0.1`. O caso do MCP no notebook é (alvo, exige ADR).
- Inventário (API9): toda rota está listada em `docs/api.md`. Rota que não
  está no doc é bug. Ferramenta MCP, quando existir, entra na mesma lista
  (alvo, exige ADR).

## 7. Logs

- Só a linha de métricas e eventos de recusa, sem conteúdo.
- Nunca: token, cabeçalho `Authorization`, prompt, resposta, schema, caminho
  do arquivo de segredo. Há testes que provam; veja a skill `pytest-gateway`.

## 8. Imagem e dependências

- Imagens base por digest, usuário sem privilégio (10002), sem `pip` na imagem
  final, healthcheck.
- Dependências com versão exata e `uv.lock`. Actions fixadas por SHA.
- Dependabot para `uv`, `docker` e `github-actions`. (alvo)
- CI: ruff com o conjunto `S` (bandit). Trivy da imagem e da config, SBOM,
  `pip-audit` e CodeQL. (alvo) Achado alto ou crítico bloqueia o merge. (alvo)

## Roteiro de revisão de um PR

1. O PR abre rota, ferramenta MCP (alvo, exige ADR) ou cabeçalho novo? Está em
   `/v1`, com token e listado em `docs/api.md`?
2. Algum campo de entrada sem limite ou sem `extra="forbid"`?
3. Algum caminho chega ao Ollama sem passar pela allowlist e pelo `Limitador`?
4. Alguma mensagem de erro ou linha de log carrega dado do pedido, da resposta
   ou do token?
5. Dependência nova: versão exata, lock, licença compatível com MIT, e por que
   ela é necessária?
6. Dockerfile: digest mantido, usuário 10002 mantido, nada de pacote extra na
   imagem final?

Achado sem correção no PR vira item em `.ai/pitfalls.md` com evidência.

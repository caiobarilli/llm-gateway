# Segurança

## O que o gateway protege

- O **token**, que autoriza o uso do modelo.
- A **GPU**: tempo e memória da máquina que roda o Ollama.
- O **Ollama**, que nunca deve virar um proxy aberto: o gateway só chama `POST /api/chat`.

## Modelo de ameaças

| Quem | O que tenta | Onde o código responde |
|---|---|---|
| Quem alcança a porta sem token | Usar o modelo ou ver o que existe | 401 em toda rota de `/v1`. Só o `/health` é pública. |
| Quem tem o token | Gastar a GPU, pedir modelo que não é seu, mandar corpo enorme | Allowlist, limites de entrada, `Limitador` e tempos limite. |
| Quem tem o token | Mandar um schema que faz o gateway buscar uma URL ou gastar CPU | Subconjunto de palavras-chave e tetos de tamanho (ADR 0009). |
| O modelo | Devolver saída fora do formato ou cortada | Validação por JSON Schema e erro 502, sem repassar o texto. |
| O Ollama ou a rede até ele | Responder lixo, demorar ou cair | Pydantic na resposta, tempos limite e erro próprio, sem repassar o corpo. |
| A cadeia de dependências | Trazer código alterado | Versões exatas, `uv.lock` com hashes, imagens e actions fixadas. |

Fora deste modelo: o canal até o gateway. Ele fala HTTP. Expor a porta fora do loopback ou da rede interna, e proteger esse caminho (por exemplo, com um túnel), cabe a quem roda a imagem. Quem pode ler o arquivo do token também fica fora: é o consumidor que o monta.

## OWASP API Security Top 10 (2023)

| Item | Como o gateway responde |
|---|---|
| **API1** Autorização de objeto quebrada | Não há objetos por dono nem identificador na URL. O token vale para tudo que o gateway expõe, e a superfície é fechada. |
| **API2** Autenticação quebrada | Token em arquivo, relido a cada pedido, `hmac.compare_digest`, fail-closed e mensagem única para toda recusa (ADR 0008). |
| **API3** Autorização de propriedade de objeto quebrada | `extra="forbid"` em todo modelo de entrada: campo desconhecido é recusado. A resposta é montada campo a campo por `formatar`, sem repassar o objeto do Ollama. |
| **API4** Consumo irrestrito de recursos | Corpo de 64 KiB, 8 mensagens, 8000 caracteres, `max_tokens` até 1024, `num_ctx` fixo, um pedido por vez sem fila (ADR 0002) e tempos limite de 5 s e 60 s. |
| **API5** Autorização de função quebrada | Não existe função administrativa. Baixar, apagar e listar modelos do Ollama não passam pelo gateway. |
| **API6** Acesso irrestrito a fluxos sensíveis | O fluxo caro é a geração. Ela passa por token, allowlist e `Limitador`. |
| **API7** SSRF | O destino do upstream vem de `GATEWAY_OLLAMA_URL`, e redirecionamentos não são seguidos. O único campo do pedido que poderia escolher uma URL era o `$ref` do schema, e o subconjunto de palavras-chave o recusa (ADR 0009). |
| **API8** Configuração incorreta de segurança | `/docs`, `/redoc` e `/openapi.json` desligados, barra final sem redirecionamento (`redirect_slashes=False`), sem cabeçalho `Server`, sem access log, configuração inválida impede a subida, usuário sem privilégio na imagem. |
| **API9** Gestão incorreta do inventário | Toda rota está em `docs/api.md` e em `docs/openapi.json`. Rota nova fora de `/v1` exige ADR (`.ai/regras.md`). |
| **API10** Consumo inseguro de APIs | O Ollama é um upstream como outro qualquer: a resposta é validada e o texto dele nunca é repassado (seção abaixo). |

## Autenticação

- Um token Bearer, lido de um arquivo. O arquivo é relido a cada pedido, então trocar o token vale sem reiniciar.
- Comparação com `hmac.compare_digest`, em bytes.
- Sem arquivo, arquivo vazio, ilegível, fora de ASCII ou com menos de 32 caracteres depois do `strip`: 503 `token_indisponivel`. Cabeçalho ausente, malformado ou token errado: 401 com `WWW-Authenticate: Bearer`, sempre a mesma mensagem.
- O motivo `token curto` vai para o log, sem o token. Gere o token com `openssl rand -hex 32` (64 caracteres). Não há limite de tentativas: com 32 caracteres ou mais, adivinhar não é um risco real.
- Código: `src/llm_gateway/autenticacao.py:15-62`. Provas: `tests/test_autenticacao.py`.

## Allowlist

`GATEWAY_MODELOS` é a autorização. O modelo do pedido é conferido antes de qualquer chamada ao Ollama (`src/llm_gateway/modelos.py:7-16`). O nome do modelo tem até 100 caracteres: mais que isso dá 400 `invalid_request` antes da allowlist. A mensagem do 404 cita o nome recebido.

## Limites

Os valores estão em `docs/api.md` e `docs/configuracao.md`. O corpo é lido com teto: o `Content-Length` declarado é conferido antes, e o que chega é contado. A mensagem do 400 cita só caminhos do schema (até 5, com até 40 caracteres cada). Campo desconhecido aparece como o caminho até ele mais `(campo não permitido)`: nem o valor nem o nome que o cliente inventou voltam na resposta.

## O schema do cliente

O schema do `response_format` é executado pelo gateway: valida a saída e vai inteiro para o Ollama. Ele é um subconjunto de JSON Schema, com lista fixa de palavras-chave e tetos de nós, profundidade e tamanho (`docs/api.md`, ADR 0009). `$ref` (local ou remoto), `pattern`, `format` e os combinadores são recusados com 400 `schema_invalido` antes de qualquer execução, o que fecha a busca remota do `jsonschema` e a expressão regular com custo exponencial. Código: `src/llm_gateway/subconjunto.py`. Provas: `tests/test_subconjunto.py`.

## A saída é dado não confiável

O gateway não interpreta nem executa o que o modelo devolve.

- A resposta do Ollama é validada com Pydantic. Fora do formato: 502 `upstream_resposta_invalida`.
- Com `response_format`, a saída é validada contra o schema do pedido. Falha dá 502 `saida_invalida` ou `saida_truncada`, sem o conteúdo (ADR 0003).
- Quem consome trata o conteúdo como dado não confiável. No PHParrot, ele passa por validação e por aprovação antes de ser usado (ADR 0013 do PHParrot, item 7).

## Logs

Só a linha de métricas e eventos curtos de autenticação, sem conteúdo (ADR 0004). Uma exceção inesperada na rota do chat vira 500 `erro_interno` e deixa na linha só o nome da classe (`erro`), nunca a mensagem. Nunca entram token, cabeçalho `Authorization`, prompt, mensagens, resposta nem schema. Os testes `tests/test_chat.py:354` e `tests/test_autenticacao.py:131` provam isso com valores marcados e com o log em `DEBUG`.

## Imagem

- Imagens base fixadas por tag e digest (`Dockerfile:1` e `:3`).
- O `zlib1g` da base é atualizado no estágio final (`apt-get install --only-upgrade zlib1g`), porque a base fixada traz a versão com os CVE-2026-76844 e CVE-2026-85091 (DSA-6613-1 do Debian). O build confere a versão com o `dpkg`, e a linha sai quando a base trouxer a correção (`.ai/pitfalls.md`).
- A imagem declara a origem (`org.opencontainers.image.source`) e carrega o `openapi.json` em `/app/openapi.json`.
- Estágios separados: o pacote é instalado não editável e a imagem final leva só o `.venv`, sem `src/` (ADR 0007).
- Usuário 10002, sem `pip` na imagem final, `HEALTHCHECK` em `/health` (`Dockerfile:54-68`).
- Sobe com o sistema de arquivos só leitura e `/tmp` em tmpfs (`docs/operacao.md`).
- A porta não é publicada por padrão. Se for, só em `127.0.0.1`.

## Cadeia de dependências

- Versões exatas no `pyproject.toml` e `uv.lock` versionado, com hashes (ADR 0005).
- Backend de build com versão travada (`uv_build==0.13.7`), na mesma versão do `uv` da imagem (ADR 0005).
- O build usa `uv sync --locked`: um `pyproject.toml` que diverge do `uv.lock` falha o gate, em vez de instalar versões diferentes das declaradas.
- `httpx2` e `httpcore2` (o cliente HTTP do upstream, que o SDK `openai` também usa) foram conferidos: os metadados do PyPI e o repositório `pydantic/httpx2` batem (autor do `httpx`, BSD-3-Clause), o projeto tem cerca de 6 meses (criado em 2026-05-11, 22 releases) e não publica attestation de Trusted Publishing (a rota de proveniência do PyPI responde 404).
- As actions do `ci.yml` estão fixadas por SHA, e o workflow tem permissões somente leitura.
- O ruff roda com o conjunto `S` (regras de segurança do bandit).
- Este repositório ainda não executa varredura de vulnerabilidade da imagem nem do lock no CI. Medido à mão com o Trivy `v0.76.1`: imagem, Dockerfile e `uv.lock` limpos para `CRITICAL,HIGH` com `--ignore-unfixed`.

# Grilling S2: segurança, imagem, cadeia de dependências, CI de segurança e MCP

Alvo: o Dockerfile, o `pyproject.toml` e o `uv.lock` em `9db9b3f`, o CI de segurança que falta e o modelo de ameaça do MCP. Trilha 1, skill `api-security` (§6 a §8).
Método: como na S1. Os achados vieram de medição (Trivy, `pip-audit`, `hadolint`, PyPI, GitHub, builds descartáveis). Um revisor de segurança cético e um advogado do consumidor julgaram cada achado, sem ver a opinião um do outro.
Regra de aceite sem o Maintainer: consenso, severidade baixa ou média, dentro do contrato e do teto. O resto fica pendente.
Nada foi implementado.

Os dois revisores corrigiram uma premissa: o PHParrot **não consome** esta imagem hoje. Ele constrói a própria cópia em `docker/gateway/` (`terraform/main.tf:12` e `:245-248`), com o mesmo digest de base e também com `--frozen`. A S5 trata de trocar isso.

## Decidido pelo Maintainer

Nada novo. Valem as decisões da S1 que tocam aqui: F4 (token de 32 caracteres ou mais) e F6 (lista de palavras-chave do schema). A lista de ferramentas de CI que o Maintainer quer ver (Dependabot, Trivy da imagem e da config, SBOM, `pip-audit`, CodeQL) é o ponto de partida de F13.

## Aceito por consenso

### F11 (média): a imagem reprovaria o critério de Trivy do PHParrot, e subir o digest não corrige
- Evidência medida:
  - `trivy image --severity CRITICAL,HIGH --ignore-unfixed` sobre a imagem do `main`: dependências Python, 0 achados. Debian 13.7: 2 HIGH em `zlib1g 1:1.3.dfsg+really1.3.1-1+b1`, com correção em `…+deb13u1` (CVE-2026-76844 e CVE-2026-85091).
  - A base mais nova (`python:3.13-slim`, puxada na hora, também 3.13.18, digest `e48f59cd…`) tem o mesmo `zlib1g +b1`. A base ainda não trouxe a correção.
  - O Debian oferece a correção: `apt list --upgradable` dentro da base fixada mostra `zlib1g … stable-security … deb13u1 [upgradable from … +b1]`.
  - O critério do PHParrot é `severity: CRITICAL,HIGH`, `ignore-unfixed: true`, `exit-code: '1'` (`containers.yml:120-128`). Precedente: `d44c917` (`docker/whisper/Dockerfile:52`, `docker/nginx/Dockerfile:4`).
- Lentes: as duas escolhem a opção (a), atualizar o pacote no estágio final. Rejeitam `.trivyignore` para CVE que já tem correção e adiar a release sem prazo. O cético pede que se confira o CVE, porque o título do CVE-2026-76844 na saída do Trivy fala de `webpack-dev-middleware`, não de zlib.
- Proposta: no estágio final, antes do `USER 10002` (`Dockerfile:45`), uma linha `apt-get update && apt-get install -y --no-install-recommends --only-upgrade zlib1g && rm -rf /var/lib/apt/lists/*`, com conferência por `dpkg-query` no log do build. Um item em `.ai/pitfalls.md` e uma nota no ADR 0005 dizem que a linha sai quando a base trouxer `+deb13u1`.
- Custo conhecido: o build deixa de ser hermético (precisa de rede e do índice do Debian do dia). É o mesmo custo que o PHParrot aceitou em `d44c917`.
- Aceite: `trivy image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1` sobre a imagem final sai com 0, e o `dpkg-query` do build mostra `deb13u1`.

### F12 (média): `uv sync --frozen` aceita lock desatualizado em silêncio
- Evidência medida: numa cópia, troquei `fastapi==0.162.0` por `==0.161.0` só no `pyproject.toml`. `uv sync --frozen --no-dev` instalou o `0.162.0` sem aviso. `uv sync --locked --no-dev` falhou com `hint: To update the lockfile, run uv lock`. O Dockerfile usa `--frozen` em `:19`, `:25`, `:29` e `:34`. O gate pode passar com versões diferentes das que o `pyproject.toml` afirma.
- Lentes: as duas aceitam. Concordam que não precisa de um passo `uv lock --check` no CI, porque o build do estágio `teste` já falharia.
- Proposta: `--locked` nos 4 `uv sync` do Dockerfile. O `uv run --frozen --no-sync` fica. Atualizar `README.md`, `docs/desenvolvimento.md:8` e o ADR 0005 (`:9`, `:26`), que citam `--frozen`.
- Aceite: um teste de gate (ou o passo manual documentado) em que o `pyproject.toml` diverge do lock e o `docker build --target teste .` falha.
- Nota: a cópia do PHParrot também usa `--frozen` (`docker/gateway/Dockerfile:19`, `:23`). Isso deixa de importar quando a S5 acontecer.

### F14 (baixa): superfície da imagem final e o que o consumidor aplica
- Evidência medida (imagem final, 208 MB): usuário 10002, sem `curl`, `wget`, `pip` nem `uv`; mas há `sh`, `bash`, `apt`, `dpkg`, `perl` e binários setuid (`passwd`, `chfn`, `newgrp`, `chsh`, `umount`, `su`, `mount`, `gpasswd`). `/app` é `root:root 755`. A imagem sobe e fica `healthy` com `--read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 128m`.
- Lentes: as duas aceitam só documentar. Remover setuid, `apt` e `perl` (b) ou usar base distroless (c) é custo contínuo para uma ameaça que exige antes execução de código no container como 10002. O cético ressalva que o controle que neutraliza os setuid é o `no-new-privileges`, e que o `cap_drop` muda pouco para um uid que não é root.
- Proposta: `docs/operacao.md` (a lista de `:68-75` e o exemplo de `:79-90`) passa a trazer `--cap-drop ALL`, `--security-opt no-new-privileges` e `--pids-limit 64`, marcados como testados.

### F15 (baixa): procedência de `httpx2` e `httpcore2`
- Evidência medida hoje:
  - PyPI: `httpx2` e `httpcore2` 2.16.0, autor do `httpx`, BSD-3-Clause, 22 releases de 2026-05-11 a 2026-10-21, `Homepage`/`Source` em `github.com/pydantic/httpx2`.
  - GitHub: `pydantic/httpx2`, criado em 2026-05-11, último push em 2026-11-07, não é fork, não está arquivado, licença BSD-3-Clause.
  - Attestation de Trusted Publishing: `https://pypi.org/integrity/httpx2/2.16.0/<wheel>/provenance` responde **404**, ou seja, não há attestation.
  - O `openai` 3.46.0 também usa o `httpx2` (`openai._base_client` não tem `httpx`, só `httpx2`), então o pacote é o cliente HTTP do ecossistema, não uma escolha isolada deste repositório.
- Lentes: as duas rejeitam um check de licenças no CI (23 pacotes permissivos não pagam a manutenção) e pedem uma conferência única da procedência, registrada em `docs/seguranca.md`.
- Proposta: uma linha em `docs/seguranca.md`: os metadados do PyPI e o repositório batem, o projeto tem cerca de 6 meses e não publica attestation.
- Registro: licenças de runtime, todas permissivas e compatíveis com MIT: MIT, BSD-3-Clause, Apache-2.0 (`opentelemetry-api`, que entra por `fastapi`, não por escolha deste projeto) e PSF-2.0.

### Modelo de ameaça do MCP: condições para o ADR existir
O MCP continua fora do teto. As duas lentes concordam nas condições abaixo, e elas passam a ser o roteiro do ADR dele.
1. **Token na entrada do mount.** Um app montado em `/mcp` não herda `dependencies=[Depends(exigir_token)]` do router `/v1`, nem os tratadores de `ErroOpenAI`, nem o teto de corpo, que hoje mora na rota. O token entra como middleware ASGI que cobre o mount, com testes de 401 e 503 em `/mcp` ligado.
2. **Desligado de verdade.** Com `GATEWAY_MCP=false`, `/mcp` não existe: teste de 404.
3. **Mesmos limites.** Teto de 64 KiB no nível ASGI, os mesmos modelos Pydantic (`extra="forbid"`), o filtro de schema da F6 sobre qualquer schema vindo por argumento, o mesmo `Limitador`, a mesma allowlist e uma só linha de métricas, sem texto.
4. **Sem estado, ou exceção explícita.** Modo sem `Mcp-Session-Id`, ou uma exceção ao teto "sem estado" com limite de sessões.
5. **Erros mascarados.** O SDK pode registrar argumentos ou devolver o texto da exceção ao cliente. Teste com valores marcados, com o log em `DEBUG`, passando por uma chamada MCP.
6. **Validação de `Origin`** em `/mcp`, sem CORS aberto, com teste. A especificação a exige para servidor em localhost. É o único risco com exploração concreta se o Bearer não valer.
7. **Delta de dependências medido** (contagem, licenças, Trivy verde) e escolha justificada entre `fastmcp` e o `mcp.server.fastmcp` do SDK oficial. Versão exata no `pyproject.toml` e no `uv.lock`. `FastMCP.from_fastapi` continua proibido.
8. **Publicar a porta expõe também o `/v1`** a qualquer processo local da máquina. O ADR precisa dizer isso.
- Exagero, segundo as duas lentes: a injeção de prompt indireta pelo texto gerado é do cliente MCP e cabe numa frase em `docs/seguranca.md`; o token no arquivo de configuração do notebook se resolve documentando a permissão do arquivo; os timeouts e a compatibilidade com o fluxo OAuth são de compatibilidade, não de segurança, e só viram bloqueio se o cliente do Maintainer não aceitar Bearer.

## Pendente do Maintainer

### P3. F13 (média): que CI de segurança entra antes da `v0.1.0` e com que bloqueio
O pedido original traz Dependabot, Trivy da imagem e da config, SBOM, `pip-audit` e CodeQL. As lentes divergem do conjunto, e mudar o que o Maintainer pediu e configurar regras de branch (fora do código) é decisão dele.
- Fatos medidos:
  - `pip-audit` sobre 36 pacotes (com dev): "No known vulnerabilities found".
  - `trivy fs` sobre o repositório lê o `uv.lock` (tipo `uv`) e acha 0 vulnerabilidades. Cobre o mesmo que o `pip-audit`, sem rede para o OSV.
  - `trivy config` sobre o `Dockerfile`: 0 problemas. `hadolint`: sem avisos. O PHParrot usa `hadolint` com `DL3008` ignorado.
  - SBOM CycloneDX 1.7 pelo Trivy: 111 componentes (23 PyPI, 87 Debian, 1 do SO).
  - O `ci.yml` só constrói o estágio `teste` (`ci.yml:36`). A imagem final, a que vai para o GHCR, nunca é construída nem varrida no CI.
- Cético: o Trivy da imagem e da config com `exit-code 1` como checks obrigatórios, o build do estágio final no CI, o Dependabot com o `ignore` do Python e uma varredura semanal por cron (como em `containers.yml:16-17`). Cortaria o `pip-audit` (o `trivy fs` cobre) e o `uv lock --check`. Mantém o CodeQL em "default setup", sem bloquear. SBOM como anexo da release. Aponta que sem checks obrigatórios num ruleset, com um mantenedor só, nada bloqueia: o CodeQL e o SARIF não derrubam o job.
- Advogado: um workflow `seguranca.yml` com um job de Trivy (imagem final, bloqueante) e o SBOM só em `tags: v*`. O Trivy roda quando o PR mexe em `Dockerfile`, `pyproject.toml`, `uv.lock` ou no workflow, além do cron semanal e da tag, para um CVE novo da base não derrubar PR sem relação. Corta `pip-audit`, CodeQL e o scan de configuração (redundante com `hadolint`). Pergunta quem lê o alerta do cron: sem notificação, a CI vermelha ninguém vê.
- Recomendação: Dependabot (`uv`, `docker`, `github-actions`, com o `ignore` de minor e major do `python`) mais um `seguranca.yml` que constrói a imagem final e roda o Trivy da imagem e da config (`CRITICAL,HIGH`, `ignore-unfixed`, `exit-code 1`) em PRs que mexem nos arquivos de build, no cron semanal e na tag. O SBOM sai só na tag e vai anexado à release. CodeQL entra em "default setup" pela interface, sem ser check obrigatório. Sai o `pip-audit` (o Trivy cobre o `uv.lock`, medido) e o `uv lock --check` (o `--locked` do F12 cobre). Os checks obrigatórios se ligam num ruleset do repositório, fora do código.
- Decisões que só o Maintainer toma: aceitar tirar `pip-audit` do pedido original; se o CodeQL entra e se é obrigatório; ligar o ruleset; quem recebe a notificação do cron.

### P4. F14 (baixa), a parte fora do repositório: o Terraform do PHParrot
- O `terraform/main.tf:255-279` do PHParrot não tem `cap_drop`, `security_opts` (`no-new-privileges`) nem `pids_limit`. Testei as três flags na imagem, e elas funcionam.
- O advogado aceitaria dois ou três ajustes num PR separado do PHParrot, sem bloquear a release. O cético lembra que o controle relevante é o `no-new-privileges`.
- Custo fora deste repositório: decisão do Maintainer. Recomendação: entra no PR da S5 que mexe no Terraform do PHParrot, com `security_opts = ["no-new-privileges"]` e `pids_limit`.

### P5. F16 (baixa): `uv_build` e o `uv` da imagem precisam andar juntos
- O advogado aponta que `Dockerfile:1` usa `uv:0.13.7` e `pyproject.toml:2` usa `uv_build==0.13.7`. O Dependabot pode subir um sem o outro.
- Medido: com as duas versões iguais, o build funciona **sem rede** (`uv build --wheel` com `--network none` gerou `llm_gateway-0.1.0-py3-none-any.whl`), então o `uv` usa o backend embutido e não baixa nada. O `uv_build` não aparece no `uv.lock` (0 ocorrências).
- O cético apontou o risco oposto (um backend baixado sem hash). Fica refutado para o caso das versões iguais. Para versões diferentes, é hipótese não testada.
- Só o advogado levantou o ponto; não houve consenso das duas lentes.
- Recomendação: uma frase no ADR 0005 dizendo que as duas versões andam juntas, e um agrupamento no Dependabot, se ele conseguir atualizar o `[build-system]`. Sem teste novo.

### P6. Itens da S5 que as lentes levantaram
- Workflow de release: construir uma vez, varrer, publicar exatamente o digest varrido, `packages: write` só nesse job, attestation de proveniência e tag protegida. Hoje nada disso existe. Entra na S5.
- Quando o PHParrot passa a consumir a imagem do GHCR: sem isso, a CI daqui e a de lá duplicam o trabalho e divergem. Entra na S5.

## Hipóteses refutadas

- `uv_build` baixado sem hash: refutada para versões iguais (build offline funcionou).
- Trivy não cobre o `uv.lock`: refutada (`trivy fs` lê o `uv.lock` e reporta 0).

## Hipóteses não testadas

- O título do CVE-2026-76844 na saída do Trivy fala de webpack, não de zlib. Não consegui conferir no tracker do Debian. A correção `deb13u1` existe no índice `stable-security`, mas não confirmei que ela trata exatamente esse CVE.
- CodeQL e todo o comportamento dentro do GitHub Actions (permissões, `security-events: write`, SARIF, checks obrigatórios): nada disso roda neste ambiente.
- `uv_build` com versão diferente da do `uv`: não testei se ele baixa o backend e como o `uv.lock` o trata.
- Todo o modelo de ameaça do MCP: não há MCP, não há FastMCP instalado e não li a documentação atual dele.
- Reprodutibilidade do build com `apt-get install --only-upgrade`: o resultado depende do estado do índice do Debian no dia.

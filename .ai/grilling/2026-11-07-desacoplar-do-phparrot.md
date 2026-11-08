# Grilling S5: desacoplar do PHParrot

Alvo: o plano de separar o gateway do PHParrot, proposto pelo orquestrador e aprovado em princípio pelo Maintainer. O grilling serve para achar os buracos antes de implementar.
Princípio do plano: o PHParrot não sabe que existe Python, FastAPI ou Ollama. Ele conhece só o contrato HTTP (formato da OpenAI) e uma imagem por digest.
Método: li o PHParrot (somente leitura, `main` em `864751c`) e medi o que dava para medir. Um revisor cético de cadeia de suprimentos, release e contrato, e um advogado do consumidor e do desenvolvedor local, julgaram cada item do plano e apontaram os buracos, sem ver a opinião um do outro.
Regra de aceite sem o Maintainer: consenso, severidade baixa ou média, dentro do contrato e do teto. O resto fica pendente. O plano já tem aprovação em princípio, mas mudar um item dele é decisão do Maintainer.
Nada foi implementado.

## O que foi medido

- **O PHParrot não consome esta imagem hoje.** Ele constrói a própria cópia: `terraform/main.tf:12` (contexto `docker/gateway`) e `:237-249` (`docker_image "gateway"` com `build` e `triggers` pelo hash dos arquivos).
- **O Dockerfile de uma linha não passa no Trivy de configuração.** Testei `trivy config --severity CRITICAL,HIGH` (o critério do `containers.yml:130-163` do PHParrot) sobre um Dockerfile só com o `FROM`: `DS-0002 (HIGH): Specify at least 1 USER command`. Com uma segunda linha, `USER 10002:10002`, dá 0 problemas. O `hadolint` com a config do PHParrot não imprimiu nada nas duas versões.
- **Dev sem rede, a parte do `docker build`.** Subi um registro local, publiquei a imagem, apaguei a tag local e construí um Dockerfile `FROM localhost:5000/llm-gateway:0.1.0@sha256:…`: com a imagem fora do cache, o build puxou do registro. Com a imagem em cache e o registro parado, o mesmo Dockerfile construiu sem erro, com e sem `--pull=false`. A parte do Terraform (provider `docker_image`) não foi testada.
- **O `docs/openapi.json` publicado não tem as respostas.** Para o chat declara só `200` com schema vazio (`{}`). Não há resposta de erro, schema de erro, enum de `code` nem cabeçalho `Retry-After`. `components.schemas` só tem entrada: `EsquemaJson`, `FormatoDeResposta`, `Mensagem`, `Pedido`. O `GET /v1/models` e o `/health` têm schema genérico.
- **O PHParrot monta as respostas à mão.** `tests/Feature/GeradorDeTextosTest.php` define `respostaDoChat()` e `erroDoGateway()` e usa `Http::fake`. O `GeradorGateway.php` lê só `choices.0.message.content`, `error.code` (validado por `^[a-z_]{1,40}$`, fora disso vira `desconhecido`) e `Retry-After`.
- **A versão do OpenAPI não vem do pacote.** `app.py:37` chama `FastAPI(title=…)` sem `version=`. O `info.version` do `openapi.json` (`0.1.0`) é o padrão do FastAPI e continuaria `0.1.0` na `v0.2.0`.
- **A imagem final não carrega o `openapi.json`.** O Dockerfile não copia `docs/`.
- **Acoplamento do lado do PHParrot:** `.lintstagedrc.mjs:30` (roda `docker build --target teste docker/gateway`), `.gitignore:36`, `.husky/check-comentarios.test.mjs:123-146` (caminhos `docker/gateway/…` como exemplo), as regras de Python do `check-comentarios.mjs`, `gateway.yml`, o bloco `uv` e o `ignore` do `python` em `dependabot.yml:31-70`, a matriz `alvo: [php, whisper, nginx, gateway]` do `containers.yml`, e referências em 9 arquivos de docs.

## Aceito por consenso

### Sobre o contrato e a versão
- **H3 (média): o contrato de implantação também é contrato.** Está fora do OpenAPI: os nomes `GATEWAY_*` (`terraform/main.tf:255-287`), a porta 8000, rodar como 10002 com `read_only` e `/tmp` em tmpfs, e o `/health`. Renomear `GATEWAY_TOKEN_ARQUIVO` quebra o PHParrot e todo teste continua verde.
  - Regra de versão proposta: enquanto a versão é `0.y`, sobe o **minor** para qualquer mudança de contrato, e o **patch** é seguro. Conta como contrato: o OpenAPI, a tabela de erros e de limites de `docs/api.md`, uma validação mais estrita (como a F6), um `code` novo num caminho existente (o PHParrot trata `code` fora da lista como `desconhecido`), as variáveis `GATEWAY_*`, a porta, o uid e a exigência de sistema de arquivos só leitura. A partir da 1.0, semver normal.
  - Onde: uma seção em `docs/api.md`.
- **H4 (média): visibilidade do GHCR.** Pacote público, porque o repositório é público, a imagem não tem segredo e ninguém precisa de credencial no CI, no dev nem no Terraform. Risco: a primeira publicação pode nascer privada. Proposta: `LABEL org.opencontainers.image.source=https://github.com/caiobarilli/llm-gateway` no Dockerfile. Aceite: `docker logout ghcr.io && docker pull ghcr.io/caiobarilli/llm-gateway:0.1.0@sha256:…` funciona sem credencial, antes de o PHParrot fixar o digest. A visibilidade é do pacote: se for preciso corrigir na interface do GitHub, não exige tag nova.
- **H5 (média): rollback e dev sem rede.** Nunca mover nem sobrescrever uma tag, e sem tag `latest`. O workflow recusa publicar se a tag já existe, e a regra de tag é `v*`. Rollback é um PR no PHParrot que volta o digest anterior (digest é imutável). A versão ruim ganha uma nota na release. O build do Dockerfile com digest em cache funciona sem rede (medido). O `docker pull` da primeira vez vira pré-requisito documentado.
- **H6 (média): `gateway_imagem`.** Um `docker_image` com `build` não serve para uma imagem só local, porque o provider tenta puxá-la. Desenho: `docker_image` com `count` quando a variável é nula, e `data "docker_image"` quando ela vem preenchida, com um `local.gateway_imagem_id` alimentando o container, e uma saída que mostra qual imagem está em uso, para o dev não esquecer o override. Se a imagem local não existir, o `plan` falha, e esse é o comportamento certo. **Não testado**: não rodei Terraform.
- **H7 (baixa): nomes.** `phparrot-gateway` (container, DNS, caminho do segredo, `config/phparrot.php:24-25`) é nome do lado do consumidor e fica. O gateway não tem padrão para o caminho do segredo (`GATEWAY_TOKEN_ARQUIVO` é obrigatória), então não há acoplamento. Uma frase na doc: "o container `phparrot-gateway` roda a imagem `llm-gateway`". O `title` do OpenAPI ainda diz `phparrot-gateway`; a F2 cobre.
- **H8 (média): o job de release.** Um job só, com `packages: write` apenas nele: construir a imagem final e carregá-la, varrê-la com o Trivy na mesma versão e com as mesmas flags do PHParrot (`CRITICAL,HIGH`, `ignore-unfixed`, `exit-code 1`), publicar **exatamente o digest varrido**, escrever o digest no resumo da release e anexar o SBOM. Regra de proteção na tag `v*`. Sem `pip-audit` (o Trivy lê o `uv.lock` e as `dist-info` do `.venv`). CodeQL não bloqueia a release.
- **H9 (baixa): o hook do PHParrot.** `DIRETIVA_PYTHON`, `analisarPython` e os exemplos `.py` de `check-comentarios.test.mjs:123-146` ficam sem arquivo para checar. Saem no mesmo commit que remove o Python.
- **H10 (alta): a ordem do item 8 deixa commits quebrados.** Com o `FROM` de uma linha, `.lintstagedrc.mjs:30` (`--target teste`) quebra o pre-commit, e o `gateway.yml` deixa o CI vermelho. O primeiro commit no PHParrot é **atômico**: Dockerfile novo, remoção da regra do lint-staged, remoção do `gateway.yml`, do bloco `uv` e do `ignore` do `python` do `dependabot.yml` (regra morta com um `FROM` só), e da linha do `.gitignore`.
- **Novo, medido: o Dockerfile do PHParrot tem duas linhas, não uma.** `FROM ghcr.io/caiobarilli/llm-gateway:0.1.0@sha256:…` e `USER 10002:10002`, porque o Trivy de configuração dá `DS-0002 (HIGH)` sem `USER`.
- **Novo, consenso das duas lentes: a `v0.1.0` precisa passar no Trivy antes de o digest ser fixado.** Com o `FROM` fixado numa imagem que já nasce vulnerável (o `zlib1g` da S2), o Dependabot e o Trivy do PHParrot ficam vermelhos. A F11 é pré-requisito da release.

## Pendente do Maintainer

### P12 (alta). O teste de contrato do item 7: de onde vêm as respostas e quem o atualiza
As duas lentes concordam que o item 7 **como está escrito não funciona**: o `openapi.json` publicado não tem as respostas, e uma cópia versionada no PHParrot não muda no PR do Dependabot (o Dependabot só muda o `FROM`), então o teste continuaria verde sobre o contrato velho. Divergem no remédio.
- **Advogado do consumidor:** cortar o item 7 como escrito. Os fakes de `GeradorDeTextosTest.php` ficam à mão, sem gerador (seria complexidade nova). A guarda do contrato mora no gateway, num teste dourado (`gerar() == docs/openapi.json`, da F21-C), e a nota da release traz uma linha "Contrato: inalterado" ou "Contrato: mudou". O PR do Dependabot é o ponto de revisão. Sem cópia no PHParrot. Enriquecer o OpenAPI só com o que o consumidor lê (`choices[0].message.content`, `error.code`, `Retry-After` no 503).
- **Cético:** manter a guarda automática. A imagem copia o `openapi.json` (`COPY docs/openapi.json`; o `.dockerignore` não exclui `docs/`). Na matriz `gateway` do `containers.yml` do PHParrot, um passo extrai o arquivo da imagem fixada (`docker run --rm --entrypoint cat … /app/openapi.json | diff - <cópia>`) e falha no PR do Dependabot até alguém atualizar a cópia. O caminho da cópia entra em `paths:` do `containers.yml`. Baixar o arquivo da tag (opção b do brief) é pior: a tag git pode ser movida, o digest não.
- **Síntese minha, não julgada pelas lentes:** a imagem carrega o `openapi.json`, e a CI do PHParrot o extrai da imagem fixada e **afirma o que o `GeradorGateway` precisa** (a rota existe, o enum de `code` contém os códigos que ele mapeia, a resposta do chat traz os campos que ele lê, o 503 traz `Retry-After`), sem cópia versionada para atualizar à mão. Falha no PR do Dependabot se a imagem nova mudar algo que o consumidor usa.
- Vale para qualquer opção: o OpenAPI precisa antes das respostas (modelo da `chat.completion`, modelo do erro com enum de `code`, `Retry-After` no 503) e do teste `gerar() == docs/openapi.json` com o `COPY docs/openapi.json` no estágio `teste` (F21-C). Isso entra antes da `v0.1.0`, porque o `openapi.json` da tag é "o contrato publicado daquela versão".
- Recomendação: a síntese. O contrato que o PHParrot de fato usa passa a ser verificado automaticamente, e não há terceiro arquivo para atualizar à mão. Se o Maintainer preferir o mais simples, o do advogado (nota de release e revisão do PR) cumpre o princípio com menos peças.

### P13 (média). Trivy e SBOM do gateway na matriz do `containers.yml` do PHParrot (item 4 do plano)
O plano diz que eles continuam, "escaneando a imagem usada de fato". As duas lentes veem o mesmo problema: o cron semanal (`containers.yml:16-17`, `ignore-unfixed`, `exit-code 1`) fica vermelho a cada CVE nova na imagem fixada, e o PHParrot não corrige isso sozinho, só trocando o `FROM`.
- Advogado: tirar o `gateway` das duas matrizes (`imagens` e `sarif`) e reescanear a última tag por cron no llm-gateway. Se o Maintainer quiser manter no PHParrot, que seja só o Trivy.
- Cético: o llm-gateway faz um Trivy semanal do último release e solta um patch sempre que houver correção, com o Dependabot docker acompanhando a imagem base.
- Recomendação: manter só o Trivy de imagem no PHParrot (a razão do plano, escanear a imagem realmente usada), tirar o SBOM de lá (ele vai anexado à release), e o llm-gateway reescaneia a última tag toda semana e solta o patch. Um cron vermelho passa a significar "atualize o `FROM`", o que o Dependabot já abre como PR. Fica decisão do Maintainer porque muda o item 4.

### P14 (média). Attestation de proveniência
- Cético: publicar com `attest-build-provenance` e verificar no PHParrot (`gh attestation verify oci://…@sha256:… --repo caiobarilli/llm-gateway`). Se ninguém vai verificar, cortar. Hoje Terraform e Docker não verificam nada.
- Advogado: fica para depois.
- Recomendação: depois. Sem um verificador no consumidor, a attestation fica só no papel. Entra junto com um passo de verificação no PHParrot, ou não entra. Liga-se à P3 da S2.

### Itens que só uma lente levantou (recomendo aceitar)
- **`info.version` do OpenAPI vem do pacote** (cético). `app.py:37` não passa `version=`. Proposta: `version=importlib.metadata.version("llm-gateway")`, e a release falha se a tag, o `pyproject.toml` e o `info.version` divergirem. Baixa.
- **O pedido não está no contrato** (cético). `EsquemaJson.schema` é um objeto livre (`openapi.json:27-31`), então a lista de palavras-chave da F6 não aparece nele. Se uma versão nova tirar uma palavra que o `PromptDeItem::esquema()` usa, o gateway passa a responder 400 e o teste do PHParrot continua verde. Proposta: exportar `x-palavras-chave` no OpenAPI, e o PHParrot testa que as chaves do esquema dele estão dentro dessa lista. Média. A F6 já exige, do lado do gateway, um teste com o schema exato do PHParrot, o que cobre metade do risco.
- **O primeiro `apply` depois da migração recria o container** (advogado), porque o `image_id` muda. A doc do PHParrot avisa, como `docs/configuracao.md:139` já faz para outras recriações. Baixa.
- **Fechar o PR do Dependabot da versão ruim** (cético): ele não reabre a mesma versão. Não testado.

## Ordem recomendada do plano, com o critério de aceite de cada etapa
As duas lentes recomendam a mesma ordem, com pequenas diferenças que a lista abaixo já incorpora.

**No llm-gateway, antes do PHParrot:**
1. Identidade neutra e segurança do contrato (F1, F2, F4, F5, F6, F7, F8). Aceite: o gate verde, `grep -rni phparrot src tests tools Dockerfile pyproject.toml .github` sem resultado, `openapi.json` regenerado.
2. OpenAPI completo (respostas, erro com enum de `code`, `Retry-After`, `info.version` do pacote) e o teste `gerar() == docs/openapi.json`. Aceite: o teste falha se alguém mexer na rota sem regenerar.
3. Imagem: `--locked` (F12), `apt-get install --only-upgrade zlib1g` (F11), `LABEL org.opencontainers.image.source`, `COPY docs/openapi.json`. Aceite: Trivy de imagem com `CRITICAL,HIGH`, `ignore-unfixed` e `exit-code 1` sai com 0, e o Trivy de configuração também.
4. Workflow de release e CI de segurança, no formato decidido em P3 e P14. Aceite: um ensaio numa tag `v0.0.1-rc` publica o digest varrido no resumo, e uma segunda publicação da mesma tag é recusada.
5. `v0.1.0`. Aceite: `docker logout ghcr.io && docker pull …@sha256:…` anônimo funciona, a nota da release traz o digest e a linha de contrato.

**No PHParrot, um branch, depois da `v0.1.0`:**
6. Commit atômico: `docker/gateway/Dockerfile` de duas linhas (`FROM …@sha256:…` e `USER 10002:10002`), remoção da regra do lint-staged, do `gateway.yml`, do bloco `uv`, do `ignore` do `python` e da linha do `.gitignore`. Aceite: o hook de pre-commit real passa, o CI fica verde, `terraform plan` não mostra mudança além do `image_id`.
7. A guarda do contrato (P12). Aceite: ela falha se a imagem fixada mudar algo que o `GeradorGateway` usa.
8. `gateway_imagem` com `data "docker_image"`. Aceite: `terraform plan` passa com e sem a variável, e `apply` com `llm-gateway:local` sobe o container.
9. Remover o Python do repositório, as regras de Python do hook e os exemplos `.py` do teste do hook. Escrever o ADR 0014 (o que muda em relação ao 0013). README e docs apontam para o llm-gateway. Aceite: `grep -ri gateway` só acha o lado do consumidor, e o hook segue verde sem nenhum `.py` no repositório.
10. O Maintainer aprova e só então apaga o branch local `split/llm-gateway`. É a única cópia da árvore já separada; a história também existe nos commits que tocam `docker/gateway/` do PHParrot.

## Hipóteses não testadas

- A semântica do provider `docker_image` do Terraform com imagem local, o `data "docker_image"` e o `apply -replace`: não rodei Terraform.
- A visibilidade padrão de um pacote novo no GHCR e o efeito do `LABEL org.opencontainers.image.source`.
- Se o Dependabot reabre o PR da mesma versão depois de fechado.
- O comportamento do build do PHParrot sem rede **dentro do Terraform**. O `docker build` com a imagem em cache e o registro parado foi medido, com um registro local no lugar do GHCR.
- A verificação de attestation (`gh attestation verify`): não há attestation publicada.
- O efeito real do cron semanal vermelho sobre o fluxo do Maintainer: raciocinado, não observado.

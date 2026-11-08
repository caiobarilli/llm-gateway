# CI de segurança e release por tag

## Contexto

O `ci.yml` só constrói o estágio `teste`. A imagem final, a que vai para o GHCR, nunca era construída nem varrida, e não havia Dependabot nem release. O consumidor fixa a imagem por digest, então o digest que ele fixa precisa ser o que foi varrido. Medido na S2 e repetido nesta rodada: o Trivy lê o `uv.lock` (`trivy fs`, tipo `uv`), então o `pip-audit` não acrescenta nada.

## Decisão

CI de segurança (`.github/workflows/seguranca.yml`):

- Três jobs, com o Trivy `v0.76.1` e as flags do PHParrot (`CRITICAL,HIGH`, `ignore-unfixed`, `exit-code 1`): a imagem final, o Dockerfile (`config`) e o `uv.lock` (`fs`, só `vuln`). A imagem é construída sem cache, porque uma camada de `apt-get` em cache esconderia uma correção nova do Debian.
- Roda em PR e em push no `main` que mexem em `Dockerfile`, `pyproject.toml`, `uv.lock`, `docs/openapi.json` ou no workflow, e toda segunda-feira por cron (e por `workflow_dispatch`). Assim um CVE novo da base não derruba um PR que não tem relação.
- Sem `pip-audit` e sem `uv lock --check` (o `--locked` do Dockerfile cobre). O SBOM sai só na release. CodeQL (default setup) e o ruleset da `main` são ligados pelo Maintainer na interface do GitHub, fora do código, e o CodeQL não bloqueia.
- O cron vermelho avisa o Maintainer pelas notificações do GitHub (não observado: nada disso roda fora do GitHub). Ele significa "atualize o `FROM`", e o Dependabot já abre esse PR.

Dependabot (`.github/dependabot.yml`): `uv`, `docker` e `github-actions`, toda segunda-feira, e o bloco de `docker` ignora `semver-minor` e `semver-major` do `python` (`.ai/pitfalls.md`). O Dependabot pode subir o `uv` da imagem sem o `uv_build` (ADR 0005): quem revisa o PR sobe os dois juntos.

Release (`.github/workflows/release.yml`), disparada por uma tag `vX.Y.Z` ou `vX.Y.Z-rcN`, num job só com `packages: write`:

1. Valida a tag. Em `vX.Y.Z`, a tag, o `pyproject.toml` e o `info.version` do `/app/openapi.json` da imagem precisam ser o mesmo número. Tag `-rc` é ensaio: não confere a versão, é publicada como pré-lançamento.
2. Constrói a imagem final sem cache, sem proveniência e sem SBOM do buildx (um manifesto de imagem simples, não um índice), e a empurra para um `registry:2` local do job (`localhost:5000`).
3. Varre esse digest com o Trivy, com bloqueio, e gera o SBOM CycloneDX do mesmo digest.
4. Só então copia o digest varrido para `ghcr.io/caiobarilli/llm-gateway:X.Y.Z` com `docker buildx imagetools create --prefer-index=false` e confere que o digest publicado é igual ao varrido.
5. Cria a release com o SBOM anexado e o digest no texto.

Regras de tag: nunca mover nem sobrescrever (o job recusa publicar se a tag de imagem já existe), sem tag `latest`. Voltar atrás é apontar o consumidor para o digest da versão anterior, que é imutável. A versão ruim ganha uma nota na release. O pacote no GHCR é público, porque o repositório é público e a imagem não tem segredo. A primeira publicação pode nascer privada, e a visibilidade se corrige na interface do GitHub sem tag nova. O `LABEL org.opencontainers.image.source` liga o pacote ao repositório.

Attestation de proveniência fica para depois: sem um verificador no consumidor, ela fica só no papel.

## Consequência

- O digest que o consumidor fixa é o que passou pelo Trivy, e o `gh release` o mostra.
- A release depende de rede e do índice do Debian do dia (ADR 0005). Uma base que ainda traz um CVE `HIGH` com correção bloqueia a release até o `FROM` subir.
- Achado do ensaio local (`registry:2` nas portas 5000 e 5001): o `docker buildx imagetools create` sem `--prefer-index=false` embrulha a imagem num índice OCI, e o digest publicado muda (`5a32ed51…` no lugar de `c0ab30df…`). Com a flag, a cópia é fiel, e o `publicar.sh` confere a igualdade.
- Não testado, porque só roda no GitHub: o login e o push no GHCR, `gh release create`, o `registry:2` como serviço do job, o `trivy-action`, as permissões do job, a notificação do cron e a visibilidade do pacote.

## Evidência

- `.github/workflows/seguranca.yml`, `.github/workflows/release.yml` e `.github/dependabot.yml`. `.github/scripts/validar-tag.sh`, `conferir-versao-da-imagem.sh`, `publicar.sh` e `nota-da-release.sh` (os mesmos scripts que o ensaio local rodou).
- Ensaio local: `validar-tag.sh` aceita `v0.0.1-rc` e `v0.1.0` e recusa `v0.1.1` (diverge do `pyproject.toml`), `v1.0`, `v0.1.0-beta` e `0.1.0`. `publicar.sh` copiou `localhost:5000/llm-gateway@sha256:c0ab30df…` para `localhost:5001/llm-gateway:0.0.1-rc` com o mesmo digest, recusou a segunda publicação da mesma tag e recusou um digest diferente do varrido.
- `Dockerfile:46` (`LABEL`) e `:59` (o `openapi.json` na imagem).

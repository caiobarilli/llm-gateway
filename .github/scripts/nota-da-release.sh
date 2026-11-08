#!/bin/sh
set -eu

cat > "$ARQUIVO" <<NOTA
Imagem publicada: \`$IMAGEM:$VERSAO@$DIGEST\`

\`\`\`bash
docker pull $IMAGEM:$VERSAO@$DIGEST
\`\`\`

Este é o digest que o Trivy varreu (\`CRITICAL,HIGH\`, \`ignore-unfixed\`, sem achados) antes da publicação. O SBOM CycloneDX anexado descreve esse mesmo digest. A tag não é movida nem sobrescrita: para voltar, aponte o consumidor para o digest da versão anterior.

O contrato desta versão está em \`/app/openapi.json\` da imagem e em \`docs/openapi.json\` da tag.
NOTA

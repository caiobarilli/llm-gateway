#!/bin/sh
set -eu

if docker buildx imagetools inspect "$DESTINO" > /dev/null 2>&1; then
  echo "a tag já existe e nunca é movida: $DESTINO" >&2
  exit 1
fi

docker buildx imagetools create --prefer-index=false --tag "$DESTINO" "$ORIGEM"

publicado=$(docker buildx imagetools inspect "$DESTINO" --format '{{json .Manifest}}' | python3 -c 'import json, sys; print(json.load(sys.stdin)["digest"])')
if [ "$publicado" != "$DIGEST" ]; then
  echo "o digest publicado ($publicado) não é o varrido ($DIGEST)" >&2
  exit 1
fi

echo "digest=$publicado" >> "${GITHUB_OUTPUT:-/dev/stdout}"

#!/bin/sh
set -eu

publicada=$(docker run --rm --entrypoint cat "$REFERENCIA" /app/openapi.json | python3 -c 'import json, sys; print(json.load(sys.stdin)["info"]["version"])')
if [ "$publicada" != "$VERSAO" ]; then
  echo "info.version da imagem ($publicada) diverge da tag ($VERSAO)" >&2
  exit 1
fi

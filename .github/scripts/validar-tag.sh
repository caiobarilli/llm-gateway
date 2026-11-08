#!/bin/sh
set -eu

padrao='^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]*)?$'
if ! printf '%s\n' "$TAG" | grep -Eq "$padrao"; then
  echo "tag fora do padrão vX.Y.Z ou vX.Y.Z-rcN: $TAG" >&2
  exit 1
fi

versao=${TAG#v}
preliminar=false
case "$versao" in
  *-rc*) preliminar=true ;;
esac

if [ "$preliminar" = false ]; then
  pacote=$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
  if [ "$pacote" != "$versao" ]; then
    echo "a tag ($versao) e o pyproject.toml ($pacote) divergem" >&2
    exit 1
  fi
fi

{
  echo "versao=$versao"
  echo "preliminar=$preliminar"
} >> "${GITHUB_OUTPUT:-/dev/stdout}"

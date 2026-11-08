import ast
import io
import re
import sys
import tokenize
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import NamedTuple

DIRETIVA = re.compile(r"^(type:|noqa(:|\s|$))")
PASTAS_PADRAO = ("src", "tests", "tools")
LIMITE_DO_TRECHO = 120


class Achado(NamedTuple):
    linha: int
    motivo: str
    trecho: str


def achar_comentarios(fonte: str) -> Iterator[Achado]:
    linhas = fonte.splitlines()
    for ficha in tokenize.generate_tokens(io.StringIO(fonte).readline):
        if ficha.type != tokenize.COMMENT:
            continue

        if DIRETIVA.match(ficha.string[1:].strip()):
            continue

        numero = ficha.start[0]
        yield Achado(numero, "comentário", linhas[numero - 1].strip())


def achar_docstrings(fonte: str) -> Iterator[Achado]:
    linhas = fonte.splitlines()
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue

        if ast.get_docstring(no, clean=False) is None:
            continue

        numero = no.body[0].lineno
        yield Achado(numero, "docstring", linhas[numero - 1].strip())


def verificar(fonte: str) -> list[Achado]:
    return sorted([*achar_comentarios(fonte), *achar_docstrings(fonte)])


def arquivos_python(pastas: Sequence[Path]) -> Iterator[Path]:
    for pasta in pastas:
        if pasta.is_file():
            yield pasta
        else:
            yield from sorted(pasta.rglob("*.py"))


def principal(argumentos: Sequence[str]) -> int:
    pastas = [Path(argumento) for argumento in (argumentos or PASTAS_PADRAO)]
    falhas = 0

    for arquivo in arquivos_python(pastas):
        try:
            achados = verificar(arquivo.read_text(encoding="utf-8"))
        except (SyntaxError, tokenize.TokenError) as erro:
            print(f"sem_comentario: {arquivo} não foi possível analisar: {type(erro).__name__}", file=sys.stderr)
            falhas += 1
            continue

        for achado in achados:
            print(
                f"sem_comentario: {arquivo}:{achado.linha} {achado.motivo}: {achado.trecho[:LIMITE_DO_TRECHO]}",
                file=sys.stderr,
            )
            falhas += 1

    if falhas:
        print("Só # type: e # noqa são aceitos. O porquê vai em .ai/adr/ e o uso em docs/.", file=sys.stderr)

    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(principal(sys.argv[1:]))

from pathlib import Path

import pytest
from sem_comentario import principal, verificar

RAIZ = Path(__file__).resolve().parent.parent


def test_comentario_sozinho_na_linha_e_achado() -> None:
    achados = verificar("x = 1\n# explica o que faz\ny = 2\n")

    assert [(achado.linha, achado.motivo) for achado in achados] == [(2, "comentário")]


def test_comentario_no_fim_da_linha_e_achado() -> None:
    achados = verificar("x = 1  # explica\n")

    assert [(achado.linha, achado.motivo) for achado in achados] == [(1, "comentário")]
    assert achados[0].trecho == "x = 1  # explica"


def test_cerquilha_dentro_de_string_nao_e_comentario() -> None:
    fonte = (
        'a = "texto # com cerquilha"\n'
        "b = 'outro # aqui'\n"
        'c = f"{a} # no f-string"\n'
        'd = """linha 1\n# linha 2 dentro de string\n"""\n'
        'e = "aspas \\" # escapadas"\n'
    )

    assert verificar(fonte) == []


def test_type_e_noqa_sao_aceitos() -> None:
    fonte = (
        "a: int = 'x'  # type: ignore[assignment]\n"
        "import os  # noqa\n"
        "import sys  # noqa: F401\n"
        "import re  # noqa:F401\n"
        "# type: ignore\n"
    )

    assert verificar(fonte) == []


def test_diretiva_so_vale_no_comeco_do_comentario() -> None:
    achados = verificar("x = 1  # isto não é noqa\ny = 2  # type_ignore\n")

    assert [achado.linha for achado in achados] == [1, 2]


def test_docstring_de_modulo_classe_e_funcao_e_achado() -> None:
    fonte = (
        '"""Módulo."""\n\n\n'
        "class A:\n"
        '    """Classe."""\n\n'
        "    def f(self) -> None:\n"
        '        """Função."""\n\n\n'
        "async def g() -> None:\n"
        '    """Async."""\n'
    )

    achados = verificar(fonte)

    assert [(achado.linha, achado.motivo) for achado in achados] == [
        (1, "docstring"),
        (5, "docstring"),
        (8, "docstring"),
        (12, "docstring"),
    ]


def test_string_que_nao_e_docstring_passa() -> None:
    assert verificar('def f() -> str:\n    x = 1\n    return """texto\nlongo"""\n') == []


def test_principal_falha_e_aponta_arquivo_e_linha(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "limpo.py").write_text("x = 1  # noqa\n")
    (tmp_path / "sujo.py").write_text("x = 1\ny = 2  # explica\n")

    codigo = principal([str(tmp_path)])

    erro = capsys.readouterr().err
    assert codigo == 1
    assert f"{tmp_path / 'sujo.py'}:2 comentário: y = 2  # explica" in erro
    assert "limpo.py" not in erro


def test_principal_passa_com_pasta_limpa(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1  # type: ignore\n")

    assert principal([str(tmp_path)]) == 0


def test_principal_falha_com_arquivo_que_nao_compila(tmp_path: Path) -> None:
    (tmp_path / "quebrado.py").write_text("def f(:\n")

    assert principal([str(tmp_path)]) == 1


def test_o_proprio_repositorio_esta_limpo() -> None:
    assert principal([str(RAIZ / "src"), str(RAIZ / "tests"), str(RAIZ / "tools")]) == 0

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, autorizacao


def assert_recusado(resposta_status: int, cabecalhos: dict[str, str], corpo: dict[str, dict[str, str]]) -> None:
    assert resposta_status == 401
    assert cabecalhos["www-authenticate"] == "Bearer"
    assert corpo["error"]["code"] == "invalid_api_key"
    assert corpo["error"]["type"] == "invalid_request_error"


def test_sem_token_responde_401(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/models")

    assert_recusado(resposta.status_code, dict(resposta.headers), resposta.json())


def test_token_errado_responde_401(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/models", headers=autorizacao("b2" * 32))

    assert_recusado(resposta.status_code, dict(resposta.headers), resposta.json())


@pytest.mark.parametrize(
    "cabecalho",
    [f"Basic {TOKEN}", TOKEN, "Bearer", "Bearer ", f"Bearer  {TOKEN}", f"Bearer {TOKEN} extra", "Bearer tok\u00e9n"],
)
def test_cabecalho_malformado_responde_401(cliente: TestClient, cabecalho: str) -> None:
    resposta = cliente.get("/v1/models", headers={b"Authorization": cabecalho.encode("latin-1")})

    assert_recusado(resposta.status_code, dict(resposta.headers), resposta.json())


def test_token_certo_passa_com_esquema_em_qualquer_caixa(cliente: TestClient) -> None:
    assert cliente.get("/v1/models", headers=autorizacao()).status_code == 200
    assert cliente.get("/v1/models", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


def test_espacos_e_quebra_de_linha_no_arquivo_sao_ignorados(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_text(f"  {TOKEN}\n")

    assert cliente.get("/v1/models", headers=autorizacao()).status_code == 200


def test_rotacao_no_lugar_vale_sem_reiniciar(cliente: TestClient, arquivo_do_token: Path) -> None:
    novo = "c3" * 32
    assert cliente.get("/v1/models", headers=autorizacao()).status_code == 200

    with arquivo_do_token.open("w") as arquivo:
        arquivo.write(novo)

    assert cliente.get("/v1/models", headers=autorizacao()).status_code == 401
    assert cliente.get("/v1/models", headers=autorizacao(novo)).status_code == 200


def assert_indisponivel(cliente: TestClient, cabecalhos: dict[str, str] | None = None) -> None:
    resposta = cliente.get("/v1/models", headers=autorizacao() if cabecalhos is None else cabecalhos)

    assert resposta.status_code == 503
    assert resposta.json()["error"]["code"] == "token_indisponivel"
    assert resposta.json()["error"]["type"] == "server_error"


def test_arquivo_ausente_fecha_com_503(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.unlink()

    assert_indisponivel(cliente)


def test_arquivo_vazio_fecha_com_503(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_text(" \n")

    assert_indisponivel(cliente)


def test_arquivo_ilegivel_fecha_com_503(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.unlink()
    arquivo_do_token.mkdir()

    assert_indisponivel(cliente)


def test_arquivo_que_nao_e_ascii_fecha_com_503(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_bytes(b"\xff\xfe")

    assert_indisponivel(cliente)


def test_sem_token_no_servidor_nem_o_token_certo_passa(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_text("")

    assert_indisponivel(cliente, autorizacao(""))
    assert_indisponivel(cliente, {"Authorization": "Bearer "})
    assert_indisponivel(cliente, autorizacao())


def test_token_de_31_caracteres_fecha_com_503_e_o_de_32_passa(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_text("k" * 31)
    assert_indisponivel(cliente, autorizacao("k" * 31))

    arquivo_do_token.write_text("k" * 32)
    assert cliente.get("/v1/models", headers=autorizacao("k" * 32)).status_code == 200


def test_o_tamanho_conta_depois_do_strip(cliente: TestClient, arquivo_do_token: Path) -> None:
    arquivo_do_token.write_text(f"  {'k' * 31}  \n")

    assert_indisponivel(cliente, autorizacao("k" * 31))


def test_token_curto_registra_o_motivo_sem_o_token(
    cliente: TestClient, arquivo_do_token: Path, caplog: pytest.LogCaptureFixture
) -> None:
    curto = "segredo-curto"
    arquivo_do_token.write_text(curto)
    caplog.set_level(logging.DEBUG)

    resposta = cliente.get("/v1/models", headers=autorizacao(curto))

    assert resposta.status_code == 503
    assert "token indisponível: token curto" in caplog.text
    assert curto not in caplog.text
    assert curto not in resposta.text


def test_token_nao_aparece_no_log_nem_na_resposta(
    cliente: TestClient, arquivo_do_token: Path, caplog: pytest.LogCaptureFixture
) -> None:
    errado = "d4" * 32
    caplog.set_level(logging.DEBUG)

    respostas = [
        cliente.get("/v1/models", headers=autorizacao()),
        cliente.get("/v1/models", headers=autorizacao(errado)),
        cliente.get("/v1/models", headers={"Authorization": f"Basic {TOKEN}"}),
    ]
    arquivo_do_token.unlink()
    respostas.append(cliente.get("/v1/models", headers=autorizacao()))

    assert "autenticação recusada" in caplog.text
    assert "token indisponível" in caplog.text
    for segredo in (TOKEN, errado):
        assert segredo not in caplog.text
        for resposta in respostas:
            assert segredo not in resposta.text
            assert segredo not in str(dict(resposta.headers))

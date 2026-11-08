import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import autorizacao


def test_health_responde_ok_sem_token(cliente: TestClient) -> None:
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_documentacao_automatica_fica_desligada(cliente: TestClient) -> None:
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).status_code == 404


@pytest.mark.parametrize("caminho", ["/health/", "/v1/models/", "/v1/chat/completions/"])
def test_barra_final_responde_404_sem_redirecionar(cliente: TestClient, caminho: str) -> None:
    resposta = cliente.get(caminho, headers={**autorizacao(), "Host": "evil.example"}, follow_redirects=False)

    assert resposta.status_code == 404
    assert "location" not in resposta.headers
    assert resposta.json()["error"]["code"] == "not_found"
    assert resposta.json()["error"]["type"] == "invalid_request_error"


def test_rota_inexistente_responde_no_formato_da_openai(cliente: TestClient) -> None:
    resposta = cliente.get("/nada")

    assert resposta.status_code == 404
    assert resposta.json()["error"]["type"] == "invalid_request_error"
    assert resposta.json()["error"]["code"] == "not_found"


def test_parametro_tipado_invalido_responde_400_no_formato_da_openai_sem_eco(app: FastAPI) -> None:
    @app.get("/teste-tipado")
    def rota_tipada(n: int) -> dict[str, int]:
        return {"n": n}

    with TestClient(app) as cliente:
        resposta = cliente.get("/teste-tipado", params={"n": "VALOR_SECRETO_DO_CLIENTE"})

    assert resposta.status_code == 400
    assert resposta.json() == {
        "error": {
            "message": "Pedido inválido.",
            "type": "invalid_request_error",
            "param": None,
            "code": "invalid_request",
        }
    }
    assert "detail" not in resposta.json()
    assert "VALOR_SECRETO_DO_CLIENTE" not in resposta.text

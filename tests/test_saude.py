from fastapi.testclient import TestClient


def test_health_responde_ok_sem_token(cliente: TestClient) -> None:
    resposta = cliente.get("/health")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_documentacao_automatica_fica_desligada(cliente: TestClient) -> None:
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).status_code == 404


def test_rota_inexistente_responde_no_formato_da_openai(cliente: TestClient) -> None:
    resposta = cliente.get("/nada")

    assert resposta.status_code == 404
    assert resposta.json()["error"]["type"] == "invalid_request_error"
    assert resposta.json()["error"]["code"] == "not_found"

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llm_gateway.app import criar_app
from llm_gateway.config import Config
from llm_gateway.erros import ErroOpenAI
from llm_gateway.modelos import exigir_modelo_permitido
from tests.conftest import MODELO, autorizacao


def test_models_lista_so_a_allowlist_no_formato_da_openai(cliente: TestClient) -> None:
    resposta = cliente.get("/v1/models", headers=autorizacao())

    assert resposta.status_code == 200
    assert resposta.json() == {
        "object": "list",
        "data": [{"id": MODELO, "object": "model", "created": 0, "owned_by": "phparrot"}],
    }


def test_models_com_dois_modelos_lista_os_dois_na_ordem(arquivo_do_token: Path) -> None:
    config = Config(arquivo_do_token, (MODELO, "qwen3:4b"), 1, "http://ollama.test:11434")

    with TestClient(criar_app(config)) as cliente:
        ids = [modelo["id"] for modelo in cliente.get("/v1/models", headers=autorizacao()).json()["data"]]

    assert ids == [MODELO, "qwen3:4b"]


def test_modelo_permitido_passa(config: Config) -> None:
    assert exigir_modelo_permitido(config, MODELO) == MODELO


@pytest.mark.parametrize("modelo", ["llama3.2:1b", "LLAMA3.2:3B", "llama3.2:3b ", "", "x" * 500])
def test_modelo_fora_da_lista_e_recusado_com_404_da_openai(config: Config, modelo: str) -> None:
    with pytest.raises(ErroOpenAI) as recusa:
        exigir_modelo_permitido(config, modelo)

    assert recusa.value.status == 404
    assert recusa.value.tipo == "invalid_request_error"
    assert recusa.value.codigo == "model_not_found"
    assert len(recusa.value.mensagem) < 200

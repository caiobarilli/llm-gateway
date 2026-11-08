import importlib.metadata
import json
from typing import Any

import pytest
from exportar_openapi import DESTINO, gerar

from llm_gateway.erros import Codigo
from llm_gateway.subconjunto import PALAVRAS_PERMITIDAS

ROTAS = {"/health", "/v1/models", "/v1/chat/completions"}
STATUS_DO_CHAT = {"200", "400", "401", "404", "413", "500", "502", "503", "504"}


@pytest.fixture(scope="module")
def contrato() -> dict[str, Any]:
    return gerar()


def test_o_openapi_publicado_e_o_que_a_factory_gera(contrato: dict[str, Any]) -> None:
    assert contrato == json.loads(DESTINO.read_text(encoding="utf-8"))


def test_a_versao_do_contrato_e_a_do_pacote(contrato: dict[str, Any]) -> None:
    assert contrato["info"]["version"] == importlib.metadata.version("llm-gateway")
    assert contrato["info"]["title"] == "llm-gateway"


def test_as_rotas_do_contrato_sao_as_tres_do_inventario(contrato: dict[str, Any]) -> None:
    assert set(contrato["paths"]) == ROTAS


def test_so_o_health_dispensa_o_token(contrato: dict[str, Any]) -> None:
    for caminho, operacoes in contrato["paths"].items():
        for operacao in operacoes.values():
            assert ("security" in operacao) == caminho.startswith("/v1/")


def test_o_enum_de_code_e_o_enum_dos_codigos_do_gateway(contrato: dict[str, Any]) -> None:
    codigos = contrato["components"]["schemas"]["Codigo"]

    assert codigos["enum"] == [codigo.value for codigo in Codigo]
    detalhe = contrato["components"]["schemas"]["DetalheDoErro"]["properties"]["code"]
    assert {"$ref": "#/components/schemas/Codigo"} in detalhe["anyOf"]
    assert {"type": "null"} in detalhe["anyOf"]


def test_o_chat_declara_a_resposta_e_todos_os_erros(contrato: dict[str, Any]) -> None:
    respostas = contrato["paths"]["/v1/chat/completions"]["post"]["responses"]

    assert set(respostas) == STATUS_DO_CHAT
    sucesso = respostas["200"]["content"]["application/json"]["schema"]
    assert sucesso == {"$ref": "#/components/schemas/RespostaDoChat"}
    for status in STATUS_DO_CHAT - {"200"}:
        assert respostas[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/CorpoDeErro"
        }


def test_o_503_traz_o_retry_after_e_o_401_traz_o_desafio(contrato: dict[str, Any]) -> None:
    for caminho in ("/v1/chat/completions", "/v1/models"):
        respostas = next(iter(contrato["paths"][caminho].values()))["responses"]

        assert respostas["401"]["headers"]["WWW-Authenticate"]["schema"] == {"type": "string"}
    chat = contrato["paths"]["/v1/chat/completions"]["post"]["responses"]
    assert chat["503"]["headers"]["Retry-After"]["schema"] == {"type": "integer"}


def test_a_resposta_do_chat_tem_os_campos_que_o_consumidor_le(contrato: dict[str, Any]) -> None:
    esquemas = contrato["components"]["schemas"]

    assert set(esquemas["RespostaDoChat"]["required"]) == {"id", "object", "created", "model", "choices", "usage"}
    assert esquemas["RespostaDoChat"]["properties"]["choices"]["items"] == {"$ref": "#/components/schemas/Escolha"}
    assert set(esquemas["Escolha"]["required"]) == {"index", "message", "finish_reason"}
    assert set(esquemas["MensagemDaResposta"]["required"]) == {"role", "content"}
    assert set(esquemas["CorpoDeErro"]["required"]) == {"error"}
    assert set(esquemas["DetalheDoErro"]["required"]) == {"message", "type", "code"}


def test_as_palavras_do_subconjunto_estao_no_contrato(contrato: dict[str, Any]) -> None:
    esquema = contrato["components"]["schemas"]["EsquemaJson"]["properties"]["schema"]

    assert esquema["x-palavras-chave"] == sorted(PALAVRAS_PERMITIDAS)

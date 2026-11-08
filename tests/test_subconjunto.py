import socket
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import OllamaFalso, resposta_do_ollama
from tests.test_chat import chat, erro, pedido

ESQUEMA_DO_CONSUMIDOR = {
    "type": "object",
    "properties": {
        "en": {"type": "string", "minLength": 1, "maxLength": 2000},
        "pt-BR": {"type": "string", "minLength": 1, "maxLength": 2000},
    },
    "required": ["en", "pt-BR"],
    "additionalProperties": False,
}
SAIDA_DO_CONSUMIDOR = '{"en": "I eat.", "pt-BR": "Eu como."}'
PROIBIDAS = [
    "$ref",
    "$defs",
    "$schema",
    "$id",
    "$anchor",
    "$dynamicRef",
    "$comment",
    "pattern",
    "patternProperties",
    "format",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "if",
    "then",
    "else",
    "dependentSchemas",
    "dependentRequired",
    "prefixItems",
    "contains",
    "uniqueItems",
    "propertyNames",
    "unevaluatedProperties",
    "additionalItems",
    "multipleOf",
    "exclusiveMinimum",
    "default",
    "examples",
]
MENSAGEM_DE_PALAVRA = "O JSON Schema do response_format usa uma palavra-chave fora do subconjunto aceito."
MENSAGEM_DE_LIMITE = "O JSON Schema do response_format passa dos limites de tamanho do subconjunto aceito."


def formato(esquema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": "item", "schema": esquema, "strict": True}}


def com_palavra_em(posicao: str, palavra: str) -> dict[str, Any]:
    folha: dict[str, Any] = {"type": "string", palavra: "x"}
    esquemas: dict[str, dict[str, Any]] = {
        "raiz": {"type": "object", palavra: "x"},
        "properties": {"type": "object", "properties": {"campo": folha}},
        "items": {"type": "array", "items": folha},
        "additionalProperties": {"type": "object", "additionalProperties": folha},
    }

    return esquemas[posicao]


def aninhar(chave: str, niveis: int) -> dict[str, Any]:
    esquema: dict[str, Any] = {"type": "string"}
    for _ in range(niveis - 1):
        esquema = {chave: {"campo": esquema}} if chave == "properties" else {chave: esquema}

    return esquema


@pytest.fixture
def servidor_interno() -> Iterator[socket.socket]:
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen()
        servidor.setblocking(False)
        yield servidor


def acessos(servidor: socket.socket) -> int:
    contagem = 0
    while True:
        try:
            conexao, _ = servidor.accept()
        except BlockingIOError:
            return contagem

        conexao.close()
        contagem += 1


def conferir_recusa(cliente: TestClient, ollama: OllamaFalso, esquema: dict[str, Any], mensagem: str) -> None:
    resposta = chat(cliente, pedido(response_format=formato(esquema)))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "schema_invalido"
    assert erro(resposta)["message"] == mensagem
    assert ollama.pedidos == []


def test_o_esquema_exato_do_consumidor_passa_e_chega_inteiro_ao_ollama(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    ollama.responder_com(**resposta_do_ollama(SAIDA_DO_CONSUMIDOR))

    resposta = chat(cliente, pedido(response_format=formato(ESQUEMA_DO_CONSUMIDOR), max_tokens=1024, temperature=0.7))

    assert resposta.status_code == 200
    assert ollama.pedidos[0]["corpo"]["format"] == ESQUEMA_DO_CONSUMIDOR


@pytest.mark.parametrize("palavra", PROIBIDAS)
@pytest.mark.parametrize("posicao", ["raiz", "properties", "items", "additionalProperties"])
def test_palavra_fora_da_lista_responde_400_em_qualquer_nivel(
    cliente: TestClient, ollama: OllamaFalso, posicao: str, palavra: str
) -> None:
    conferir_recusa(cliente, ollama, com_palavra_em(posicao, palavra), MENSAGEM_DE_PALAVRA)


@pytest.mark.parametrize("modelo", ["http://127.0.0.1:{porta}/segredo-interno", "ftp://127.0.0.1:{porta}/x"])
def test_ref_remoto_responde_400_sem_nenhum_acesso(
    cliente: TestClient, ollama: OllamaFalso, servidor_interno: socket.socket, modelo: str
) -> None:
    ref = modelo.format(porta=servidor_interno.getsockname()[1])

    conferir_recusa(cliente, ollama, {"$ref": ref}, MENSAGEM_DE_PALAVRA)
    conferir_recusa(cliente, ollama, {"type": "object", "properties": {"a": {"$ref": ref}}}, MENSAGEM_DE_PALAVRA)
    assert acessos(servidor_interno) == 0


@pytest.mark.parametrize(
    "esquema",
    [
        {"$ref": "file:///etc/hostname"},
        {"$ref": "#/$defs/texto", "$defs": {"texto": {"type": "string"}}},
        {"$ref": "#"},
    ],
)
def test_ref_local_e_de_arquivo_respondem_400(
    cliente: TestClient, ollama: OllamaFalso, esquema: dict[str, Any]
) -> None:
    conferir_recusa(cliente, ollama, esquema, MENSAGEM_DE_PALAVRA)


def test_pattern_responde_400_e_uma_propriedade_chamada_pattern_continua_valendo(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    conferir_recusa(cliente, ollama, {"type": "string", "pattern": "^(a+)+$"}, MENSAGEM_DE_PALAVRA)

    esquema = {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}
    ollama.responder_com(**resposta_do_ollama('{"pattern": "^(a+)+$"}'))

    assert chat(cliente, pedido(response_format=formato(esquema))).status_code == 200


def test_nome_de_propriedade_com_cifrao_e_com_palavra_proibida_e_so_um_nome(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    esquema = {
        "type": "object",
        "properties": {"$ref": {"type": "string"}, "format": {"type": "string"}, "allOf": {"type": "string"}},
        "required": ["$ref", "format"],
    }
    ollama.responder_com(**resposta_do_ollama('{"$ref": "a", "format": "b", "allOf": "c"}'))

    assert chat(cliente, pedido(response_format=formato(esquema))).status_code == 200


def test_valores_de_enum_e_de_const_e_itens_de_required_sao_dado_e_nao_schema(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    esquema = {
        "type": "object",
        "properties": {
            "a": {"enum": ["$ref", {"pattern": "(", "$ref": "http://127.0.0.1:1/x"}]},
            "b": {"const": {"$ref": "file:///etc/hostname", "format": "uri"}},
        },
        "required": ["a", "b", "pattern", "$ref"],
    }
    saida = '{"a": "$ref", "b": {"$ref": "file:///etc/hostname", "format": "uri"}, "pattern": 1, "$ref": 2}'
    ollama.responder_com(**resposta_do_ollama(saida))

    assert chat(cliente, pedido(response_format=formato(esquema))).status_code == 200


def test_title_e_description_passam(cliente: TestClient, ollama: OllamaFalso) -> None:
    esquema = {"title": "Frase", "description": "Uma frase", "type": "object", "properties": {}}
    ollama.responder_com(**resposta_do_ollama("{}"))

    assert chat(cliente, pedido(response_format=formato(esquema))).status_code == 200


@pytest.mark.parametrize("chave", ["properties", "items", "additionalProperties"])
def test_profundidade_6_passa_e_7_responde_400(cliente: TestClient, ollama: OllamaFalso, chave: str) -> None:
    ollama.responder_com(**resposta_do_ollama("{}"))

    assert chat(cliente, pedido(response_format=formato(aninhar(chave, 6)))).status_code == 200

    ollama.pedidos.clear()
    conferir_recusa(cliente, ollama, aninhar(chave, 7), MENSAGEM_DE_LIMITE)


def test_64_nos_passam_e_65_respondem_400(cliente: TestClient, ollama: OllamaFalso) -> None:
    ollama.responder_com(**resposta_do_ollama("{}"))

    def com_propriedades(quantidade: int) -> dict[str, Any]:
        return {"type": "object", "properties": {f"p{indice}": {"type": "string"} for indice in range(quantidade)}}

    assert chat(cliente, pedido(response_format=formato(com_propriedades(63)))).status_code == 200

    ollama.pedidos.clear()
    conferir_recusa(cliente, ollama, com_propriedades(64), MENSAGEM_DE_LIMITE)


@pytest.mark.parametrize("palavra", ["minLength", "maxLength", "minItems", "maxItems"])
def test_teto_numerico_de_0_a_4096(cliente: TestClient, ollama: OllamaFalso, palavra: str) -> None:
    ollama.responder_com(**resposta_do_ollama("{}"))

    for valor in (0, 4096):
        assert chat(cliente, pedido(response_format=formato({palavra: valor}))).status_code == 200

    ollama.pedidos.clear()
    for valor in (4097, -1, 10_000_000):
        conferir_recusa(cliente, ollama, {palavra: valor}, MENSAGEM_DE_LIMITE)


@pytest.mark.parametrize("valor", [True, False, "10", 1.5, None, [1]])
def test_teto_numerico_recusa_o_que_nao_e_inteiro(cliente: TestClient, ollama: OllamaFalso, valor: object) -> None:
    resposta = chat(cliente, pedido(response_format=formato({"maxLength": valor})))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "schema_invalido"
    assert ollama.pedidos == []


def test_enum_com_64_itens_passa_e_com_65_responde_400(cliente: TestClient, ollama: OllamaFalso) -> None:
    ollama.responder_com(**resposta_do_ollama("1"))

    assert chat(cliente, pedido(response_format=formato({"enum": list(range(64))}))).status_code == 200

    ollama.pedidos.clear()
    conferir_recusa(cliente, ollama, {"enum": list(range(65))}, MENSAGEM_DE_LIMITE)


@pytest.mark.parametrize(
    "esquema",
    [
        {"properties": ["a"]},
        {"properties": {"a": "string"}},
        {"items": "string"},
        {"items": [{"type": "string"}]},
        {"additionalProperties": "nao"},
    ],
)
def test_forma_errada_dentro_do_subconjunto_responde_400_e_nao_500(
    cliente: TestClient, ollama: OllamaFalso, esquema: dict[str, Any]
) -> None:
    resposta = chat(cliente, pedido(response_format=formato(esquema)))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "schema_invalido"
    assert ollama.pedidos == []


def test_schema_invalido_dentro_do_subconjunto_continua_respondendo_schema_invalido(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    resposta = chat(cliente, pedido(response_format=formato({"type": "objeto"})))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "schema_invalido"
    assert ollama.pedidos == []


def test_a_mensagem_da_recusa_nao_ecoa_o_nome_da_palavra(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = chat(cliente, pedido(response_format=formato({"palavra-inventada-pelo-cliente": 1})))

    assert resposta.status_code == 400
    assert "inventada" not in resposta.text

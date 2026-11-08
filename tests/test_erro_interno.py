import logging
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway import autenticacao
from llm_gateway import chat as modulo_chat
from tests.conftest import TOKEN, OllamaFalso, autorizacao, resposta_do_ollama
from tests.test_chat import PROMPT, chat, erro, linhas_de_metricas, pedido

SEGREDO_DO_SCHEMA = "segredo-que-so-o-schema-tem"
SEGREDOS = (PROMPT, SEGREDO_DO_SCHEMA, TOKEN)
DETALHE = f"{PROMPT} {SEGREDO_DO_SCHEMA} {TOKEN}"


def pedido_com_segredos() -> dict[str, Any]:
    esquema = {"type": "object", "title": SEGREDO_DO_SCHEMA, "properties": {"en": {"type": "string"}}}
    formato = {"type": "json_schema", "json_schema": {"name": "item", "schema": esquema}}

    return pedido(response_format=formato)


def falhar_no_upstream(ollama: OllamaFalso, _: pytest.MonkeyPatch) -> None:
    async def explodir(_: httpx2.Request) -> httpx2.Response:
        raise RuntimeError(DETALHE)

    ollama.responder = explodir


def falhar_no_validador(_: OllamaFalso, monkeypatch: pytest.MonkeyPatch) -> None:
    def explodir(*_: object) -> None:
        raise RuntimeError(DETALHE)

    monkeypatch.setattr(modulo_chat, "preparar_validador", explodir)


def falhar_na_saida(_: OllamaFalso, monkeypatch: pytest.MonkeyPatch) -> None:
    def explodir(*_: object) -> None:
        raise RuntimeError(DETALHE)

    monkeypatch.setattr(modulo_chat, "conferir_saida", explodir)


@pytest.mark.parametrize("injetar", [falhar_no_upstream, falhar_no_validador, falhar_na_saida])
def test_excecao_inesperada_vira_500_sem_vazar_nada_e_devolve_a_vaga(
    app: FastAPI,
    cliente: TestClient,
    ollama: OllamaFalso,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
    injetar: Callable[[OllamaFalso, pytest.MonkeyPatch], None],
) -> None:
    caplog.set_level(logging.DEBUG)
    injetar(ollama, monkeypatch)

    resposta = chat(cliente, pedido_com_segredos())

    assert resposta.status_code == 500
    assert erro(resposta) == {
        "message": "Erro interno do gateway.",
        "type": "server_error",
        "param": None,
        "code": "erro_interno",
    }
    saida = capfd.readouterr()
    for segredo in SEGREDOS:
        assert segredo not in resposta.text
        assert segredo not in caplog.text
        assert segredo not in saida.out
        assert segredo not in saida.err
    assert "Traceback" not in saida.err
    assert app.state.limitador.ocupadas == 0

    (metricas,) = linhas_de_metricas(caplog)
    assert metricas["status"] == 500
    assert metricas["codigo"] == "erro_interno"
    assert metricas["erro"] == "RuntimeError"


def test_o_gateway_continua_atendendo_depois_do_500(cliente: TestClient, ollama: OllamaFalso) -> None:
    async def explodir(_: httpx2.Request) -> httpx2.Response:
        raise RuntimeError(DETALHE)

    ollama.responder = explodir
    assert chat(cliente, pedido()).status_code == 500

    ollama.responder_com(**resposta_do_ollama())

    assert chat(cliente, pedido()).status_code == 200


def test_erro_nao_previsto_e_o_unico_que_preenche_o_campo_erro(
    cliente: TestClient, ollama: OllamaFalso, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    chat(cliente, pedido())
    chat(cliente, pedido(model="qwen3:4b"))

    assert [linha["erro"] for linha in linhas_de_metricas(caplog)] == [None, None]


def test_excecao_fora_do_chat_tambem_sai_no_formato_da_openai(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def explodir(*_: object) -> None:
        raise RuntimeError(DETALHE)

    monkeypatch.setattr(autenticacao, "ler_token", explodir)
    caplog.set_level(logging.DEBUG)

    with TestClient(app, raise_server_exceptions=False) as cliente:
        resposta = cliente.get("/v1/models", headers=autorizacao())

    assert resposta.status_code == 500
    assert erro(resposta) == {
        "message": "Erro interno do gateway.",
        "type": "server_error",
        "param": None,
        "code": "erro_interno",
    }
    for segredo in SEGREDOS:
        assert segredo not in resposta.text

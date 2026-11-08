import logging

import anyio
import httpx2
import pytest
from fastapi import FastAPI

from llm_gateway.concorrencia import Limitador
from llm_gateway.erros import ErroOpenAI
from tests.conftest import OllamaFalso, autorizacao, resposta_do_ollama
from tests.test_chat import pedido


@pytest.mark.anyio
async def test_com_concorrencia_1_o_segundo_chat_leva_503_na_hora(
    app: FastAPI, ollama: OllamaFalso, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    entrou, liberar = anyio.Event(), anyio.Event()

    async def segurar(_: httpx2.Request) -> httpx2.Response:
        entrou.set()
        await liberar.wait()

        return httpx2.Response(200, json=resposta_do_ollama())

    ollama.responder = segurar
    respostas: list[httpx2.Response] = []
    transporte = httpx2.ASGITransport(app=app)

    async with httpx2.AsyncClient(transport=transporte, base_url="http://gateway", headers=autorizacao()) as cliente:

        async def primeiro() -> None:
            respostas.append(await cliente.post("/v1/chat/completions", json=pedido()))

        async with anyio.create_task_group() as grupo:
            grupo.start_soon(primeiro)
            await entrou.wait()

            with anyio.fail_after(2):
                segundo = await cliente.post("/v1/chat/completions", json=pedido())

            liberar.set()

        terceiro = await cliente.post("/v1/chat/completions", json=pedido())

    assert segundo.status_code == 503
    assert segundo.headers["retry-after"] == "10"
    assert segundo.json()["error"] == {
        "message": "O gateway está ocupado. Tente de novo em instantes.",
        "type": "server_error",
        "param": None,
        "code": "ocupado",
    }
    assert [resposta.status_code for resposta in respostas] == [200]
    assert terceiro.status_code == 200
    assert len(ollama.pedidos) == 2
    assert app.state.limitador.ocupadas == 0
    status = [registro.__dict__["metricas"]["status"] for registro in caplog.records if registro.name == "gateway.chat"]
    assert sorted(status) == [200, 200, 503]


def test_vaga_e_devolvida_mesmo_com_excecao() -> None:
    limitador = Limitador(1)

    with pytest.raises(RuntimeError), limitador.vaga():
        raise RuntimeError

    assert limitador.ocupadas == 0

    with limitador.vaga():
        assert limitador.ocupadas == 1


def test_duas_vagas_aceitam_dois_e_recusam_o_terceiro() -> None:
    limitador = Limitador(2)

    with limitador.vaga(), limitador.vaga():
        assert limitador.ocupadas == 2

        with pytest.raises(ErroOpenAI, match="ocupado"), limitador.vaga():
            pass

    assert limitador.ocupadas == 0

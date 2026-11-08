import json
import logging
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.registro import RAIZ
from tests.conftest import TOKEN
from tests.test_chat import PROMPT, chat, pedido


def test_logger_do_pacote_chega_ao_stdout_em_json(app: FastAPI, capfd: pytest.CaptureFixture[str]) -> None:
    logging.getLogger("llm_gateway.qualquer_modulo").info("evento de teste")

    linhas = [json.loads(linha) for linha in capfd.readouterr().out.splitlines()]

    assert {"nivel": "info", "evento": "evento de teste"} in linhas


def test_logger_de_fora_do_pacote_nao_chega_ao_stdout(app: FastAPI, capfd: pytest.CaptureFixture[str]) -> None:
    logging.getLogger("gateway.chat").info("evento de fora")

    assert "evento de fora" not in capfd.readouterr().out


def test_a_raiz_do_log_e_o_nome_do_pacote() -> None:
    assert RAIZ == "llm_gateway"


class SaidaQueFalha:
    def write(self, _: str) -> int:
        raise OSError("sem espaço")

    def flush(self) -> None:
        raise OSError("sem espaço")


def test_falha_ao_escrever_o_log_nao_troca_a_resposta_nem_vaza_o_pedido(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdout", SaidaQueFalha())

    resposta = chat(cliente, pedido())

    saida = capfd.readouterr()
    assert resposta.status_code == 200
    assert "Logging error" in saida.err
    for texto in (PROMPT, TOKEN, "Responda só JSON", "additionalProperties"):
        assert texto not in saida.err
        assert texto not in saida.out

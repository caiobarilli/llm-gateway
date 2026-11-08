import json
import logging

import pytest
from fastapi import FastAPI

from llm_gateway.registro import RAIZ


def test_logger_do_pacote_chega_ao_stdout_em_json(app: FastAPI, capfd: pytest.CaptureFixture[str]) -> None:
    logging.getLogger("llm_gateway.qualquer_modulo").info("evento de teste")

    linhas = [json.loads(linha) for linha in capfd.readouterr().out.splitlines()]

    assert {"nivel": "info", "evento": "evento de teste"} in linhas


def test_logger_de_fora_do_pacote_nao_chega_ao_stdout(app: FastAPI, capfd: pytest.CaptureFixture[str]) -> None:
    logging.getLogger("gateway.chat").info("evento de fora")

    assert "evento de fora" not in capfd.readouterr().out


def test_a_raiz_do_log_e_o_nome_do_pacote() -> None:
    assert RAIZ == "llm_gateway"

import httpx2
from fastapi import FastAPI


def test_os_tempos_do_cliente_do_ollama_sao_5_s_de_conexao_e_60_s_de_leitura(app: FastAPI) -> None:
    assert app.state.cliente_ollama.timeout == httpx2.Timeout(60.0, connect=5.0)


def test_o_cliente_do_ollama_nao_segue_redirecionamento(app: FastAPI) -> None:
    assert app.state.cliente_ollama.follow_redirects is False

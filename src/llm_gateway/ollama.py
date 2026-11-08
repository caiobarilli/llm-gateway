from typing import Any

import httpx2
from pydantic import BaseModel, ValidationError

from llm_gateway.erros import Codigo, ErroOpenAI

TEMPO_DE_CONEXAO = 5.0
TEMPO_DE_LEITURA = 60.0
CONTEXTO = 4096


class MensagemOllama(BaseModel):
    role: str
    content: str


class RespostaOllama(BaseModel):
    message: MensagemOllama
    done_reason: str | None = None
    prompt_eval_count: int = 0
    eval_count: int = 0
    eval_duration: int = 0
    load_duration: int = 0


def criar_cliente(url: str, transporte: httpx2.AsyncBaseTransport | None = None) -> httpx2.AsyncClient:
    tempo = httpx2.Timeout(TEMPO_DE_LEITURA, connect=TEMPO_DE_CONEXAO)

    return httpx2.AsyncClient(base_url=url, timeout=tempo, transport=transporte, follow_redirects=False)


def _upstream(status: int, codigo: Codigo, mensagem: str) -> ErroOpenAI:
    return ErroOpenAI(status, mensagem, "server_error", codigo)


async def conversar(cliente: httpx2.AsyncClient, corpo: dict[str, Any]) -> RespostaOllama:
    try:
        resposta = await cliente.post("/api/chat", json=corpo)
    except httpx2.TimeoutException:
        raise _upstream(504, Codigo.UPSTREAM_TIMEOUT, "O modelo não respondeu a tempo.") from None
    except httpx2.RequestError:
        raise _upstream(503, Codigo.UPSTREAM_INDISPONIVEL, "O modelo está indisponível.") from None

    if resposta.status_code != 200:
        raise _upstream(502, Codigo.UPSTREAM_ERRO, f"O modelo respondeu com erro {resposta.status_code}.")

    try:
        return RespostaOllama.model_validate_json(resposta.content)
    except ValidationError:
        raise _upstream(502, Codigo.UPSTREAM_RESPOSTA_INVALIDA, "O modelo respondeu num formato inesperado.") from None

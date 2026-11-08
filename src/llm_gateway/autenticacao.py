import hmac
import logging
from pathlib import Path

from fastapi import Request

from llm_gateway.erros import Codigo, ErroOpenAI

registro = logging.getLogger(__name__)

DESAFIO = {"WWW-Authenticate": "Bearer"}
TAMANHO_MINIMO_DO_TOKEN = 32


def ler_token(arquivo: Path) -> str:
    try:
        token = arquivo.read_bytes().decode("ascii").strip()
    except (OSError, UnicodeDecodeError) as erro:
        registro.warning("token indisponível: %s", type(erro).__name__)
        raise _token_indisponivel() from None

    if token == "":
        registro.warning("token indisponível: arquivo vazio")
        raise _token_indisponivel()

    if len(token) < TAMANHO_MINIMO_DO_TOKEN:
        registro.warning("token indisponível: token curto")
        raise _token_indisponivel()

    return token


def _token_indisponivel() -> ErroOpenAI:
    return ErroOpenAI(503, "O gateway está sem token configurado.", "server_error", Codigo.TOKEN_INDISPONIVEL)


def _recusa(motivo: str) -> ErroOpenAI:
    registro.info("autenticação recusada: %s", motivo)

    return ErroOpenAI(401, "Token ausente ou inválido.", "invalid_request_error", Codigo.INVALID_API_KEY, DESAFIO)


def extrair_bearer(cabecalho: str | None) -> str:
    if cabecalho is None:
        raise _recusa("sem cabeçalho")

    partes = cabecalho.split(" ")
    if len(partes) != 2 or partes[0].lower() != "bearer" or partes[1] == "":
        raise _recusa("cabeçalho malformado")

    return partes[1]


def conferir_token(fornecido: str, esperado: str) -> None:
    if not hmac.compare_digest(fornecido.encode("utf-8"), esperado.encode("utf-8")):
        raise _recusa("token errado")


def exigir_token(request: Request) -> None:
    arquivo: Path = request.app.state.config.token_arquivo
    esperado = ler_token(arquivo)
    conferir_token(extrair_bearer(request.headers.get("authorization")), esperado)

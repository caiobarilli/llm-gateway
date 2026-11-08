from enum import StrEnum
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

TipoDeErro = Literal["invalid_request_error", "server_error"]


class Codigo(StrEnum):
    INVALID_API_KEY = "invalid_api_key"
    TOKEN_INDISPONIVEL = "token_indisponivel"  # noqa: S105
    INVALID_REQUEST = "invalid_request"
    STREAM_NAO_SUPORTADO = "stream_nao_suportado"
    MENSAGENS_GRANDES_DEMAIS = "mensagens_grandes_demais"
    SCHEMA_INVALIDO = "schema_invalido"
    CORPO_GRANDE_DEMAIS = "corpo_grande_demais"
    MODEL_NOT_FOUND = "model_not_found"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    OCUPADO = "ocupado"
    UPSTREAM_INDISPONIVEL = "upstream_indisponivel"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_ERRO = "upstream_erro"
    UPSTREAM_RESPOSTA_INVALIDA = "upstream_resposta_invalida"
    SAIDA_TRUNCADA = "saida_truncada"
    SAIDA_INVALIDA = "saida_invalida"
    ERRO_INTERNO = "erro_interno"


class DetalheDoErro(BaseModel):
    message: str
    type: TipoDeErro
    param: None = None
    code: Codigo | None


class CorpoDeErro(BaseModel):
    error: DetalheDoErro


class ErroOpenAI(Exception):
    def __init__(
        self,
        status: int,
        mensagem: str,
        tipo: TipoDeErro,
        codigo: Codigo | None,
        cabecalhos: dict[str, str] | None = None,
    ) -> None:
        super().__init__(codigo or tipo)
        self.status = status
        self.mensagem = mensagem
        self.tipo = tipo
        self.codigo = codigo
        self.cabecalhos = cabecalhos or {}


def erro_interno() -> ErroOpenAI:
    return ErroOpenAI(500, "Erro interno do gateway.", "server_error", Codigo.ERRO_INTERNO)


def resposta_de_erro(erro: ErroOpenAI) -> JSONResponse:
    corpo = CorpoDeErro(error=DetalheDoErro(message=erro.mensagem, type=erro.tipo, code=erro.codigo))

    return JSONResponse(corpo.model_dump(mode="json"), status_code=erro.status, headers=erro.cabecalhos)


async def tratar_erro_openai(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, ErroOpenAI):
        raise erro

    return resposta_de_erro(erro)


async def tratar_erro_http(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, HTTPException):
        raise erro

    tipo: TipoDeErro = "server_error" if erro.status_code >= 500 else "invalid_request_error"
    codigo = {404: Codigo.NOT_FOUND, 405: Codigo.METHOD_NOT_ALLOWED}.get(erro.status_code)

    return resposta_de_erro(ErroOpenAI(erro.status_code, str(erro.detail), tipo, codigo, dict(erro.headers or {})))


async def tratar_erro_de_validacao(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, RequestValidationError):
        raise erro

    return resposta_de_erro(ErroOpenAI(400, "Pedido inválido.", "invalid_request_error", Codigo.INVALID_REQUEST))


async def tratar_erro_inesperado(_: Request, erro: Exception) -> JSONResponse:
    return resposta_de_erro(erro_interno())


def registrar_tratadores(app: FastAPI) -> None:
    app.add_exception_handler(Exception, tratar_erro_inesperado)
    app.add_exception_handler(ErroOpenAI, tratar_erro_openai)
    app.add_exception_handler(HTTPException, tratar_erro_http)
    app.add_exception_handler(RequestValidationError, tratar_erro_de_validacao)

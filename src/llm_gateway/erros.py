from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ErroOpenAI(Exception):
    def __init__(
        self,
        status: int,
        mensagem: str,
        tipo: str,
        codigo: str | None,
        cabecalhos: dict[str, str] | None = None,
    ) -> None:
        super().__init__(codigo or tipo)
        self.status = status
        self.mensagem = mensagem
        self.tipo = tipo
        self.codigo = codigo
        self.cabecalhos = cabecalhos or {}


def resposta_de_erro(erro: ErroOpenAI) -> JSONResponse:
    corpo = {"error": {"message": erro.mensagem, "type": erro.tipo, "param": None, "code": erro.codigo}}

    return JSONResponse(corpo, status_code=erro.status, headers=erro.cabecalhos)


async def tratar_erro_openai(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, ErroOpenAI):
        raise erro

    return resposta_de_erro(erro)


async def tratar_erro_http(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, HTTPException):
        raise erro

    tipo = "server_error" if erro.status_code >= 500 else "invalid_request_error"
    codigo = {404: "not_found", 405: "method_not_allowed"}.get(erro.status_code)

    return resposta_de_erro(ErroOpenAI(erro.status_code, str(erro.detail), tipo, codigo, dict(erro.headers or {})))


async def tratar_erro_de_validacao(_: Request, erro: Exception) -> JSONResponse:
    if not isinstance(erro, RequestValidationError):
        raise erro

    return resposta_de_erro(ErroOpenAI(400, "Pedido inválido.", "invalid_request_error", "invalid_request"))


async def tratar_erro_inesperado(_: Request, erro: Exception) -> JSONResponse:
    return resposta_de_erro(ErroOpenAI(500, "Erro interno do gateway.", "server_error", "erro_interno"))


def registrar_tratadores(app: FastAPI) -> None:
    app.add_exception_handler(Exception, tratar_erro_inesperado)
    app.add_exception_handler(ErroOpenAI, tratar_erro_openai)
    app.add_exception_handler(HTTPException, tratar_erro_http)
    app.add_exception_handler(RequestValidationError, tratar_erro_de_validacao)

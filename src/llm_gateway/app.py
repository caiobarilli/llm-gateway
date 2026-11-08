from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Literal

import httpx2
from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel

from llm_gateway.autenticacao import exigir_token
from llm_gateway.chat import rotas as rotas_do_chat
from llm_gateway.concorrencia import Limitador
from llm_gateway.config import Config
from llm_gateway.contrato import RESPOSTAS_DO_V1
from llm_gateway.erros import registrar_tratadores
from llm_gateway.modelos import ListaDeModelos, listar_modelos
from llm_gateway.ollama import criar_cliente
from llm_gateway.registro import configurar_registro

v1 = APIRouter(prefix="/v1", dependencies=[Depends(exigir_token)], responses=RESPOSTAS_DO_V1)
v1.include_router(rotas_do_chat)


@v1.get("/models")
def modelos(request: Request) -> ListaDeModelos:
    config: Config = request.app.state.config

    return listar_modelos(config)


class Saude(BaseModel):
    status: Literal["ok"]


def criar_app(config: Config | None = None, transporte: httpx2.AsyncBaseTransport | None = None) -> FastAPI:
    configurar_registro()
    config = config if config is not None else Config.do_ambiente()
    cliente = criar_cliente(config.ollama_url, transporte)

    @asynccontextmanager
    async def ciclo(_: FastAPI) -> AsyncIterator[None]:
        yield
        await cliente.aclose()

    app = FastAPI(
        title="llm-gateway",
        version=version("llm-gateway"),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=ciclo,
    )
    app.state.config = config
    app.state.limitador = Limitador(config.concorrencia)
    app.state.cliente_ollama = cliente

    registrar_tratadores(app)

    @app.get("/health")
    def saude() -> Saude:
        return Saude(status="ok")

    app.include_router(v1)

    return app

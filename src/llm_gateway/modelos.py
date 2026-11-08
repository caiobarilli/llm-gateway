from typing import Literal

from pydantic import BaseModel

from llm_gateway.config import Config
from llm_gateway.erros import Codigo, ErroOpenAI

LIMITE_DO_NOME = 100


def exigir_modelo_permitido(config: Config, modelo: str) -> str:
    if modelo in config.modelos:
        return modelo

    raise ErroOpenAI(
        404,
        f"O modelo '{modelo}' não existe ou não é permitido neste gateway.",
        "invalid_request_error",
        Codigo.MODEL_NOT_FOUND,
    )


class Modelo(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "llm-gateway"


class ListaDeModelos(BaseModel):
    object: Literal["list"] = "list"
    data: list[Modelo]


def listar_modelos(config: Config) -> ListaDeModelos:
    return ListaDeModelos(data=[Modelo(id=modelo) for modelo in config.modelos])

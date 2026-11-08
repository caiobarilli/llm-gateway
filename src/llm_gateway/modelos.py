from llm_gateway.config import Config
from llm_gateway.erros import ErroOpenAI

LIMITE_DO_NOME = 100


def exigir_modelo_permitido(config: Config, modelo: str) -> str:
    if modelo in config.modelos:
        return modelo

    raise ErroOpenAI(
        404,
        f"O modelo '{modelo}' não existe ou não é permitido neste gateway.",
        "invalid_request_error",
        "model_not_found",
    )


def listar_modelos(config: Config) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"id": modelo, "object": "model", "created": 0, "owned_by": "llm-gateway"} for modelo in config.modelos
        ],
    }

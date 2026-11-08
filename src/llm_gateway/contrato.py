from typing import Any

from llm_gateway.erros import CorpoDeErro

CABECALHO_DO_DESAFIO: dict[str, Any] = {
    "WWW-Authenticate": {"description": "Sempre `Bearer`.", "schema": {"type": "string"}},
}
CABECALHO_DA_ESPERA: dict[str, Any] = {
    "Retry-After": {
        "description": "Segundos até tentar de novo. Só vem quando o `code` é `ocupado`.",
        "schema": {"type": "integer"},
    },
}


def declarar_erro(descricao: str, cabecalhos: dict[str, Any] | None = None) -> dict[str, Any]:
    resposta: dict[str, Any] = {"model": CorpoDeErro, "description": descricao}
    if cabecalhos is not None:
        resposta["headers"] = cabecalhos

    return resposta


RESPOSTAS_DO_V1: dict[int | str, dict[str, Any]] = {
    401: declarar_erro("Token ausente, malformado ou errado (`invalid_api_key`).", CABECALHO_DO_DESAFIO),
    500: declarar_erro("Exceção que o gateway não previa (`erro_interno`)."),
    503: declarar_erro("O arquivo do token está indisponível (`token_indisponivel`)."),
}

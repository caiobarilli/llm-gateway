from typing import Any

from llm_gateway.erros import Codigo, ErroOpenAI

PALAVRAS_PERMITIDAS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "title",
        "description",
    }
)
PALAVRAS_COM_TETO = frozenset({"minLength", "maxLength", "minItems", "maxItems"})
LIMITE_DE_NOS = 64
LIMITE_DE_PROFUNDIDADE = 6
TETO_NUMERICO = 4096
LIMITE_DO_ENUM = 64


def _fora_do_subconjunto() -> ErroOpenAI:
    return ErroOpenAI(
        400,
        "O JSON Schema do response_format usa uma palavra-chave fora do subconjunto aceito.",
        "invalid_request_error",
        Codigo.SCHEMA_INVALIDO,
    )


def _acima_dos_limites() -> ErroOpenAI:
    return ErroOpenAI(
        400,
        "O JSON Schema do response_format passa dos limites de tamanho do subconjunto aceito.",
        "invalid_request_error",
        Codigo.SCHEMA_INVALIDO,
    )


def _conferir_teto(valor: object) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise _fora_do_subconjunto()

    if not 0 <= valor <= TETO_NUMERICO:
        raise _acima_dos_limites()


def _visitar(no: object, nivel: int, nos: list[int]) -> None:
    nos[0] += 1
    if nos[0] > LIMITE_DE_NOS or nivel > LIMITE_DE_PROFUNDIDADE:
        raise _acima_dos_limites()

    if isinstance(no, bool):
        return

    if not isinstance(no, dict):
        raise _fora_do_subconjunto()

    for palavra, valor in no.items():
        if palavra not in PALAVRAS_PERMITIDAS:
            raise _fora_do_subconjunto()

        if palavra in PALAVRAS_COM_TETO:
            _conferir_teto(valor)
        elif palavra == "properties":
            if not isinstance(valor, dict):
                raise _fora_do_subconjunto()

            for filho in valor.values():
                _visitar(filho, nivel + 1, nos)
        elif palavra == "items":
            _visitar(valor, nivel + 1, nos)
        elif palavra == "additionalProperties":
            if not isinstance(valor, bool):
                _visitar(valor, nivel + 1, nos)
        elif palavra == "enum" and isinstance(valor, list) and len(valor) > LIMITE_DO_ENUM:
            raise _acima_dos_limites()


def exigir_subconjunto(esquema: dict[str, Any]) -> None:
    _visitar(esquema, 1, [0])

import json
import logging
import time
import uuid
from typing import Any, Literal

import httpx2
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from llm_gateway.concorrencia import Limitador
from llm_gateway.config import Config
from llm_gateway.erros import ErroOpenAI
from llm_gateway.modelos import exigir_modelo_permitido
from llm_gateway.ollama import CONTEXTO, RespostaOllama, conversar
from llm_gateway.registro import registrar_metricas

registro = logging.getLogger("gateway.chat")

LIMITE_DO_CORPO = 64 * 1024
LIMITE_DE_MENSAGENS = 8
LIMITE_DE_CARACTERES = 8000
LIMITE_DE_TOKENS = 1024
TOKENS_PADRAO = 512

FINS = {"stop": "stop", "length": "length"}

rotas = APIRouter()


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=LIMITE_DE_CARACTERES)


class EsquemaJson(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=512)
    esquema: dict[str, Any] = Field(alias="schema")
    strict: bool | None = None


class FormatoDeResposta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["json_schema"]
    json_schema: EsquemaJson


class Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(max_length=100)
    messages: list[Mensagem] = Field(min_length=1, max_length=LIMITE_DE_MENSAGENS)
    response_format: FormatoDeResposta | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=LIMITE_DE_TOKENS)
    stream: bool | None = None


def _invalido(mensagem: str, codigo: str = "invalid_request", status: int = 400) -> ErroOpenAI:
    return ErroOpenAI(status, mensagem, "invalid_request_error", codigo)


async def ler_corpo(request: Request) -> bytes:
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > LIMITE_DO_CORPO:
        raise _invalido("O corpo do pedido passa do limite.", "corpo_grande_demais", 413)

    corpo = bytearray()
    async for pedaco in request.stream():
        corpo += pedaco
        if len(corpo) > LIMITE_DO_CORPO:
            raise _invalido("O corpo do pedido passa do limite.", "corpo_grande_demais", 413)

    return bytes(corpo)


def interpretar(corpo: bytes) -> Pedido:
    try:
        pedido = Pedido.model_validate_json(corpo)
    except ValidationError as erro:
        campos = sorted({".".join(str(parte)[:40] for parte in falha["loc"]) or "corpo" for falha in erro.errors()})
        raise _invalido(f"Pedido inválido em: {', '.join(campos[:5])}.") from None

    if pedido.stream:
        raise _invalido("Streaming não é suportado.", "stream_nao_suportado")

    if sum(len(mensagem.content) for mensagem in pedido.messages) > LIMITE_DE_CARACTERES:
        raise _invalido("As mensagens passam do limite de caracteres.", "mensagens_grandes_demais")

    return pedido


def preparar_validador(pedido: Pedido) -> Draft202012Validator | None:
    if pedido.response_format is None:
        return None

    esquema = pedido.response_format.json_schema.esquema
    try:
        Draft202012Validator.check_schema(esquema)
    except SchemaError:
        raise _invalido("O JSON Schema do response_format é inválido.", "schema_invalido") from None

    return Draft202012Validator(esquema)


def montar_corpo(pedido: Pedido, modelo: str) -> dict[str, Any]:
    opcoes: dict[str, Any] = {"num_ctx": CONTEXTO, "num_predict": pedido.max_tokens or TOKENS_PADRAO}
    if pedido.temperature is not None:
        opcoes["temperature"] = pedido.temperature

    corpo: dict[str, Any] = {
        "model": modelo,
        "messages": [mensagem.model_dump() for mensagem in pedido.messages],
        "stream": False,
        "options": opcoes,
    }
    if pedido.response_format is not None:
        corpo["format"] = pedido.response_format.json_schema.esquema

    return corpo


def conferir_saida(resposta: RespostaOllama, validador: Draft202012Validator | None) -> None:
    if validador is None:
        return

    if resposta.done_reason == "length":
        raise ErroOpenAI(502, "A resposta do modelo foi cortada pelo max_tokens.", "server_error", "saida_truncada")

    try:
        dados = json.loads(resposta.message.content)
    except ValueError:
        raise ErroOpenAI(502, "A resposta do modelo não é JSON.", "server_error", "saida_invalida") from None

    if next(validador.iter_errors(dados), None) is not None:
        raise ErroOpenAI(502, "A resposta do modelo não segue o schema.", "server_error", "saida_invalida")


def formatar(resposta: RespostaOllama, modelo: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": modelo,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": resposta.message.content},
                "finish_reason": FINS.get(resposta.done_reason or "", "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": resposta.prompt_eval_count,
            "completion_tokens": resposta.eval_count,
            "total_tokens": resposta.prompt_eval_count + resposta.eval_count,
        },
    }


def tokens_por_segundo(resposta: RespostaOllama) -> float | None:
    if resposta.eval_duration <= 0:
        return None

    return round(resposta.eval_count / (resposta.eval_duration / 1e9), 1)


@rotas.post("/chat/completions")
async def completar(request: Request) -> JSONResponse:
    config: Config = request.app.state.config
    limitador: Limitador = request.app.state.limitador
    cliente: httpx2.AsyncClient = request.app.state.cliente_ollama

    inicio = time.perf_counter()
    metricas: dict[str, Any] = {
        "modelo": None,
        "status": 500,
        "codigo": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "tokens_por_segundo": None,
        "carga_ms": None,
    }

    try:
        pedido = interpretar(await ler_corpo(request))
        modelo = exigir_modelo_permitido(config, pedido.model)
        metricas["modelo"] = modelo
        validador = preparar_validador(pedido)

        with limitador.vaga():
            resposta = await conversar(cliente, montar_corpo(pedido, modelo))

        metricas.update(
            prompt_tokens=resposta.prompt_eval_count,
            completion_tokens=resposta.eval_count,
            tokens_por_segundo=tokens_por_segundo(resposta),
            carga_ms=round(resposta.load_duration / 1e6),
        )
        conferir_saida(resposta, validador)
        metricas["status"] = 200

        return JSONResponse(formatar(resposta, modelo))
    except ErroOpenAI as erro:
        metricas["status"] = erro.status
        metricas["codigo"] = erro.codigo
        raise
    finally:
        metricas["duracao_ms"] = round((time.perf_counter() - inicio) * 1000)
        registrar_metricas(registro, "chat", metricas)

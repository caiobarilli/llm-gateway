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
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from pydantic_core import ErrorDetails

from llm_gateway.concorrencia import Limitador
from llm_gateway.config import Config
from llm_gateway.contrato import CABECALHO_DA_ESPERA, declarar_erro
from llm_gateway.erros import Codigo, ErroOpenAI, erro_interno
from llm_gateway.modelos import LIMITE_DO_NOME, exigir_modelo_permitido
from llm_gateway.ollama import CONTEXTO, RespostaOllama, conversar
from llm_gateway.registro import registrar_metricas
from llm_gateway.subconjunto import (
    LIMITE_DE_NOS,
    LIMITE_DE_PROFUNDIDADE,
    LIMITE_DO_ENUM,
    PALAVRAS_PERMITIDAS,
    TETO_NUMERICO,
    exigir_subconjunto,
)

registro = logging.getLogger(__name__)

LIMITE_DO_CORPO = 64 * 1024
LIMITE_DE_MENSAGENS = 8
LIMITE_DE_CARACTERES = 8000
LIMITE_DE_TOKENS = 1024
TOKENS_PADRAO = 512
PALAVRAS_DO_CONTRATO: list[JsonValue] = [*sorted(PALAVRAS_PERMITIDAS)]


class MensagemDaResposta(BaseModel):
    role: Literal["assistant"]
    content: str


class Escolha(BaseModel):
    index: int
    message: MensagemDaResposta
    finish_reason: Literal["stop", "length"]


class Uso(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class RespostaDoChat(BaseModel):
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[Escolha]
    usage: Uso


RESPOSTAS_DO_CHAT: dict[int | str, dict[str, Any]] = {
    200: {"model": RespostaDoChat, "description": "A resposta do chat no formato da OpenAI."},
    400: declarar_erro(
        "Pedido recusado: `invalid_request`, `stream_nao_suportado`, `mensagens_grandes_demais` ou `schema_invalido`."
    ),
    404: declarar_erro("Modelo fora da allowlist (`model_not_found`)."),
    413: declarar_erro(f"Corpo acima de {LIMITE_DO_CORPO // 1024} KiB (`corpo_grande_demais`)."),
    502: declarar_erro(
        "Falha do upstream ou saída recusada: `upstream_erro`, `upstream_resposta_invalida`, "
        "`saida_truncada` ou `saida_invalida`."
    ),
    503: declarar_erro(
        "`ocupado` (com `Retry-After`), `token_indisponivel` ou `upstream_indisponivel`.", CABECALHO_DA_ESPERA
    ),
    504: declarar_erro("O Ollama não respondeu a tempo (`upstream_timeout`)."),
}

rotas = APIRouter()


class Mensagem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=LIMITE_DE_CARACTERES)


class EsquemaJson(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=512)
    esquema: dict[str, Any] = Field(
        alias="schema",
        description=(
            "Subconjunto de JSON Schema (Draft 2020-12): só as palavras-chave de x-palavras-chave. "
            f"Até {LIMITE_DE_NOS} nós, profundidade {LIMITE_DE_PROFUNDIDADE}, inteiros de 0 a {TETO_NUMERICO} em "
            f"minLength, maxLength, minItems e maxItems e até {LIMITE_DO_ENUM} itens em enum."
        ),
        json_schema_extra={"x-palavras-chave": PALAVRAS_DO_CONTRATO},
    )
    strict: bool | None = None


class FormatoDeResposta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["json_schema"]
    json_schema: EsquemaJson


class Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(max_length=LIMITE_DO_NOME)
    messages: list[Mensagem] = Field(min_length=1, max_length=LIMITE_DE_MENSAGENS)
    response_format: FormatoDeResposta | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=LIMITE_DE_TOKENS)
    stream: bool | None = None


def _invalido(mensagem: str, codigo: Codigo = Codigo.INVALID_REQUEST, status: int = 400) -> ErroOpenAI:
    return ErroOpenAI(status, mensagem, "invalid_request_error", codigo)


async def ler_corpo(request: Request) -> bytes:
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > LIMITE_DO_CORPO:
        raise _invalido("O corpo do pedido passa do limite.", Codigo.CORPO_GRANDE_DEMAIS, 413)

    corpo = bytearray()
    async for pedaco in request.stream():
        corpo += pedaco
        if len(corpo) > LIMITE_DO_CORPO:
            raise _invalido("O corpo do pedido passa do limite.", Codigo.CORPO_GRANDE_DEMAIS, 413)

    return bytes(corpo)


def _caminho_do_erro(falha: ErrorDetails) -> str:
    desconhecido = falha["type"] == "extra_forbidden"
    local = falha["loc"][:-1] if desconhecido else falha["loc"]
    caminho = ".".join(str(parte)[:40] for parte in local) or "corpo"

    return f"{caminho} (campo não permitido)" if desconhecido else caminho


def interpretar(corpo: bytes) -> Pedido:
    try:
        pedido = Pedido.model_validate_json(corpo)
    except ValidationError as erro:
        campos = sorted({_caminho_do_erro(falha) for falha in erro.errors()})
        raise _invalido(f"Pedido inválido em: {', '.join(campos[:5])}.") from None

    if pedido.stream:
        raise _invalido("Streaming não é suportado.", Codigo.STREAM_NAO_SUPORTADO)

    if sum(len(mensagem.content) for mensagem in pedido.messages) > LIMITE_DE_CARACTERES:
        raise _invalido("As mensagens passam do limite de caracteres.", Codigo.MENSAGENS_GRANDES_DEMAIS)

    return pedido


def preparar_validador(pedido: Pedido) -> Draft202012Validator | None:
    if pedido.response_format is None:
        return None

    esquema = pedido.response_format.json_schema.esquema
    exigir_subconjunto(esquema)
    try:
        Draft202012Validator.check_schema(esquema)
    except SchemaError:
        raise _invalido("O JSON Schema do response_format é inválido.", Codigo.SCHEMA_INVALIDO) from None

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
        raise ErroOpenAI(
            502, "A resposta do modelo foi cortada pelo max_tokens.", "server_error", Codigo.SAIDA_TRUNCADA
        )

    try:
        dados = json.loads(resposta.message.content)
    except ValueError:
        raise ErroOpenAI(502, "A resposta do modelo não é JSON.", "server_error", Codigo.SAIDA_INVALIDA) from None

    if next(validador.iter_errors(dados), None) is not None:
        raise ErroOpenAI(502, "A resposta do modelo não segue o schema.", "server_error", Codigo.SAIDA_INVALIDA)


def formatar(resposta: RespostaOllama, modelo: str) -> RespostaDoChat:
    return RespostaDoChat(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        object="chat.completion",
        created=int(time.time()),
        model=modelo,
        choices=[
            Escolha(
                index=0,
                message=MensagemDaResposta(role="assistant", content=resposta.message.content),
                finish_reason="length" if resposta.done_reason == "length" else "stop",
            )
        ],
        usage=Uso(
            prompt_tokens=resposta.prompt_eval_count,
            completion_tokens=resposta.eval_count,
            total_tokens=resposta.prompt_eval_count + resposta.eval_count,
        ),
    )


def tokens_por_segundo(resposta: RespostaOllama) -> float | None:
    if resposta.eval_duration <= 0:
        return None

    return round(resposta.eval_count / (resposta.eval_duration / 1e9), 1)


@rotas.post("/chat/completions", responses=RESPOSTAS_DO_CHAT)
async def completar(request: Request) -> JSONResponse:
    config: Config = request.app.state.config
    limitador: Limitador = request.app.state.limitador
    cliente: httpx2.AsyncClient = request.app.state.cliente_ollama

    inicio = time.perf_counter()
    metricas: dict[str, Any] = {
        "modelo": None,
        "status": 500,
        "codigo": None,
        "erro": None,
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

        return JSONResponse(formatar(resposta, modelo).model_dump())
    except ErroOpenAI as erro:
        metricas["status"] = erro.status
        metricas["codigo"] = erro.codigo
        raise
    except Exception as falha:
        metricas["codigo"] = Codigo.ERRO_INTERNO
        metricas["erro"] = type(falha).__name__
        raise erro_interno() from None
    finally:
        metricas["duracao_ms"] = round((time.perf_counter() - inicio) * 1000)
        registrar_metricas(registro, "chat", metricas)

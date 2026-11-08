import json
import logging
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from llm_gateway.chat import LIMITE_DE_CARACTERES, LIMITE_DE_TOKENS, LIMITE_DO_CORPO, TOKENS_PADRAO
from llm_gateway.ollama import CONTEXTO
from tests.conftest import MODELO, TOKEN, OllamaFalso, autorizacao, resposta_do_ollama

ESQUEMA = {
    "type": "object",
    "properties": {"en": {"type": "string"}, "pt": {"type": "string"}},
    "required": ["en", "pt"],
    "additionalProperties": False,
}
PROMPT = "Escreva uma frase A1 sobre o café da manhã em casa."


def pedido(**campos: Any) -> dict[str, Any]:
    return {
        "model": MODELO,
        "messages": [{"role": "system", "content": "Responda só JSON."}, {"role": "user", "content": PROMPT}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "item", "schema": ESQUEMA, "strict": True}},
        "temperature": 0.7,
        "max_tokens": 300,
        **campos,
    }


def chat(cliente: TestClient, corpo: Any, **cabecalhos: str) -> httpx2.Response:
    return cliente.post("/v1/chat/completions", json=corpo, headers={**autorizacao(), **cabecalhos})


def erro(resposta: httpx2.Response) -> dict[str, Any]:
    corpo: dict[str, Any] = resposta.json()["error"]
    assert set(corpo) == {"message", "type", "param", "code"}

    return corpo


def test_caminho_feliz_com_schema_responde_no_formato_da_openai(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = chat(cliente, pedido())

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["object"] == "chat.completion"
    assert corpo["id"].startswith("chatcmpl-")
    assert isinstance(corpo["created"], int)
    assert corpo["model"] == MODELO
    assert corpo["choices"] == [
        {
            "index": 0,
            "message": {"role": "assistant", "content": '{"en": "I eat.", "pt": "Eu como."}'},
            "finish_reason": "stop",
        }
    ]
    assert corpo["usage"] == {"prompt_tokens": 63, "completion_tokens": 27, "total_tokens": 90}


def test_traduz_o_pedido_para_o_api_chat_do_ollama(cliente: TestClient, ollama: OllamaFalso) -> None:
    chat(cliente, pedido())

    assert ollama.pedidos == [
        {
            "caminho": "/api/chat",
            "corpo": {
                "model": MODELO,
                "messages": pedido()["messages"],
                "stream": False,
                "format": ESQUEMA,
                "options": {"num_ctx": CONTEXTO, "num_predict": 300, "temperature": 0.7},
            },
        }
    ]


def test_sem_response_format_nem_temperatura_usa_os_padroes(cliente: TestClient, ollama: OllamaFalso) -> None:
    ollama.responder_com(**resposta_do_ollama("texto livre, não JSON"))
    corpo = pedido()
    del corpo["response_format"], corpo["temperature"], corpo["max_tokens"]

    resposta = chat(cliente, corpo)

    assert resposta.status_code == 200
    assert resposta.json()["choices"][0]["message"]["content"] == "texto livre, não JSON"
    enviado = ollama.pedidos[0]["corpo"]
    assert "format" not in enviado
    assert enviado["options"] == {"num_ctx": CONTEXTO, "num_predict": TOKENS_PADRAO}


@pytest.mark.parametrize(("done_reason", "finish_reason"), [("stop", "stop"), ("length", "length"), (None, "stop")])
def test_mapeia_o_done_reason_sem_schema(
    cliente: TestClient, ollama: OllamaFalso, done_reason: str | None, finish_reason: str
) -> None:
    ollama.responder_com(**resposta_do_ollama("texto", done_reason=done_reason))

    resposta = chat(cliente, pedido(response_format=None))

    assert resposta.json()["choices"][0]["finish_reason"] == finish_reason


def test_usage_sem_contagem_do_ollama_vira_zero(cliente: TestClient, ollama: OllamaFalso) -> None:
    corpo = resposta_do_ollama()
    del corpo["prompt_eval_count"], corpo["eval_count"]
    ollama.responder_com(**corpo)

    assert chat(cliente, pedido()).json()["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_stream_true_responde_400(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = chat(cliente, pedido(stream=True))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "stream_nao_suportado"
    assert ollama.pedidos == []


def test_modelo_fora_da_allowlist_responde_404(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = chat(cliente, pedido(model="qwen3:4b"))

    assert resposta.status_code == 404
    assert erro(resposta)["code"] == "model_not_found"
    assert ollama.pedidos == []


def test_sem_token_responde_401_sem_chamar_o_ollama(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = cliente.post("/v1/chat/completions", json=pedido())

    assert resposta.status_code == 401
    assert ollama.pedidos == []


@pytest.mark.parametrize(
    ("campos", "trecho"),
    [
        ({"n": 2}, "corpo (campo não permitido)"),
        ({"messages": []}, "messages"),
        ({"messages": [{"role": "tool", "content": "x"}]}, "messages.0.role"),
        ({"messages": [{"role": "user", "content": ["parte"]}]}, "messages.0.content"),
        ({"messages": [{"role": "user", "content": "x"}] * 9}, "messages"),
        ({"messages": [{"role": "user", "content": "x" * (LIMITE_DE_CARACTERES + 1)}]}, "messages.0.content"),
        ({"max_tokens": LIMITE_DE_TOKENS + 1}, "max_tokens"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"temperature": 3}, "temperature"),
        ({"response_format": {"type": "json_object"}}, "response_format.json_schema, response_format.type"),
        (
            {"response_format": {"type": "json_schema", "json_schema": {"name": "a b", "schema": {}}}},
            "response_format.json_schema.name",
        ),
    ],
)
def test_pedido_fora_do_subconjunto_responde_400_sem_chamar_o_ollama(
    cliente: TestClient, ollama: OllamaFalso, campos: dict[str, Any], trecho: str
) -> None:
    resposta = chat(cliente, pedido(**campos))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "invalid_request"
    assert erro(resposta)["message"] == f"Pedido inválido em: {trecho}."
    assert ollama.pedidos == []


NOME_INVENTADO = 'x\ny"z<script>'
VALOR_INVENTADO = "valor-que-so-o-cliente-escreveu"


@pytest.mark.parametrize(
    ("onde", "esperado"),
    [
        ("raiz", "corpo (campo não permitido)"),
        ("mensagem", "messages.0 (campo não permitido)"),
        ("response_format", "response_format (campo não permitido)"),
        ("json_schema", "response_format.json_schema (campo não permitido)"),
    ],
)
def test_campo_desconhecido_nunca_ecoa_o_nome_nem_o_valor(
    cliente: TestClient, ollama: OllamaFalso, onde: str, esperado: str
) -> None:
    corpo = pedido()
    alvo = {
        "raiz": corpo,
        "mensagem": corpo["messages"][0],
        "response_format": corpo["response_format"],
        "json_schema": corpo["response_format"]["json_schema"],
    }[onde]
    alvo[NOME_INVENTADO] = VALOR_INVENTADO

    resposta = chat(cliente, corpo)

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "invalid_request"
    assert erro(resposta)["message"] == f"Pedido inválido em: {esperado}."
    for inventado in ("script", "x\\ny", VALOR_INVENTADO):
        assert inventado not in resposta.text
    assert ollama.pedidos == []


def test_a_mensagem_do_400_lista_no_maximo_5_caminhos(cliente: TestClient, ollama: OllamaFalso) -> None:
    mensagens = [{"role": "tool", "content": "x"}] * 8

    resposta = chat(cliente, pedido(messages=mensagens))

    assert resposta.status_code == 400
    caminhos = erro(resposta)["message"].removeprefix("Pedido inválido em: ").removesuffix(".").split(", ")
    assert len(caminhos) == 5
    assert all(caminho.startswith("messages.") and caminho.endswith(".role") for caminho in caminhos)
    assert ollama.pedidos == []


def test_nome_do_modelo_com_mais_de_100_caracteres_responde_400(cliente: TestClient, ollama: OllamaFalso) -> None:
    resposta = chat(cliente, pedido(model="m" * 101))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "invalid_request"
    assert "m" * 101 not in resposta.text
    assert ollama.pedidos == []


def test_nome_do_modelo_com_100_caracteres_passa_pelo_formato_e_cai_na_allowlist(
    cliente: TestClient, ollama: OllamaFalso
) -> None:
    resposta = chat(cliente, pedido(model="m" * 100))

    assert resposta.status_code == 404
    assert erro(resposta)["code"] == "model_not_found"
    assert len(erro(resposta)["message"]) < 200
    assert ollama.pedidos == []


def test_soma_das_mensagens_acima_do_limite_responde_400(cliente: TestClient) -> None:
    metade = "x" * (LIMITE_DE_CARACTERES // 2 + 1)
    mensagens = [{"role": "user", "content": metade}, {"role": "assistant", "content": metade}]

    resposta = chat(cliente, pedido(messages=mensagens))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "mensagens_grandes_demais"


def test_corpo_que_nao_e_json_responde_400(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/v1/chat/completions", content=b"{nao e json", headers={**autorizacao(), "Content-Type": "application/json"}
    )

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "invalid_request"


def test_corpo_acima_do_limite_responde_413(cliente: TestClient, ollama: OllamaFalso) -> None:
    grande = pedido(messages=[{"role": "user", "content": "x" * LIMITE_DO_CORPO}])

    resposta = chat(cliente, grande)

    assert resposta.status_code == 413
    assert erro(resposta)["code"] == "corpo_grande_demais"
    assert ollama.pedidos == []


def test_corpo_acima_do_limite_sem_content_length_responde_413(cliente: TestClient) -> None:
    def pedacos() -> Any:
        yield b'{"model": "' + b"x" * LIMITE_DO_CORPO
        yield b'"}'

    resposta = cliente.post("/v1/chat/completions", content=pedacos(), headers=autorizacao())

    assert resposta.status_code == 413


def test_schema_invalido_responde_400(cliente: TestClient, ollama: OllamaFalso) -> None:
    formato = {"type": "json_schema", "json_schema": {"name": "item", "schema": {"type": "objeto"}}}

    resposta = chat(cliente, pedido(response_format=formato))

    assert resposta.status_code == 400
    assert erro(resposta)["code"] == "schema_invalido"
    assert ollama.pedidos == []


SAIDA_SECRETA = "frase-que-so-o-modelo-escreveu"


@pytest.mark.parametrize(
    ("conteudo", "done_reason", "codigo"),
    [
        (f'{{"en": "{SAIDA_SECRETA}"', "stop", "saida_invalida"),
        (f'{{"en": "{SAIDA_SECRETA}"}}', "stop", "saida_invalida"),
        (f'{{"en": "{SAIDA_SECRETA}", "pt": 1}}', "stop", "saida_invalida"),
        (f'{{"en": "{SAIDA_SECRETA}", "pt": "x", "extra": "y"}}', "stop", "saida_invalida"),
        (f'{{"en": "{SAIDA_SECRETA}", "pt": "x"}}', "length", "saida_truncada"),
    ],
)
def test_saida_fora_do_schema_vira_502_sem_o_conteudo(
    cliente: TestClient,
    ollama: OllamaFalso,
    caplog: pytest.LogCaptureFixture,
    conteudo: str,
    done_reason: str,
    codigo: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    ollama.responder_com(**resposta_do_ollama(conteudo, done_reason=done_reason))

    resposta = chat(cliente, pedido())

    assert resposta.status_code == 502
    assert erro(resposta)["code"] == codigo
    assert erro(resposta)["type"] == "server_error"
    assert SAIDA_SECRETA not in resposta.text
    assert SAIDA_SECRETA not in caplog.text


def test_ollama_fora_do_ar_responde_503(cliente: TestClient, ollama: OllamaFalso) -> None:
    async def recusar(pedido: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("conexão recusada", request=pedido)

    ollama.responder = recusar

    resposta = chat(cliente, pedido())

    assert resposta.status_code == 503
    assert erro(resposta)["code"] == "upstream_indisponivel"


def test_timeout_do_ollama_responde_504(cliente: TestClient, ollama: OllamaFalso) -> None:
    async def demorar(pedido: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("demorou", request=pedido)

    ollama.responder = demorar

    resposta = chat(cliente, pedido())

    assert resposta.status_code == 504
    assert erro(resposta)["code"] == "upstream_timeout"


@pytest.mark.parametrize(
    ("status", "corpo", "codigo"),
    [
        (500, {"error": "segredo-do-upstream"}, "upstream_erro"),
        (404, {"error": "model 'segredo-do-upstream' not found"}, "upstream_erro"),
        (200, {"segredo-do-upstream": True}, "upstream_resposta_invalida"),
    ],
)
def test_resposta_estranha_do_ollama_responde_502_sem_vazar_o_corpo(
    cliente: TestClient, ollama: OllamaFalso, status: int, corpo: dict[str, Any], codigo: str
) -> None:
    ollama.responder_com(status, **corpo)

    resposta = chat(cliente, pedido())

    assert resposta.status_code == 502
    assert erro(resposta)["code"] == codigo
    assert "segredo-do-upstream" not in resposta.text


def test_corpo_do_ollama_que_nao_e_json_responde_502(cliente: TestClient, ollama: OllamaFalso) -> None:
    async def lixo(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>proxy</html>")

    ollama.responder = lixo

    resposta = chat(cliente, pedido())

    assert resposta.status_code == 502
    assert erro(resposta)["code"] == "upstream_resposta_invalida"


def linhas_de_metricas(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [registro.__dict__["metricas"] for registro in caplog.records if registro.name == "llm_gateway.chat"]


def test_cada_pedido_ao_chat_gera_uma_linha_de_metricas(
    cliente: TestClient, ollama: OllamaFalso, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    chat(cliente, pedido())
    chat(cliente, pedido(model="qwen3:4b"))

    sucesso, recusa = linhas_de_metricas(caplog)
    duracao = sucesso.pop("duracao_ms")
    assert isinstance(duracao, int)
    assert duracao >= 0
    assert sucesso == {
        "modelo": MODELO,
        "status": 200,
        "codigo": None,
        "erro": None,
        "prompt_tokens": 63,
        "completion_tokens": 27,
        "tokens_por_segundo": 50.0,
        "carga_ms": 4,
    }
    assert recusa["modelo"] is None
    assert recusa["status"] == 404
    assert recusa["codigo"] == "model_not_found"
    assert recusa["prompt_tokens"] is None


def test_linha_de_metricas_sai_em_json_numa_linha_so(
    cliente: TestClient, ollama: OllamaFalso, capfd: pytest.CaptureFixture[str]
) -> None:
    chat(cliente, pedido())

    linhas = [json.loads(linha) for linha in capfd.readouterr().out.splitlines() if '"evento": "chat"' in linha]

    assert len(linhas) == 1
    assert set(linhas[0]) == {
        "nivel",
        "evento",
        "modelo",
        "status",
        "codigo",
        "erro",
        "prompt_tokens",
        "completion_tokens",
        "tokens_por_segundo",
        "carga_ms",
        "duracao_ms",
    }


def test_prompt_resposta_schema_e_token_nunca_vao_para_o_log(
    cliente: TestClient, ollama: OllamaFalso, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    ollama.responder_com(**resposta_do_ollama(f'{{"en": "{SAIDA_SECRETA}", "pt": "x"}}'))

    chat(cliente, pedido())
    chat(cliente, pedido(stream=True))
    chat(cliente, pedido(), Authorization="Bearer errado")

    saida = caplog.text + capfd.readouterr().out
    for segredo in (PROMPT, SAIDA_SECRETA, TOKEN, "additionalProperties", "Responda só JSON"):
        assert segredo not in saida

import json

import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tests.conftest import MODELO, TOKEN, OllamaFalso
from tests.test_chat import ESQUEMA, PROMPT


class Frase(BaseModel):
    en: str
    pt: str


@pytest.fixture
def sdk(cliente: TestClient) -> openai.OpenAI:
    return openai.OpenAI(base_url="http://gateway/v1", api_key=TOKEN, http_client=cliente, max_retries=0)


def test_models_list_do_sdk_le_a_allowlist(sdk: openai.OpenAI) -> None:
    modelos = sdk.models.list()

    assert [modelo.id for modelo in modelos.data] == [MODELO]
    assert modelos.data[0].owned_by == "llm-gateway"


def test_chat_completions_create_com_json_schema_estrito(sdk: openai.OpenAI, ollama: OllamaFalso) -> None:
    resposta = sdk.chat.completions.create(
        model=MODELO,
        messages=[{"role": "system", "content": "Responda só JSON."}, {"role": "user", "content": PROMPT}],
        response_format={"type": "json_schema", "json_schema": {"name": "item", "schema": ESQUEMA, "strict": True}},
        temperature=0.7,
        max_tokens=300,
    )

    assert json.loads(resposta.choices[0].message.content or "") == {"en": "I eat.", "pt": "Eu como."}
    assert resposta.choices[0].finish_reason == "stop"
    assert resposta.usage is not None
    assert resposta.usage.total_tokens == 90
    assert ollama.pedidos[0]["corpo"]["format"] == ESQUEMA


def test_parse_com_modelo_pydantic_plano(sdk: openai.OpenAI) -> None:
    resposta = sdk.chat.completions.parse(
        model=MODELO,
        messages=[{"role": "user", "content": PROMPT}],
        response_format=Frase,
    )

    assert resposta.choices[0].message.parsed == Frase(en="I eat.", pt="Eu como.")

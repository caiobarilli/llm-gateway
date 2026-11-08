import json
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.app import criar_app
from llm_gateway.config import Config

TOKEN = "a1" * 32
MODELO = "llama3.2:3b"

Resposta = Callable[[httpx2.Request], Awaitable[httpx2.Response]]


def resposta_do_ollama(conteudo: str = '{"en": "I eat.", "pt": "Eu como."}', **campos: Any) -> dict[str, Any]:
    return {
        "model": MODELO,
        "created_at": "2026-11-05T12:00:00Z",
        "message": {"role": "assistant", "content": conteudo},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 63,
        "eval_count": 27,
        "eval_duration": 540_000_000,
        "load_duration": 4_000_000,
        "total_duration": 600_000_000,
        **campos,
    }


class OllamaFalso:
    def __init__(self) -> None:
        self.pedidos: list[dict[str, Any]] = []
        self.responder: Resposta = self._padrao

    async def _padrao(self, _: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=resposta_do_ollama())

    async def __call__(self, pedido: httpx2.Request) -> httpx2.Response:
        self.pedidos.append({"caminho": pedido.url.path, "corpo": json.loads(pedido.content)})

        return await self.responder(pedido)

    def responder_com(self, status: int = 200, **corpo: Any) -> None:
        async def responder(_: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(status, json=corpo)

        self.responder = responder


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def arquivo_do_token(tmp_path: Path) -> Path:
    arquivo = tmp_path / "gateway-token"
    arquivo.write_text(TOKEN)

    return arquivo


@pytest.fixture
def config(arquivo_do_token: Path) -> Config:
    return Config(
        token_arquivo=arquivo_do_token,
        modelos=(MODELO,),
        concorrencia=1,
        ollama_url="http://ollama.test:11434",
    )


@pytest.fixture
def ollama() -> OllamaFalso:
    return OllamaFalso()


@pytest.fixture
def app(config: Config, ollama: OllamaFalso) -> FastAPI:
    return criar_app(config, httpx2.MockTransport(ollama))


@pytest.fixture
def cliente(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as cliente:
        yield cliente


def autorizacao(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

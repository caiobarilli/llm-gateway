from pathlib import Path

import pytest

from llm_gateway.config import Config, ConfiguracaoInvalida

VALIDO = {
    "GATEWAY_TOKEN_ARQUIVO": "/run/secrets/llm-gateway-token",
    "GATEWAY_MODELOS": "llama3.2:3b",
    "GATEWAY_CONCORRENCIA": "1",
    "GATEWAY_OLLAMA_URL": "http://host.docker.internal:11434/",
}


def test_le_o_ambiente_com_tipos() -> None:
    config = Config.do_ambiente({**VALIDO, "GATEWAY_MODELOS": " llama3.2:3b , qwen3:4b ,,"})

    assert config == Config(
        token_arquivo=Path("/run/secrets/llm-gateway-token"),
        modelos=("llama3.2:3b", "qwen3:4b"),
        concorrencia=1,
        ollama_url="http://host.docker.internal:11434",
    )


@pytest.mark.parametrize(
    ("chave", "valor"),
    [
        ("GATEWAY_TOKEN_ARQUIVO", ""),
        ("GATEWAY_MODELOS", " , "),
        ("GATEWAY_CONCORRENCIA", "0"),
        ("GATEWAY_CONCORRENCIA", "um"),
        ("GATEWAY_CONCORRENCIA", ""),
        ("GATEWAY_OLLAMA_URL", "host.docker.internal:11434"),
    ],
)
def test_configuracao_invalida_impede_a_subida(chave: str, valor: str) -> None:
    with pytest.raises(ConfiguracaoInvalida):
        Config.do_ambiente({**VALIDO, chave: valor})


@pytest.mark.parametrize("chave", list(VALIDO))
def test_variavel_ausente_impede_a_subida(chave: str) -> None:
    ambiente = {k: v for k, v in VALIDO.items() if k != chave}

    with pytest.raises(ConfiguracaoInvalida):
        Config.do_ambiente(ambiente)

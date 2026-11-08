import json
import sys
from pathlib import Path
from typing import Any

from llm_gateway.app import criar_app
from llm_gateway.chat import Pedido
from llm_gateway.config import Config

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
MODELO_DE_REFERENCIA = "#/components/schemas/{model}"
ROTA_DO_CHAT = "/v1/chat/completions"
ESQUEMA_DE_SEGURANCA = "bearer"


def gerar() -> dict[str, Any]:
    config = Config(
        token_arquivo=Path("token"),
        modelos=("modelo-de-exemplo",),
        concorrencia=1,
        ollama_url="http://localhost:11434",
    )
    esquema: dict[str, Any] = criar_app(config).openapi()

    componentes: dict[str, Any] = esquema.setdefault("components", {})
    esquemas: dict[str, Any] = componentes.setdefault("schemas", {})
    pedido = Pedido.model_json_schema(ref_template=MODELO_DE_REFERENCIA)
    esquemas.update(pedido.pop("$defs", {}))
    esquemas["Pedido"] = pedido
    componentes.setdefault("securitySchemes", {})[ESQUEMA_DE_SEGURANCA] = {"type": "http", "scheme": "bearer"}

    for caminho, operacoes in esquema["paths"].items():
        if not caminho.startswith("/v1/"):
            continue

        for operacao in operacoes.values():
            operacao["security"] = [{ESQUEMA_DE_SEGURANCA: []}]

    esquema["paths"][ROTA_DO_CHAT]["post"]["requestBody"] = {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pedido"}}},
    }

    return esquema


def principal() -> int:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(gerar(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"exportar_openapi: {DESTINO.relative_to(DESTINO.parent.parent)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(principal())

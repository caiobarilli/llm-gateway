import json
import logging
import sys
from typing import Any, override

RAIZ = "llm_gateway"
ATRIBUTO_DAS_METRICAS = "metricas"


class FormatoJson(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord) -> str:
        linha: dict[str, Any] = {"nivel": record.levelname.lower(), "evento": record.getMessage()}
        metricas = getattr(record, ATRIBUTO_DAS_METRICAS, None)
        if isinstance(metricas, dict):
            linha.update(metricas)

        return json.dumps(linha, ensure_ascii=False)


class SaidaPadrao(logging.Handler):
    @override
    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def configurar_registro() -> None:
    raiz = logging.getLogger(RAIZ)
    if any(isinstance(saida.formatter, FormatoJson) for saida in raiz.handlers):
        return

    saida = SaidaPadrao()
    saida.setFormatter(FormatoJson())
    raiz.addHandler(saida)
    raiz.setLevel(logging.INFO)


def registrar_metricas(registro: logging.Logger, evento: str, metricas: dict[str, Any]) -> None:
    registro.info(evento, extra={ATRIBUTO_DAS_METRICAS: metricas})

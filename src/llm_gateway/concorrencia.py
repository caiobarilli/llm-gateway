import threading
from collections.abc import Iterator
from contextlib import contextmanager

from llm_gateway.erros import ErroOpenAI

ESPERA_SUGERIDA_EM_SEGUNDOS = 10


class Limitador:
    def __init__(self, vagas: int, espera_sugerida: int = ESPERA_SUGERIDA_EM_SEGUNDOS) -> None:
        self._vagas = vagas
        self._ocupadas = 0
        self._espera_sugerida = espera_sugerida
        self._trava = threading.Lock()

    @property
    def ocupadas(self) -> int:
        return self._ocupadas

    @contextmanager
    def vaga(self) -> Iterator[None]:
        with self._trava:
            if self._ocupadas >= self._vagas:
                raise ErroOpenAI(
                    503,
                    "O gateway está ocupado. Tente de novo em instantes.",
                    "server_error",
                    "ocupado",
                    {"Retry-After": str(self._espera_sugerida)},
                )
            self._ocupadas += 1

        try:
            yield
        finally:
            with self._trava:
                self._ocupadas -= 1

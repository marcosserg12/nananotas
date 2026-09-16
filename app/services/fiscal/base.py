from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.venda import Venda


@dataclass
class ResultadoFiscal:
    referencia: str
    status: str
    numero: str | None = None
    serie: str | None = None
    chave_acesso: str | None = None
    protocolo: str | None = None
    url_danfe: str | None = None
    url_xml: str | None = None
    mensagem_erro: str | None = None


class FiscalProvider(ABC):
    @abstractmethod
    def emitir(self, venda: Venda) -> ResultadoFiscal:
        ...

    @abstractmethod
    def consultar(self, referencia: str) -> ResultadoFiscal:
        ...

    @abstractmethod
    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        ...

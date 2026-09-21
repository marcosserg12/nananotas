import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class StatusNota(str, enum.Enum):
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), unique=True, nullable=False)
    provedor = Column(String(30), nullable=False, default="focus_nfe")
    referencia = Column(String(50), nullable=False)
    status = Column(Enum(StatusNota), nullable=False, default=StatusNota.PROCESSANDO)
    numero = Column(String(20), nullable=True)
    serie = Column(String(10), nullable=True)
    chave_acesso = Column(String(44), nullable=True)
    protocolo = Column(String(30), nullable=True)
    url_danfe = Column(String(255), nullable=True)
    url_xml = Column(String(255), nullable=True)
    mensagem_erro = Column(Text, nullable=True)
    # Momento (UTC) em que a nota passou a "autorizada" pela primeira vez --
    # usado só para exibir "Data de Autorização" no DANFE (ver
    # app/services/fiscal/sefaz_direto/xml_builder.py::FUSO_BRASILIA pro
    # padrão de conversão pra hora de Brasília). Nunca sobrescrito depois de
    # preenchido, mesmo que a nota seja reconsultada várias vezes.
    autorizado_em = Column(DateTime, nullable=True)
    # Momento (UTC) do último envio bem-sucedido do cupom por e-mail pro
    # cliente -- sobrescrito a cada reenvio (ao contrário de `autorizado_em`),
    # porque aqui o que importa é "quando foi a última vez", não "a primeira".
    email_enviado_em = Column(DateTime, nullable=True)

    venda = relationship("Venda")

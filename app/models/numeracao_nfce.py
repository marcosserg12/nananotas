from sqlalchemy import Column, Integer, String

from app.database import Base


class NumeracaoNFCe(Base):
    __tablename__ = "numeracao_nfce"

    id = Column(Integer, primary_key=True)
    serie = Column(Integer, nullable=False, unique=True)
    ultimo_numero = Column(Integer, nullable=False, default=0)
    # Lista de inteiros separados por vírgula (ex.: "5,7,12") -- números
    # reservados via `reservar_proximo_numero` que nunca chegaram a ser
    # autorizados pela Sefaz (falha de assinatura, erro de rede, etc.) e
    # portanto precisam de um pedido de inutilização formal para fechar o
    # "buraco" na numeração exigida pela legislação fiscal. Formato texto
    # simples (não uma tabela própria) porque este sistema emite uma nota por
    # vez para um restaurante pequeno -- volume de falhas esperado é baixo o
    # suficiente para não justificar uma tabela dedicada.
    numeros_pendentes_inutilizacao = Column(String(1000), nullable=False, default="")

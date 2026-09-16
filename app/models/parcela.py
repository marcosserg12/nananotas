import enum
from datetime import date

from sqlalchemy import Column, Date, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship

from app.database import Base


class StatusParcela(str, enum.Enum):
    ABERTO = "aberto"
    PAGO = "pago"


class Parcela(Base):
    __tablename__ = "parcelas"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), nullable=False)
    numero = Column(Integer, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    vencimento = Column(Date, nullable=False)
    status = Column(Enum(StatusParcela), nullable=False, default=StatusParcela.ABERTO)

    venda = relationship("Venda")

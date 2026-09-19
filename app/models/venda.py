import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class StatusVenda(str, enum.Enum):
    ORCAMENTO = "orcamento"
    PAGO = "pago"
    CANCELADO = "cancelado"


class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True)
    numero_orcamento = Column(Integer, unique=True, nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    data_venda = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(Enum(StatusVenda), nullable=False, default=StatusVenda.ORCAMENTO)
    forma_pagamento = Column(String(30), nullable=True)
    bandeira = Column(String(2), nullable=True)
    valor_total = Column(Numeric(10, 2), nullable=False, default=0)
    valor_pago = Column(Numeric(10, 2), nullable=True)
    troco = Column(Numeric(10, 2), nullable=True)

    cliente = relationship("Cliente")
    itens = relationship("VendaItem", back_populates="venda", cascade="all, delete-orphan")


class VendaItem(Base):
    __tablename__ = "venda_itens"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), nullable=False)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Numeric(10, 2), nullable=False, default=1)
    preco_unitario = Column(Numeric(10, 2), nullable=False)

    venda = relationship("Venda", back_populates="itens")
    produto = relationship("Produto")

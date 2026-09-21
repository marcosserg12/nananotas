from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, false
from sqlalchemy.orm import relationship

from app.database import Base


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True)
    codigo_interno = Column(String(50), nullable=False)
    nome = Column(String(200), nullable=False)
    codigo_fabricante = Column(String(50), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    ncm = Column(String(8), nullable=False)
    unidade = Column(String(6), nullable=False, default="UN")
    preco_custo = Column(Numeric(10, 2), nullable=False, default=0)
    preco_venda = Column(Numeric(10, 2), nullable=False)
    preco_atacado = Column(Numeric(10, 2), nullable=True)
    estoque_atual = Column(Numeric(10, 2), nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True)
    # Gerador de valor (ver gerador_itens_service): quando ligado, o produto
    # pode ser sorteado pra fechar um valor total, com esta chance (1-100%) de
    # aparecer e um preço unitário escolhido entre o mínimo e o máximo.
    gerador_ativo = Column(Boolean, nullable=False, default=False, server_default=false())
    gerador_chance = Column(Integer, nullable=False, default=100, server_default="100")
    gerador_preco_min = Column(Numeric(10, 2), nullable=True)
    gerador_preco_max = Column(Numeric(10, 2), nullable=True)

    categoria = relationship("Categoria")

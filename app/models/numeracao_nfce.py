from sqlalchemy import Column, Integer

from app.database import Base


class NumeracaoNFCe(Base):
    __tablename__ = "numeracao_nfce"

    id = Column(Integer, primary_key=True)
    serie = Column(Integer, nullable=False, unique=True)
    ultimo_numero = Column(Integer, nullable=False, default=0)

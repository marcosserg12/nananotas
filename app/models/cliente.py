import enum

from sqlalchemy import Boolean, Column, Enum, Integer, String

from app.database import Base


class TipoPessoa(str, enum.Enum):
    PF = "PF"
    PJ = "PJ"


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True)
    tipo_pessoa = Column(Enum(TipoPessoa), nullable=False, default=TipoPessoa.PF)
    nome = Column(String(200), nullable=False)
    cpf_cnpj = Column(String(18), nullable=True)
    ie = Column(String(20), nullable=True)
    endereco = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    email = Column(String(120), nullable=True)
    consumidor_final = Column(Boolean, nullable=False, default=False)

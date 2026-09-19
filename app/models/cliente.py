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
    # "normal" ou "isento" -- só é relevante para PJ; usado em
    # xml_builder._montar_dest para decidir indIEDest quando o cliente não
    # tem IE preenchida (isento de inscrição estadual, não "não contribuinte").
    tipo_inscricao_estadual = Column(String(10), nullable=True)
    endereco_cep = Column(String(9), nullable=True)
    endereco_logradouro = Column(String(200), nullable=True)
    endereco_numero = Column(String(20), nullable=True)
    endereco_complemento = Column(String(100), nullable=True)
    endereco_bairro = Column(String(100), nullable=True)
    endereco_cidade = Column(String(100), nullable=True)
    endereco_uf = Column(String(2), nullable=True)
    telefone = Column(String(20), nullable=True)
    email = Column(String(120), nullable=True)
    consumidor_final = Column(Boolean, nullable=False, default=False)

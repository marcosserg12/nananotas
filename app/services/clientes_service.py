from sqlalchemy.orm import Session

from app.models.cliente import Cliente, TipoPessoa

NOME_CONSUMIDOR_FINAL = "AO CONSUMIDOR"


def garantir_consumidor_final(db: Session) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.consumidor_final.is_(True)).first()
    if cliente is None:
        cliente = Cliente(nome=NOME_CONSUMIDOR_FINAL, tipo_pessoa=TipoPessoa.PF, consumidor_final=True)
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
    return cliente


def listar_clientes(db: Session) -> list[Cliente]:
    return db.query(Cliente).order_by(Cliente.nome).all()


def criar_cliente(
    db: Session,
    *,
    tipo_pessoa: TipoPessoa,
    nome: str,
    cpf_cnpj: str | None = None,
    ie: str | None = None,
    endereco: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
) -> Cliente:
    cliente = Cliente(
        tipo_pessoa=tipo_pessoa,
        nome=nome,
        cpf_cnpj=cpf_cnpj,
        ie=ie,
        endereco=endereco,
        telefone=telefone,
        email=email,
        consumidor_final=False,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def atualizar_cliente(db: Session, cliente_id: int, **campos) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError("Cliente não encontrado")
    if cliente.consumidor_final:
        raise ValueError("Cliente padrão Consumidor Final não pode ser editado")
    for campo, valor in campos.items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


def buscar_clientes(db: Session, termo: str) -> list[Cliente]:
    padrao = f"%{termo}%"
    return (
        db.query(Cliente)
        .filter((Cliente.nome.ilike(padrao)) | (Cliente.cpf_cnpj.ilike(padrao)))
        .order_by(Cliente.nome)
        .limit(10)
        .all()
    )

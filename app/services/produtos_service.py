from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.categoria import Categoria
from app.models.produto import Produto


def listar_produtos_por_categoria(db: Session) -> list[tuple[Categoria, list[Produto]]]:
    categorias = db.query(Categoria).order_by(Categoria.nome).all()
    resultado = []
    for categoria in categorias:
        produtos = (
            db.query(Produto)
            .filter(Produto.categoria_id == categoria.id)
            .order_by(Produto.nome)
            .all()
        )
        resultado.append((categoria, produtos))
    return resultado


def obter_ou_criar_categoria(db: Session, nome: str) -> Categoria:
    categoria = db.query(Categoria).filter(Categoria.nome == nome).first()
    if categoria is None:
        categoria = Categoria(nome=nome)
        db.add(categoria)
        db.commit()
        db.refresh(categoria)
    return categoria


def criar_produto(
    db: Session,
    *,
    codigo_interno: str,
    nome: str,
    categoria_nome: str,
    ncm: str,
    unidade: str,
    preco_venda: Decimal,
    codigo_fabricante: str | None = None,
    preco_custo: Decimal = Decimal("0"),
    preco_atacado: Decimal | None = None,
    estoque_atual: Decimal = Decimal("0"),
) -> Produto:
    categoria = obter_ou_criar_categoria(db, categoria_nome)
    produto = Produto(
        codigo_interno=codigo_interno,
        nome=nome,
        codigo_fabricante=codigo_fabricante,
        categoria_id=categoria.id,
        ncm=ncm,
        unidade=unidade,
        preco_custo=preco_custo,
        preco_venda=preco_venda,
        preco_atacado=preco_atacado,
        estoque_atual=estoque_atual,
        ativo=True,
    )
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto


def atualizar_produto(db: Session, produto_id: int, **campos) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    for campo, valor in campos.items():
        setattr(produto, campo, valor)
    db.commit()
    db.refresh(produto)
    return produto


def alternar_ativo(db: Session, produto_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    produto.ativo = not produto.ativo
    db.commit()
    db.refresh(produto)
    return produto


def buscar_produtos(db: Session, termo: str) -> list[Produto]:
    padrao = f"%{termo}%"
    return (
        db.query(Produto)
        .filter(Produto.ativo.is_(True))
        .filter((Produto.nome.ilike(padrao)) | (Produto.codigo_interno.ilike(padrao)))
        .order_by(Produto.nome)
        .limit(10)
        .all()
    )

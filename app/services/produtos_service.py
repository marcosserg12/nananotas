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


def validar_config_gerador(produto: Produto) -> None:
    """Chance entre 1 e 100; a faixa de preço é opcional (sem ela o produto
    simplesmente não entra no gerador), mas se vier tem que estar completa e
    coerente -- senão o gerador falharia só na hora de vender."""
    chance = produto.gerador_chance
    if chance is None or not 1 <= chance <= 100:
        raise ValueError("A chance de aparecer precisa estar entre 1 e 100")
    minimo, maximo = produto.gerador_preco_min, produto.gerador_preco_max
    if minimo is None and maximo is None:
        return
    if minimo is None or maximo is None:
        raise ValueError("Informe o preço mínimo e o preço máximo (ou deixe os dois em branco)")
    if minimo <= 0:
        raise ValueError("O preço mínimo precisa ser maior que zero")
    if maximo < minimo:
        raise ValueError("O preço máximo não pode ser menor que o mínimo")


def _com_faixa_do_gerador(consulta):
    return consulta.filter(
        Produto.ativo.is_(True),
        Produto.gerador_preco_min.isnot(None),
        Produto.gerador_preco_max.isnot(None),
    )


def listar_candidatos_gerador(db: Session) -> list[Produto]:
    return _com_faixa_do_gerador(db.query(Produto)).order_by(Produto.nome).all()


def contar_produtos_sem_faixa_do_gerador(db: Session) -> int:
    total_ativos = db.query(Produto).filter(Produto.ativo.is_(True)).count()
    return total_ativos - _com_faixa_do_gerador(db.query(Produto)).count()


def salvar_config_gerador(db: Session, configs: list[dict]) -> None:
    """Grava a configuração do gerador de vários produtos de uma vez, tudo ou
    nada: se qualquer produto estiver inválido, nada é salvo. Cada item de
    `configs` tem `produto_id`, `chance`, `preco_min`, `preco_max`."""
    try:
        for config in configs:
            produto = db.get(Produto, config["produto_id"])
            if produto is None:
                raise ValueError("Produto não encontrado")
            produto.gerador_chance = config["chance"]
            produto.gerador_preco_min = config["preco_min"]
            produto.gerador_preco_max = config["preco_max"]
            try:
                validar_config_gerador(produto)
            except ValueError as exc:
                raise ValueError(f"{produto.nome}: {exc}") from exc
        db.commit()
    except ValueError:
        db.rollback()
        raise


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
    gerador_chance: int = 100,
    gerador_preco_min: Decimal | None = None,
    gerador_preco_max: Decimal | None = None,
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
        gerador_chance=gerador_chance,
        gerador_preco_min=gerador_preco_min,
        gerador_preco_max=gerador_preco_max,
    )
    validar_config_gerador(produto)
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
    try:
        validar_config_gerador(produto)
    except ValueError:
        db.rollback()
        raise
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


def listar_produtos_ativos(db: Session) -> list[Produto]:
    return db.query(Produto).filter(Produto.ativo.is_(True)).order_by(Produto.nome).all()


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

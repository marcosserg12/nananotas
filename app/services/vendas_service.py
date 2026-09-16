from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.produto import Produto
from app.models.venda import StatusVenda, Venda, VendaItem


def proximo_numero_orcamento(db: Session) -> int:
    ultimo = db.query(Venda).order_by(Venda.numero_orcamento.desc()).first()
    return (ultimo.numero_orcamento + 1) if ultimo else 1


def criar_venda(db: Session, cliente_id: int) -> Venda:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError("Cliente não encontrado")
    venda = Venda(
        numero_orcamento=proximo_numero_orcamento(db),
        cliente_id=cliente_id,
        status=StatusVenda.ORCAMENTO,
        valor_total=Decimal("0"),
    )
    db.add(venda)
    db.commit()
    db.refresh(venda)
    return venda


def adicionar_item(db: Session, venda_id: int, produto_id: int, quantidade: Decimal) -> VendaItem:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    item = VendaItem(
        venda_id=venda_id,
        produto_id=produto_id,
        quantidade=quantidade,
        preco_unitario=produto.preco_venda,
    )
    db.add(item)
    db.commit()
    recalcular_total(db, venda_id)
    db.refresh(item)
    return item


def remover_item(db: Session, item_id: int) -> None:
    item = db.get(VendaItem, item_id)
    if item is None:
        raise ValueError("Item não encontrado")
    venda_id = item.venda_id
    db.delete(item)
    db.commit()
    recalcular_total(db, venda_id)


def recalcular_total(db: Session, venda_id: int) -> Decimal:
    venda = db.get(Venda, venda_id)
    total = sum((item.quantidade * item.preco_unitario for item in venda.itens), Decimal("0"))
    venda.valor_total = total
    db.commit()
    return total

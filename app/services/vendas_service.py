from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.nota_fiscal import NotaFiscal
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


def adicionar_item(
    db: Session,
    venda_id: int,
    produto_id: int,
    quantidade: Decimal,
    preco_unitario: Decimal | None = None,
) -> VendaItem:
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
        preco_unitario=preco_unitario if preco_unitario is not None else produto.preco_venda,
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


def cancelar_venda(db: Session, venda_id: int) -> Venda:
    """Cancela um orçamento/venda que ainda não tem nota fiscal com chave de
    acesso -- se já tiver, a nota precisa ser cancelada na Sefaz primeiro
    (fluxo separado, `notas_service.cancelar_nota`), nunca só apagada daqui.
    Se a venda já estava paga, devolve o estoque que `confirmar_venda`
    baixou -- senão o produto ficaria com estoque a menos por uma venda que
    nunca aconteceu de verdade."""
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status == StatusVenda.CANCELADO:
        raise ValueError("Venda já está cancelada")

    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is not None and nota.chave_acesso:
        raise ValueError(
            "Esta venda já tem uma nota fiscal com chave de acesso -- cancele a nota fiscal primeiro, não a venda"
        )

    if venda.status == StatusVenda.PAGO:
        for item in venda.itens:
            produto = db.get(Produto, item.produto_id)
            produto.estoque_atual = produto.estoque_atual + item.quantidade

    venda.status = StatusVenda.CANCELADO
    db.commit()
    db.refresh(venda)
    return venda


def listar_orcamentos(db: Session) -> list[Venda]:
    """Vendas que ainda podem ser editadas/excluídas livremente: ainda em
    orçamento, ou já pagas mas sem uma nota fiscal com chave de acesso --
    a mesma condição que `cancelar_venda` usa pra permitir excluir (ver
    docstring lá). Uma venda paga cuja nota já tem chave de acesso "vira"
    nota fiscal de verdade e sai desta lista -- só pode ser desfeita
    cancelando a nota (`notas_service.cancelar_nota`), nunca excluindo a
    venda. Vendas já canceladas também não aparecem aqui: não têm mais
    nada de útil pra fazer com elas."""
    subquery_vendas_com_nota_valida = (
        db.query(NotaFiscal.venda_id).filter(NotaFiscal.chave_acesso.isnot(None)).subquery()
    )
    return (
        db.query(Venda)
        .filter(Venda.status != StatusVenda.CANCELADO)
        .filter(Venda.id.notin_(db.query(subquery_vendas_com_nota_valida)))
        .order_by(Venda.id.desc())
        .all()
    )


def recalcular_total(db: Session, venda_id: int) -> Decimal:
    venda = db.get(Venda, venda_id)
    total = sum((item.quantidade * item.preco_unitario for item in venda.itens), Decimal("0"))
    venda.valor_total = total
    db.commit()
    return total

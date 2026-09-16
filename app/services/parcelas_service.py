from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.parcela import Parcela
from app.models.produto import Produto
from app.models.venda import StatusVenda, Venda


def gerar_parcelas(
    db: Session,
    venda_id: int,
    forma_pagamento: str,
    numero_parcelas: int,
    primeiro_vencimento: date | None = None,
) -> list[Parcela]:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if numero_parcelas < 1:
        raise ValueError("Número de parcelas deve ser ao menos 1")

    db.query(Parcela).filter(Parcela.venda_id == venda_id).delete()

    valor_parcela = (venda.valor_total / numero_parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valores = [valor_parcela] * numero_parcelas
    diferenca = venda.valor_total - (valor_parcela * numero_parcelas)
    valores[-1] += diferenca

    base = primeiro_vencimento or date.today()
    parcelas = []
    for i, valor in enumerate(valores, start=1):
        parcela = Parcela(
            venda_id=venda_id,
            numero=i,
            valor=valor,
            vencimento=base + timedelta(days=30 * (i - 1)),
        )
        db.add(parcela)
        parcelas.append(parcela)

    venda.forma_pagamento = forma_pagamento
    db.commit()
    for parcela in parcelas:
        db.refresh(parcela)
    return parcelas


def confirmar_venda(db: Session, venda_id: int, valor_pago: Decimal) -> Venda:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status != StatusVenda.ORCAMENTO:
        raise ValueError("Venda já foi confirmada ou cancelada")

    for item in venda.itens:
        produto = db.get(Produto, item.produto_id)
        produto.estoque_atual = produto.estoque_atual - item.quantidade

    venda.valor_pago = valor_pago
    venda.troco = max(valor_pago - venda.valor_total, Decimal("0"))
    venda.status = StatusVenda.PAGO
    db.commit()
    db.refresh(venda)
    return venda

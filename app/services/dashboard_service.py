from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.venda import StatusVenda, Venda


def vendas_do_dia(db: Session, dia: date | None = None) -> list[Venda]:
    dia = dia or date.today()
    inicio = datetime.combine(dia, time.min)
    fim = datetime.combine(dia, time.max)
    return (
        db.query(Venda)
        .filter(Venda.data_venda >= inicio, Venda.data_venda <= fim)
        .filter(Venda.status == StatusVenda.PAGO)
        .order_by(Venda.data_venda.desc())
        .all()
    )


def total_vendido_no_dia(db: Session, dia: date | None = None) -> Decimal:
    vendas = vendas_do_dia(db, dia)
    return sum((venda.valor_total for venda in vendas), Decimal("0"))

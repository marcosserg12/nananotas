from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.venda import StatusVenda, Venda

# Brasilia is a fixed UTC-3 offset (Brazil abolished DST nationally in 2019),
# so a hardcoded offset is correct and avoids relying on the server's local
# timezone configuration (which caused sales made late in the local evening,
# already "tomorrow" in UTC, to fall outside the computed day window).
FUSO_BRASILIA = timedelta(hours=-3)


def _hoje_brasilia() -> date:
    """Data atual observada em Brasilia, calculada a partir do UTC."""
    return (datetime.utcnow() + FUSO_BRASILIA).date()


def vendas_do_dia(db: Session, dia: date | None = None) -> list[Venda]:
    dia = dia or _hoje_brasilia()
    inicio_local = datetime.combine(dia, time.min)
    fim_local = datetime.combine(dia, time.max)
    inicio = inicio_local - FUSO_BRASILIA
    fim = fim_local - FUSO_BRASILIA
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

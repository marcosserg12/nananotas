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


def formatar_hora_local(momento_utc: datetime) -> str:
    """Converte um datetime UTC (como `Venda.data_venda`) para o horário
    exibido em Brasília -- regressão real encontrada na tela: o painel
    formatava `venda.data_venda` (gravado em UTC) direto com `.strftime()`,
    mostrando a hora 3h adiantada."""
    return (momento_utc + FUSO_BRASILIA).strftime("%H:%M")


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


_MESES_ABREV = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]

_DIAS_SEMANA_ABREV = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def vendas_por_dia_semana(db: Session, dias: int = 7) -> list[dict]:
    """Total vendido por dia (Brasília), dos últimos `dias` dias até hoje
    inclusive -- usado pelo gráfico "Vendas da semana" do painel."""
    hoje = _hoje_brasilia()
    resultado = []
    for i in range(dias - 1, -1, -1):
        dia = hoje - timedelta(days=i)
        total = total_vendido_no_dia(db, dia)
        resultado.append(
            {"label": f"{_DIAS_SEMANA_ABREV[dia.weekday()]} {dia.strftime('%d/%m')}", "total": float(total)}
        )
    return resultado


def _primeiro_dia_do_mes(dia: date) -> date:
    return date(dia.year, dia.month, 1)


def _mes_seguinte(dia: date) -> date:
    if dia.month == 12:
        return date(dia.year + 1, 1, 1)
    return date(dia.year, dia.month + 1, 1)


def _voltar_meses(dia: date, meses: int) -> date:
    """Volta `meses` meses a partir do primeiro dia do mês de `dia`."""
    ano, mes = dia.year, dia.month
    total_meses = ano * 12 + (mes - 1) - meses
    return date(total_meses // 12, total_meses % 12 + 1, 1)


def vendas_por_mes(db: Session, meses: int = 6) -> list[dict]:
    """Total vendido por mês (Brasília), dos últimos `meses` meses até o mês
    atual inclusive -- usado pelo gráfico "Vendas dos últimos meses".

    Busca as vendas pagas desde o início da janela e soma em Python
    (agrupando pelo mês já ajustado pro fuso de Brasília), em vez de fazer
    isso via SQL -- evita depender de funções de data específicas do MySQL
    e mantém a mesma lógica de fuso horário usada no resto do módulo."""
    primeiro_mes_janela = _voltar_meses(_primeiro_dia_do_mes(_hoje_brasilia()), meses - 1)
    inicio_utc = datetime.combine(primeiro_mes_janela, time.min) - FUSO_BRASILIA

    vendas = (
        db.query(Venda)
        .filter(Venda.status == StatusVenda.PAGO)
        .filter(Venda.data_venda >= inicio_utc)
        .all()
    )

    totais_por_mes: dict[tuple[int, int], Decimal] = {}
    for venda in vendas:
        data_local = venda.data_venda + FUSO_BRASILIA
        chave = (data_local.year, data_local.month)
        totais_por_mes[chave] = totais_por_mes.get(chave, Decimal("0")) + venda.valor_total

    resultado = []
    mes_atual = primeiro_mes_janela
    for _ in range(meses):
        total = totais_por_mes.get((mes_atual.year, mes_atual.month), Decimal("0"))
        resultado.append({"label": f"{_MESES_ABREV[mes_atual.month - 1]}/{mes_atual.strftime('%y')}", "total": float(total)})
        mes_atual = _mes_seguinte(mes_atual)
    return resultado

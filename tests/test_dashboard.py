from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services import clientes_service, dashboard_service, parcelas_service, produtos_service, vendas_service


def _venda_paga(db_session, preco="10.00"):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco), estoque_atual=Decimal("10"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal(preco))
    return venda


def test_vendas_do_dia_retorna_apenas_vendas_pagas_de_hoje(db_session):
    venda_hoje = _venda_paga(db_session, preco="10.00")
    venda_antiga = _venda_paga(db_session, preco="20.00")
    venda_antiga.data_venda = venda_antiga.data_venda - timedelta(days=2)
    db_session.commit()

    resultado = dashboard_service.vendas_do_dia(db_session)

    ids = [venda.id for venda in resultado]
    assert venda_hoje.id in ids
    assert venda_antiga.id not in ids


def test_total_vendido_no_dia_soma_vendas_pagas(db_session):
    _venda_paga(db_session, preco="10.00")
    _venda_paga(db_session, preco="15.00")

    total = dashboard_service.total_vendido_no_dia(db_session)

    assert total == Decimal("25.00")


def test_formatar_hora_local_converte_utc_para_brasilia():
    """Regressão real vista na tela: o painel mostrava a hora gravada em UTC
    direto, 3h adiantada em relação à hora real de Brasília."""
    momento_utc = datetime(2026, 9, 18, 14, 30)

    assert dashboard_service.formatar_hora_local(momento_utc) == "11:30"


def test_vendas_por_dia_semana_retorna_7_dias_terminando_hoje(db_session):
    _venda_paga(db_session, preco="10.00")

    resultado = dashboard_service.vendas_por_dia_semana(db_session)

    assert len(resultado) == 7
    hoje = dashboard_service._hoje_brasilia()
    assert resultado[-1]["label"].endswith(hoje.strftime("%d/%m"))
    assert resultado[-1]["total"] == 10.0
    assert resultado[0]["total"] == 0.0


def test_vendas_por_dia_semana_quantidade_customizada(db_session):
    resultado = dashboard_service.vendas_por_dia_semana(db_session, dias=3)

    assert len(resultado) == 3


def test_vendas_por_mes_inclui_o_mes_atual_com_o_total_correto(db_session):
    _venda_paga(db_session, preco="10.00")
    _venda_paga(db_session, preco="5.00")

    resultado = dashboard_service.vendas_por_mes(db_session, meses=6)

    assert len(resultado) == 6
    assert resultado[-1]["total"] == 15.0


def test_vendas_por_mes_ignora_vendas_fora_da_janela(db_session):
    venda = _venda_paga(db_session, preco="10.00")
    venda.data_venda = venda.data_venda - timedelta(days=400)
    db_session.commit()

    resultado = dashboard_service.vendas_por_mes(db_session, meses=6)

    assert sum(mes["total"] for mes in resultado) == 0.0


def test_vendas_por_mes_ignora_venda_ainda_em_orcamento(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    vendas_service.criar_venda(db_session, cliente.id)

    resultado = dashboard_service.vendas_por_mes(db_session, meses=6)

    assert sum(mes["total"] for mes in resultado) == 0.0


def test_vendas_do_dia_exclui_venda_ainda_em_orcamento(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("10"),
    )
    venda_paga = _venda_paga(db_session, preco="10.00")
    venda_orcamento = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda_orcamento.id, produto.id, Decimal("1"))

    resultado = dashboard_service.vendas_do_dia(db_session)
    total = dashboard_service.total_vendido_no_dia(db_session)

    ids = [venda.id for venda in resultado]
    assert venda_paga.id in ids
    assert venda_orcamento.id not in ids
    assert total == Decimal("10.00")

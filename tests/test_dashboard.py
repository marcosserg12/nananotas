from datetime import date, timedelta
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

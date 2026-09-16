from decimal import Decimal

from app.models.venda import StatusVenda
from app.services import clientes_service, produtos_service, vendas_service


def _criar_produto(db_session, preco="10.00"):
    return produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco),
    )


def test_criar_venda_gera_numero_de_orcamento_sequencial(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)

    venda1 = vendas_service.criar_venda(db_session, cliente.id)
    venda2 = vendas_service.criar_venda(db_session, cliente.id)

    assert venda1.numero_orcamento == 1
    assert venda2.numero_orcamento == 2
    assert venda1.status == StatusVenda.ORCAMENTO


def test_adicionar_item_usa_preco_do_produto_e_recalcula_total(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session, preco="10.00")
    venda = vendas_service.criar_venda(db_session, cliente.id)

    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))
    db_session.refresh(venda)

    assert venda.valor_total == Decimal("20.00")
    assert len(venda.itens) == 1


def test_adicionar_item_com_preco_informado_sobrescreve_preco_do_produto(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session, preco="10.00")
    venda = vendas_service.criar_venda(db_session, cliente.id)

    item = vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"), preco_unitario=Decimal("8.00"))
    db_session.refresh(venda)

    assert item.preco_unitario == Decimal("8.00")
    assert venda.valor_total == Decimal("16.00")


def test_remover_item_recalcula_total(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session, preco="10.00")
    venda = vendas_service.criar_venda(db_session, cliente.id)
    item = vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))

    vendas_service.remover_item(db_session, item.id)
    db_session.refresh(venda)

    assert venda.valor_total == Decimal("0")
    assert len(venda.itens) == 0

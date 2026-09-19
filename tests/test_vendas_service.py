from decimal import Decimal

import pytest

from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.venda import StatusVenda
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


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


def test_cancelar_venda_paga_devolve_estoque_e_marca_cancelada(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("20.00"))
    db_session.refresh(produto)
    assert produto.estoque_atual == Decimal("3")

    vendas_service.cancelar_venda(db_session, venda.id)
    db_session.refresh(venda)
    db_session.refresh(produto)

    assert venda.status == StatusVenda.CANCELADO
    assert produto.estoque_atual == Decimal("5")


def test_cancelar_venda_orcamento_nao_mexe_no_estoque(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))

    vendas_service.cancelar_venda(db_session, venda.id)
    db_session.refresh(venda)
    db_session.refresh(produto)

    assert venda.status == StatusVenda.CANCELADO
    assert produto.estoque_atual == Decimal("5")


def test_cancelar_venda_ja_cancelada_levanta_erro(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.cancelar_venda(db_session, venda.id)

    with pytest.raises(ValueError):
        vendas_service.cancelar_venda(db_session, venda.id)


def test_cancelar_venda_com_nota_ja_com_chave_de_acesso_e_bloqueado(db_session):
    """Uma vez que a nota tem chave de acesso, ela pode ter sido autorizada
    de verdade na Sefaz -- cancelar a venda por baixo, sem passar pelo
    cancelamento fiscal de verdade, deixaria um documento fiscal órfão."""
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia=f"venda-{venda.id}",
        status=StatusNota.AUTORIZADA, chave_acesso="1" * 44,
    )
    db_session.add(nota)
    db_session.commit()

    with pytest.raises(ValueError, match="cancele a nota fiscal primeiro"):
        vendas_service.cancelar_venda(db_session, venda.id)


def test_listar_orcamentos_inclui_venda_ainda_em_orcamento(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resultado = vendas_service.listar_orcamentos(db_session)

    assert venda.id in [v.id for v in resultado]


def test_listar_orcamentos_inclui_venda_paga_sem_nota_emitida(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    resultado = vendas_service.listar_orcamentos(db_session)

    assert venda.id in [v.id for v in resultado]


def test_listar_orcamentos_inclui_venda_com_nota_rejeitada_sem_chave(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia=f"venda-{venda.id}",
        status=StatusNota.REJEITADA, chave_acesso=None,
    )
    db_session.add(nota)
    db_session.commit()

    resultado = vendas_service.listar_orcamentos(db_session)

    assert venda.id in [v.id for v in resultado]


def test_listar_orcamentos_exclui_venda_com_nota_autorizada(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia=f"venda-{venda.id}",
        status=StatusNota.AUTORIZADA, chave_acesso="1" * 44,
    )
    db_session.add(nota)
    db_session.commit()

    resultado = vendas_service.listar_orcamentos(db_session)

    assert venda.id not in [v.id for v in resultado]


def test_listar_orcamentos_exclui_venda_cancelada(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.cancelar_venda(db_session, venda.id)

    resultado = vendas_service.listar_orcamentos(db_session)

    assert venda.id not in [v.id for v in resultado]

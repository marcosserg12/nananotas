from decimal import Decimal

from app.models.venda import StatusVenda
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


def _venda_com_item(db_session, preco="10.00", quantidade="3", estoque="10"):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco), estoque_atual=Decimal(estoque),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal(quantidade))
    return venda, produto


def test_gerar_parcelas_divide_valor_e_ajusta_arredondamento(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1")  # total = 10.00

    parcelas = parcelas_service.gerar_parcelas(db_session, venda.id, "cartao_credito", 3)

    assert len(parcelas) == 3
    assert sum(p.valor for p in parcelas) == Decimal("10.00")
    assert parcelas[0].numero == 1
    assert parcelas[-1].numero == 3


def test_gerar_parcelas_grava_bandeira_na_venda(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1")

    parcelas_service.gerar_parcelas(db_session, venda.id, "cartao_credito", 1, bandeira="06")
    db_session.refresh(venda)

    assert venda.bandeira == "06"


def test_gerar_parcelas_sem_bandeira_grava_none(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1")

    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    db_session.refresh(venda)

    assert venda.bandeira is None


def test_confirmar_venda_baixa_estoque_e_marca_como_paga(db_session):
    venda, produto = _venda_com_item(db_session, preco="10.00", quantidade="2", estoque="10")

    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("20.00"))
    db_session.refresh(venda)
    db_session.refresh(produto)

    assert venda.status == StatusVenda.PAGO
    assert produto.estoque_atual == Decimal("8")
    assert venda.troco == Decimal("0")


def test_confirmar_venda_calcula_troco(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1", estoque="10")

    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("15.00"))
    db_session.refresh(venda)

    assert venda.troco == Decimal("5.00")


def test_confirmar_venda_ja_paga_levanta_erro(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1", estoque="10")
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    try:
        parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass

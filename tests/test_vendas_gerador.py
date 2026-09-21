import random
from decimal import Decimal

import pytest

from app.models.venda import StatusVenda
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


def _criar_produto(db, codigo, nome, *, gerador=True, chance=100, minimo="30.00", maximo="45.00", ativo=True):
    produto = produtos_service.criar_produto(
        db, codigo_interno=codigo, nome=nome, categoria_nome="Diversos", ncm="21069090", unidade="UN",
        preco_venda=Decimal("0.01"),
        gerador_ativo=gerador, gerador_chance=chance,
        gerador_preco_min=Decimal(minimo) if gerador else None,
        gerador_preco_max=Decimal(maximo) if gerador else None,
    )
    if not ativo:
        produtos_service.alternar_ativo(db, produto.id)
    return produto


@pytest.fixture()
def cardapio(db_session):
    return {
        "refeicao": _criar_produto(db_session, "1", "Refeições diversas", chance=100, minimo="30.00", maximo="45.00"),
        "bebida": _criar_produto(db_session, "2", "Bebida", chance=60, minimo="6.00", maximo="10.00"),
        "sobremesa": _criar_produto(db_session, "3", "Sobremesa", chance=30, minimo="8.00", maximo="14.00"),
    }


@pytest.fixture()
def venda(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    return vendas_service.criar_venda(db_session, cliente.id)


# ---------------- serviço ----------------

def test_gerar_itens_fecha_o_valor_exato_e_respeita_as_faixas(db_session, venda, cardapio):
    resultado = vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("140.00"), random.Random(3))

    assert resultado.valor_total == Decimal("140.00")
    assert resultado.itens
    faixas = {p.id: (p.gerador_preco_min, p.gerador_preco_max) for p in cardapio.values()}
    for item in resultado.itens:
        minimo, maximo = faixas[item.produto_id]
        assert minimo <= item.preco_unitario <= maximo
        assert item.quantidade >= 1


def test_gerar_itens_com_centavos_fecha_exato(db_session, venda, cardapio):
    resultado = vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("137.83"), random.Random(5))

    assert resultado.valor_total == Decimal("137.83")


def test_gerar_itens_substitui_os_itens_que_ja_existiam(db_session, venda, cardapio):
    vendas_service.adicionar_item(db_session, venda.id, cardapio["bebida"].id, Decimal("1"), Decimal("7.00"))

    vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("100.00"), random.Random(1))

    db_session.refresh(venda)
    assert venda.valor_total == Decimal("100.00")
    assert sum(item.quantidade * item.preco_unitario for item in venda.itens) == Decimal("100.00")


def test_gerar_de_novo_com_semente_diferente_troca_a_combinacao(db_session, venda, cardapio):
    combinacoes = set()
    for semente in range(15):
        resultado = vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("140.00"), random.Random(semente))
        combinacoes.add(tuple(sorted((i.produto_id, i.quantidade, i.preco_unitario) for i in resultado.itens)))

    assert len(combinacoes) > 3


def test_gerar_itens_so_usa_produtos_ativos_e_liberados_no_gerador(db_session, venda):
    liberado = _criar_produto(db_session, "1", "Liberado", minimo="20.00", maximo="30.00")
    _criar_produto(db_session, "2", "Nao liberado", gerador=False)
    _criar_produto(db_session, "3", "Inativo", ativo=False, minimo="5.00", maximo="8.00")

    for semente in range(20):
        resultado = vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("85.00"), random.Random(semente))

        assert {i.produto_id for i in resultado.itens} == {liberado.id}


def test_gerar_itens_sem_produtos_liberados_da_erro_e_nao_mexe_nos_itens(db_session, venda):
    produto = _criar_produto(db_session, "1", "Comum", gerador=False)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"), Decimal("10.00"))

    with pytest.raises(ValueError, match="Nenhum produto"):
        vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("50.00"))

    db_session.refresh(venda)
    assert venda.valor_total == Decimal("20.00")
    assert len(venda.itens) == 1


def test_gerar_itens_que_nao_fecha_nao_apaga_os_itens_atuais(db_session, venda):
    fixo = _criar_produto(db_session, "1", "Preco fixo", minimo="6.00", maximo="6.00")
    vendas_service.adicionar_item(db_session, venda.id, fixo.id, Decimal("1"), Decimal("6.00"))

    with pytest.raises(ValueError, match="Não consegui fechar"):
        vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("10.00"))

    db_session.refresh(venda)
    assert len(venda.itens) == 1


def test_gerar_itens_recusa_venda_que_nao_esta_em_orcamento(db_session, venda, cardapio):
    vendas_service.adicionar_item(db_session, venda.id, cardapio["bebida"].id, Decimal("1"), Decimal("7.00"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("7.00"))
    db_session.refresh(venda)
    assert venda.status == StatusVenda.PAGO

    with pytest.raises(ValueError, match="em edição"):
        vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("50.00"))


def test_gerar_itens_recusa_valor_zero(db_session, venda, cardapio):
    with pytest.raises(ValueError, match="maior que zero"):
        vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("0"))


# ---------------- rota ----------------

def test_gerar_itens_sem_login_redireciona(client, venda):
    response = client.post(f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "100"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_rota_gera_itens_aceitando_virgula_e_mostra_na_tela(authed_client, db_session, venda, cardapio):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "140,50"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/vendas/{venda.id}"
    db_session.refresh(venda)
    assert venda.valor_total == Decimal("140.50")
    pagina = authed_client.get(f"/vendas/{venda.id}")
    assert "Refeições diversas" in pagina.text
    assert "140.50" in pagina.text


def test_rota_com_valor_invalido_volta_com_mensagem_de_erro(authed_client, venda, cardapio):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "abc"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/vendas/{venda.id}?erro=")
    pagina = authed_client.get(response.headers["location"])
    assert "Valor inválido" in pagina.text


def test_rota_sem_produtos_liberados_mostra_o_motivo_na_tela(authed_client, venda):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "100"}, follow_redirects=False
    )

    pagina = authed_client.get(response.headers["location"])
    assert "Nenhum produto" in pagina.text


def test_rota_com_venda_inexistente_retorna_404(authed_client):
    response = authed_client.post("/vendas/999999/gerar-itens", data={"valor_total": "100"}, follow_redirects=False)

    assert response.status_code == 404


def test_tela_do_orcamento_mostra_o_cartao_montar_pelo_valor(authed_client, venda, cardapio):
    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "Montar pelo valor" in pagina.text
    assert f'action="/vendas/{venda.id}/gerar-itens"' in pagina.text
    assert "Nenhum produto está liberado" not in pagina.text


def test_tela_avisa_quando_nenhum_produto_esta_liberado_no_gerador(authed_client, venda):
    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "Nenhum produto está liberado" in pagina.text

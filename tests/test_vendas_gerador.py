import random
from decimal import Decimal

import pytest

from app.models.venda import StatusVenda
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


def _criar_produto(db, codigo, nome, *, faixa=True, chance=100, minimo="30.00", maximo="45.00", ativo=True):
    produto = produtos_service.criar_produto(
        db, codigo_interno=codigo, nome=nome, categoria_nome="Diversos", ncm="21069090", unidade="UN",
        preco_venda=Decimal("0.01"),
        gerador_chance=chance,
        gerador_preco_min=Decimal(minimo) if faixa else None,
        gerador_preco_max=Decimal(maximo) if faixa else None,
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


def test_gerar_itens_so_usa_produtos_ativos_e_com_faixa_de_preco(db_session, venda):
    liberado = _criar_produto(db_session, "1", "Liberado", minimo="20.00", maximo="30.00")
    _criar_produto(db_session, "2", "Sem faixa", faixa=False)
    _criar_produto(db_session, "3", "Inativo", ativo=False, minimo="5.00", maximo="8.00")

    for semente in range(20):
        resultado = vendas_service.gerar_itens_por_valor(db_session, venda.id, Decimal("85.00"), random.Random(semente))

        assert {i.produto_id for i in resultado.itens} == {liberado.id}


def test_gerar_itens_sem_nenhuma_faixa_de_preco_da_erro_e_nao_mexe_nos_itens(db_session, venda):
    produto = _criar_produto(db_session, "1", "Comum", faixa=False)
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


def test_rota_com_valor_invalido_mostra_o_erro_e_mantem_o_que_foi_digitado(authed_client, venda, cardapio):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "abc"}, follow_redirects=False
    )

    assert response.status_code == 400
    assert "Valor inválido" in response.text
    assert 'value="abc"' in response.text


def test_rota_sem_nenhuma_faixa_de_preco_mostra_o_motivo_na_tela(authed_client, venda):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "100"}, follow_redirects=False
    )

    assert response.status_code == 400
    assert "Nenhum produto" in response.text


def test_rota_com_venda_inexistente_retorna_404(authed_client):
    response = authed_client.post("/vendas/999999/gerar-itens", data={"valor_total": "100"}, follow_redirects=False)

    assert response.status_code == 404


def test_tela_do_orcamento_mostra_o_cartao_montar_pelo_valor(authed_client, venda, cardapio):
    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "Montar pelo valor" in pagina.text
    assert f'action="/vendas/{venda.id}/gerar-itens"' in pagina.text
    assert "Nenhum produto tem preço mínimo" not in pagina.text
    assert "sem faixa de preço" not in pagina.text


def test_tela_avisa_quando_nenhum_produto_tem_faixa_de_preco(authed_client, venda, db_session):
    _criar_produto(db_session, "1", "Sem faixa", faixa=False)

    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "Nenhum produto tem preço mínimo" in pagina.text
    assert 'href="/produtos/gerador"' in pagina.text


def test_tela_avisa_quantos_produtos_ficaram_de_fora_do_gerador(authed_client, venda, cardapio, db_session):
    _criar_produto(db_session, "9", "Sem faixa", faixa=False)

    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "1 produto sem faixa de preço não entra no gerador" in pagina.text


# ---------------- ajuste só desta nota ----------------

def _campos(produto, chance="100", minimo="", maximo=""):
    return {f"chance_{produto.id}": chance, f"min_{produto.id}": minimo, f"max_{produto.id}": maximo}


def _todos_os_campos(cardapio, **por_produto):
    """Simula o formulário do orçamento: um trio de campos por produto. O que não
    for informado repete o padrão salvo (como a tela já vem preenchida)."""
    campos = {}
    for chave, produto in cardapio.items():
        padrao = {
            "chance": str(produto.gerador_chance),
            "minimo": f"{produto.gerador_preco_min:.2f}",
            "maximo": f"{produto.gerador_preco_max:.2f}",
        }
        campos.update(_campos(produto, **{**padrao, **por_produto.get(chave, {})}))
    return campos


def test_tela_traz_a_tabela_de_ajuste_ja_preenchida_com_o_padrao(authed_client, venda, cardapio):
    pagina = authed_client.get(f"/vendas/{venda.id}")

    assert "Ajustar produtos e preços só desta nota" in pagina.text
    refeicao = cardapio["refeicao"]
    assert f'name="chance_{refeicao.id}" value="100"' in pagina.text
    assert f'name="min_{refeicao.id}" value="30.00"' in pagina.text
    assert f'name="max_{refeicao.id}" value="45.00"' in pagina.text
    assert 'name="salvar_padrao"' in pagina.text


def test_faixas_ajustadas_na_hora_valem_so_para_esta_nota(authed_client, db_session, venda, cardapio):
    campos = _todos_os_campos(cardapio, refeicao={"minimo": "20", "maximo": "25"})
    for outro in ("bebida", "sobremesa"):
        campos.update(_campos(cardapio[outro], "100", "", ""))  # fora desta nota

    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "100", **campos}, follow_redirects=False
    )

    assert response.status_code == 303
    db_session.refresh(venda)
    assert venda.valor_total == Decimal("100.00")
    assert {i.produto_id for i in venda.itens} == {cardapio["refeicao"].id}
    assert all(Decimal("20") <= i.preco_unitario <= Decimal("25") for i in venda.itens)
    db_session.refresh(cardapio["refeicao"])
    assert cardapio["refeicao"].gerador_preco_min == Decimal("30.00")  # padrão intacto


def test_marcar_guardar_como_padrao_atualiza_o_padrao_dos_produtos(authed_client, db_session, venda, cardapio):
    campos = _todos_os_campos(cardapio, refeicao={"chance": "90", "minimo": "20", "maximo": "45"})

    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens",
        data={"valor_total": "140", "salvar_padrao": "on", **campos},
        follow_redirects=False,
    )

    assert response.status_code == 303
    refeicao = cardapio["refeicao"]
    db_session.refresh(refeicao)
    assert (refeicao.gerador_chance, refeicao.gerador_preco_min, refeicao.gerador_preco_max) == (
        90, Decimal("20.00"), Decimal("45.00"),
    )


def test_sem_marcar_guardar_como_padrao_nada_muda_no_cadastro(authed_client, db_session, venda, cardapio):
    campos = _todos_os_campos(cardapio, refeicao={"chance": "90", "minimo": "20", "maximo": "45"})

    authed_client.post(f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "140", **campos})

    refeicao = cardapio["refeicao"]
    db_session.refresh(refeicao)
    assert (refeicao.gerador_chance, refeicao.gerador_preco_min) == (100, Decimal("30.00"))


def test_faixa_invertida_na_nota_mostra_erro_com_o_produto_e_preserva_a_digitacao(
    authed_client, db_session, venda, cardapio
):
    vendas_service.adicionar_item(db_session, venda.id, cardapio["bebida"].id, Decimal("1"), Decimal("7.00"))
    campos = _todos_os_campos(cardapio, bebida={"minimo": "12", "maximo": "8"})

    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens",
        data={"valor_total": "140", "salvar_padrao": "on", **campos},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Bebida: O preço máximo não pode ser menor" in response.text
    assert f'name="min_{cardapio["bebida"].id}" value="12"' in response.text
    assert f'name="max_{cardapio["bebida"].id}" value="8"' in response.text
    assert "<details" in response.text and "open" in response.text.split("<details", 1)[1].split(">", 1)[0]
    db_session.refresh(venda)
    assert len(venda.itens) == 1  # nada foi apagado
    db_session.refresh(cardapio["bebida"])
    assert cardapio["bebida"].gerador_preco_min == Decimal("6.00")  # nem o padrão mudou


def test_chance_invalida_na_nota_mostra_erro(authed_client, venda, cardapio):
    campos = _todos_os_campos(cardapio, refeicao={"chance": "muita"})

    response = authed_client.post(f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "140", **campos})

    assert response.status_code == 400
    assert "chance inválida" in response.text


def test_geracao_que_falha_nao_guarda_o_padrao_mesmo_marcado(authed_client, db_session, venda, cardapio):
    campos = _todos_os_campos(
        cardapio,
        refeicao={"chance": "50", "minimo": "500", "maximo": "600"},
        bebida={"minimo": "", "maximo": ""},
        sobremesa={"minimo": "", "maximo": ""},
    )

    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "10", "salvar_padrao": "on", **campos}
    )

    assert response.status_code == 400
    refeicao = cardapio["refeicao"]
    db_session.refresh(refeicao)
    assert (refeicao.gerador_chance, refeicao.gerador_preco_min) == (100, Decimal("30.00"))


def test_sem_os_campos_da_tabela_usa_o_padrao_salvo(authed_client, db_session, venda, cardapio):
    response = authed_client.post(
        f"/vendas/{venda.id}/gerar-itens", data={"valor_total": "140"}, follow_redirects=False
    )

    assert response.status_code == 303
    db_session.refresh(venda)
    assert venda.valor_total == Decimal("140.00")


def test_servico_com_configs_usa_as_faixas_recebidas_e_ignora_produto_inativo(db_session, venda, cardapio):
    produtos_service.alternar_ativo(db_session, cardapio["bebida"].id)
    configs = [
        {"produto_id": cardapio["refeicao"].id, "chance": 100, "preco_min": Decimal("20"), "preco_max": Decimal("25")},
        {"produto_id": cardapio["bebida"].id, "chance": 100, "preco_min": Decimal("5"), "preco_max": Decimal("6")},
    ]

    for semente in range(15):
        resultado = vendas_service.gerar_itens_por_valor(
            db_session, venda.id, Decimal("92.30"), random.Random(semente), configs=configs
        )

        assert resultado.valor_total == Decimal("92.30")
        assert {i.produto_id for i in resultado.itens} == {cardapio["refeicao"].id}

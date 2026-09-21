from decimal import Decimal

import pytest

from app.models.produto import Produto
from app.services import produtos_service


def _criar(db, codigo="1", nome="Refeições diversas", **extras):
    return produtos_service.criar_produto(
        db, codigo_interno=codigo, nome=nome, categoria_nome="Diversos", ncm="21069090",
        unidade="UN", preco_venda=Decimal("0.01"), **extras,
    )


def _post_campos(produto, chance="100", minimo="", maximo=""):
    return {f"chance_{produto.id}": chance, f"min_{produto.id}": minimo, f"max_{produto.id}": maximo}


# ---------------- serviço ----------------

def test_produto_novo_nasce_com_chance_100_e_sem_faixa_de_preco(db_session):
    produto = _criar(db_session)

    assert produto.gerador_chance == 100
    assert produto.gerador_preco_min is None and produto.gerador_preco_max is None


def test_criar_produto_com_faixa_guarda_a_configuracao(db_session):
    produto = _criar(
        db_session, gerador_chance=70, gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00")
    )

    assert produto.gerador_chance == 70
    assert produto.gerador_preco_min == Decimal("30.00")
    assert produto.gerador_preco_max == Decimal("45.00")


@pytest.mark.parametrize(
    "extras, mensagem",
    [
        ({"gerador_chance": 0}, "entre 1 e 100"),
        ({"gerador_chance": 101}, "entre 1 e 100"),
        ({"gerador_preco_min": Decimal("1")}, "ou deixe os dois em branco"),
        ({"gerador_preco_max": Decimal("2")}, "ou deixe os dois em branco"),
        ({"gerador_preco_min": Decimal("0"), "gerador_preco_max": Decimal("2")}, "maior que zero"),
        ({"gerador_preco_min": Decimal("9"), "gerador_preco_max": Decimal("2")}, "não pode ser menor"),
    ],
)
def test_configuracao_incompleta_ou_incoerente_e_recusada(db_session, extras, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        _criar(db_session, **extras)

    assert db_session.query(Produto).count() == 0


def test_atualizar_com_configuracao_invalida_recusa_e_desfaz(db_session):
    produto = _criar(db_session, gerador_preco_min=Decimal("30"), gerador_preco_max=Decimal("45"))

    with pytest.raises(ValueError, match="não pode ser menor"):
        produtos_service.atualizar_produto(
            db_session, produto.id, gerador_preco_min=Decimal("50"), gerador_preco_max=Decimal("40")
        )

    db_session.refresh(produto)
    assert produto.gerador_preco_min == Decimal("30.00")
    assert produto.gerador_preco_max == Decimal("45.00")


def test_candidatos_do_gerador_sao_os_produtos_ativos_com_faixa(db_session):
    com_faixa = _criar(db_session, "1", "Com faixa", gerador_preco_min=Decimal("1"), gerador_preco_max=Decimal("2"))
    _criar(db_session, "2", "Sem faixa")
    inativo = _criar(db_session, "3", "Inativo", gerador_preco_min=Decimal("1"), gerador_preco_max=Decimal("2"))
    produtos_service.alternar_ativo(db_session, inativo.id)

    assert [p.id for p in produtos_service.listar_candidatos_gerador(db_session)] == [com_faixa.id]


def test_contar_produtos_ativos_sem_faixa(db_session):
    _criar(db_session, "1", "Com faixa", gerador_preco_min=Decimal("1"), gerador_preco_max=Decimal("2"))
    _criar(db_session, "2", "Sem faixa A")
    _criar(db_session, "3", "Sem faixa B")
    inativo = _criar(db_session, "4", "Inativo sem faixa")
    produtos_service.alternar_ativo(db_session, inativo.id)

    assert produtos_service.contar_produtos_sem_faixa_do_gerador(db_session) == 2


def test_salvar_config_gerador_grava_varios_produtos_de_uma_vez(db_session):
    a = _criar(db_session, "1", "A")
    b = _criar(db_session, "2", "B")

    produtos_service.salvar_config_gerador(
        db_session,
        [
            {"produto_id": a.id, "chance": 80, "preco_min": Decimal("30"), "preco_max": Decimal("45")},
            {"produto_id": b.id, "chance": 20, "preco_min": None, "preco_max": None},
        ],
    )

    db_session.refresh(a)
    db_session.refresh(b)
    assert (a.gerador_chance, a.gerador_preco_min, a.gerador_preco_max) == (80, Decimal("30.00"), Decimal("45.00"))
    assert (b.gerador_chance, b.gerador_preco_min, b.gerador_preco_max) == (20, None, None)


def test_salvar_config_gerador_e_tudo_ou_nada_e_cita_o_produto_com_erro(db_session):
    a = _criar(db_session, "1", "Produto A")
    b = _criar(db_session, "2", "Produto B")

    with pytest.raises(ValueError, match="Produto B: O preço máximo não pode ser menor"):
        produtos_service.salvar_config_gerador(
            db_session,
            [
                {"produto_id": a.id, "chance": 50, "preco_min": Decimal("5"), "preco_max": Decimal("8")},
                {"produto_id": b.id, "chance": 50, "preco_min": Decimal("9"), "preco_max": Decimal("3")},
            ],
        )

    db_session.refresh(a)
    assert a.gerador_chance == 100 and a.gerador_preco_min is None


# ---------------- tela do gerador ----------------

def test_tela_do_gerador_sem_login_redireciona(client):
    response = client.get("/produtos/gerador", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tela_lista_os_produtos_ativos_com_os_valores_salvos(authed_client, db_session):
    a = _criar(db_session, "1", "Refeições diversas", gerador_chance=65,
               gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00"))
    inativo = _criar(db_session, "2", "Produto desligado")
    produtos_service.alternar_ativo(db_session, inativo.id)

    pagina = authed_client.get("/produtos/gerador")

    assert pagina.status_code == 200
    assert "Refeições diversas" in pagina.text
    assert "Produto desligado" not in pagina.text
    assert f'name="chance_{a.id}" value="65"' in pagina.text
    assert f'name="min_{a.id}" value="30.00"' in pagina.text
    assert f'name="max_{a.id}" value="45.00"' in pagina.text


def test_salvar_pela_tela_aceita_virgula_e_em_branco(authed_client, db_session):
    a = _criar(db_session, "1", "A")
    b = _criar(db_session, "2", "B")

    response = authed_client.post(
        "/produtos/gerador",
        data={**_post_campos(a, "70", "30,00", "45,50"), **_post_campos(b, "", "", "")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/produtos/gerador?salvo=1"
    db_session.refresh(a)
    db_session.refresh(b)
    assert (a.gerador_chance, a.gerador_preco_min, a.gerador_preco_max) == (70, Decimal("30.00"), Decimal("45.50"))
    assert (b.gerador_chance, b.gerador_preco_min, b.gerador_preco_max) == (100, None, None)
    assert "Configuração salva" in authed_client.get("/produtos/gerador?salvo=1").text


def test_salvar_com_faixa_invertida_volta_com_erro_e_mantem_o_que_foi_digitado(authed_client, db_session):
    a = _criar(db_session, "1", "Refeições diversas")
    b = _criar(db_session, "2", "Bebida")

    response = authed_client.post(
        "/produtos/gerador",
        data={**_post_campos(a, "100", "30", "45"), **_post_campos(b, "60", "10", "6")},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Bebida: O preço máximo não pode ser menor" in response.text
    assert f'name="min_{b.id}" value="10"' in response.text
    assert f'name="max_{b.id}" value="6"' in response.text
    db_session.refresh(a)
    assert a.gerador_preco_min is None  # nada foi salvo


@pytest.mark.parametrize(
    "campos, trecho",
    [
        ({"chance": "muita", "minimo": "1", "maximo": "2"}, "chance inválida"),
        ({"chance": "0", "minimo": "1", "maximo": "2"}, "entre 1 e 100"),
        ({"chance": "100", "minimo": "abc", "maximo": "2"}, "Valor inválido"),
        ({"chance": "100", "minimo": "5", "maximo": ""}, "ou deixe os dois em branco"),
    ],
)
def test_salvar_com_valores_invalidos_retorna_400(authed_client, db_session, campos, trecho):
    a = _criar(db_session, "1", "Refeições diversas")

    response = authed_client.post("/produtos/gerador", data=_post_campos(a, **campos), follow_redirects=False)

    assert response.status_code == 400
    assert trecho in response.text
    assert "Refeições diversas" in response.text


# ---------------- outras telas de produto ----------------

def test_formulario_de_produto_nao_tem_mais_campos_do_gerador(authed_client):
    pagina = authed_client.get("/produtos/novo")

    assert "gerador" not in pagina.text.lower()


def test_lista_de_produtos_tem_link_pro_gerador_e_mostra_a_faixa_de_cada_um(authed_client, db_session):
    _criar(db_session, "1", "Com faixa", gerador_chance=65,
           gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00"))
    _criar(db_session, "2", "Sem faixa")

    pagina = authed_client.get("/produtos")

    assert 'href="/produtos/gerador"' in pagina.text
    assert 'data-label="Gerador"' in pagina.text
    assert "65%" in pagina.text and "30.00 a 45.00" in pagina.text
    assert "sem faixa de preço" in pagina.text

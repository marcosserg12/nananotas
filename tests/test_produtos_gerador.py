from decimal import Decimal

import pytest

from app.models.produto import Produto
from app.services import produtos_service


def _dados_produto(**extras):
    dados = {
        "codigo_interno": "1",
        "nome": "Refeições diversas",
        "categoria_nome": "Diversos",
        "ncm": "21069090",
        "unidade": "UN",
        "preco_venda": "0.01",
    }
    dados.update(extras)
    return dados


def _criar(db, **extras):
    return produtos_service.criar_produto(
        db, codigo_interno="1", nome="Refeições diversas", categoria_nome="Diversos", ncm="21069090",
        unidade="UN", preco_venda=Decimal("0.01"), **extras,
    )


# ---------------- serviço ----------------

def test_produto_novo_nasce_fora_do_gerador_com_chance_100(db_session):
    produto = _criar(db_session)

    assert produto.gerador_ativo is False
    assert produto.gerador_chance == 100
    assert produto.gerador_preco_min is None and produto.gerador_preco_max is None


def test_criar_produto_no_gerador_guarda_a_configuracao(db_session):
    produto = _criar(
        db_session, gerador_ativo=True, gerador_chance=70,
        gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00"),
    )

    assert produto.gerador_ativo is True
    assert produto.gerador_chance == 70
    assert produto.gerador_preco_min == Decimal("30.00")
    assert produto.gerador_preco_max == Decimal("45.00")


@pytest.mark.parametrize(
    "extras, mensagem",
    [
        ({"gerador_chance": 0, "gerador_preco_min": Decimal("1"), "gerador_preco_max": Decimal("2")}, "entre 1 e 100"),
        ({"gerador_chance": 101, "gerador_preco_min": Decimal("1"), "gerador_preco_max": Decimal("2")}, "entre 1 e 100"),
        ({"gerador_preco_min": None, "gerador_preco_max": Decimal("2")}, "preço mínimo e o preço máximo"),
        ({"gerador_preco_min": Decimal("1"), "gerador_preco_max": None}, "preço mínimo e o preço máximo"),
        ({"gerador_preco_min": Decimal("0"), "gerador_preco_max": Decimal("2")}, "maior que zero"),
        ({"gerador_preco_min": Decimal("9"), "gerador_preco_max": Decimal("2")}, "não pode ser menor"),
    ],
)
def test_configuracao_incompleta_ou_incoerente_do_gerador_e_recusada(db_session, extras, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        _criar(db_session, gerador_ativo=True, **extras)

    assert db_session.query(Produto).count() == 0


def test_produto_fora_do_gerador_nao_valida_faixa_de_preco(db_session):
    produto = _criar(db_session, gerador_ativo=False, gerador_preco_min=Decimal("9"), gerador_preco_max=Decimal("2"))

    assert produto.id is not None


def test_atualizar_com_configuracao_invalida_recusa_e_desfaz(db_session):
    produto = _criar(
        db_session, gerador_ativo=True, gerador_preco_min=Decimal("30"), gerador_preco_max=Decimal("45")
    )

    with pytest.raises(ValueError, match="não pode ser menor"):
        produtos_service.atualizar_produto(
            db_session, produto.id, gerador_preco_min=Decimal("50"), gerador_preco_max=Decimal("40")
        )

    db_session.refresh(produto)
    assert produto.gerador_preco_min == Decimal("30.00")
    assert produto.gerador_preco_max == Decimal("45.00")


def test_listar_candidatos_so_traz_produtos_ativos_e_liberados(db_session):
    liberado = _criar(db_session, gerador_ativo=True, gerador_preco_min=Decimal("1"), gerador_preco_max=Decimal("2"))
    produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Comum", categoria_nome="Diversos", ncm="21069090",
        unidade="UN", preco_venda=Decimal("1"),
    )
    inativo = produtos_service.criar_produto(
        db_session, codigo_interno="3", nome="Inativo", categoria_nome="Diversos", ncm="21069090",
        unidade="UN", preco_venda=Decimal("1"), gerador_ativo=True,
        gerador_preco_min=Decimal("1"), gerador_preco_max=Decimal("2"),
    )
    produtos_service.alternar_ativo(db_session, inativo.id)

    assert [p.id for p in produtos_service.listar_candidatos_gerador(db_session)] == [liberado.id]


# ---------------- rotas ----------------

def test_criar_produto_pelo_formulario_com_gerador_aceita_virgula(authed_client, db_session):
    response = authed_client.post(
        "/produtos/novo",
        data=_dados_produto(
            gerador_ativo="on", gerador_chance="70", gerador_preco_min="30,00", gerador_preco_max="45,50"
        ),
        follow_redirects=False,
    )

    assert response.status_code == 303
    produto = db_session.query(Produto).one()
    assert produto.gerador_ativo is True
    assert produto.gerador_chance == 70
    assert produto.gerador_preco_min == Decimal("30.00")
    assert produto.gerador_preco_max == Decimal("45.50")


def test_criar_produto_sem_marcar_o_gerador_continua_funcionando(authed_client, db_session):
    response = authed_client.post("/produtos/novo", data=_dados_produto(), follow_redirects=False)

    assert response.status_code == 303
    assert db_session.query(Produto).one().gerador_ativo is False


def test_criar_produto_com_faixa_invertida_retorna_400_e_nao_cria(authed_client, db_session):
    response = authed_client.post(
        "/produtos/novo",
        data=_dados_produto(gerador_ativo="on", gerador_preco_min="50", gerador_preco_max="40"),
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "não pode ser menor" in response.text
    assert db_session.query(Produto).count() == 0


def test_criar_produto_com_gerador_sem_precos_retorna_400(authed_client):
    response = authed_client.post(
        "/produtos/novo", data=_dados_produto(gerador_ativo="on"), follow_redirects=False
    )

    assert response.status_code == 400


def test_criar_produto_com_chance_invalida_retorna_400(authed_client):
    response = authed_client.post(
        "/produtos/novo",
        data=_dados_produto(gerador_ativo="on", gerador_chance="muita", gerador_preco_min="1", gerador_preco_max="2"),
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "Chance" in response.text


def test_criar_produto_com_preco_do_gerador_invalido_retorna_400(authed_client):
    response = authed_client.post(
        "/produtos/novo",
        data=_dados_produto(gerador_ativo="on", gerador_preco_min="abc", gerador_preco_max="2"),
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_editar_produto_liga_e_desliga_o_gerador(authed_client, db_session):
    produto = _criar(db_session)
    base = _dados_produto()

    ligar = authed_client.post(
        f"/produtos/{produto.id}/editar",
        data={**base, "gerador_ativo": "on", "gerador_chance": "40", "gerador_preco_min": "8", "gerador_preco_max": "12"},
        follow_redirects=False,
    )
    assert ligar.status_code == 303
    db_session.refresh(produto)
    assert produto.gerador_ativo is True and produto.gerador_chance == 40

    desligar = authed_client.post(f"/produtos/{produto.id}/editar", data=base, follow_redirects=False)
    assert desligar.status_code == 303
    db_session.refresh(produto)
    assert produto.gerador_ativo is False


def test_editar_produto_com_faixa_invertida_retorna_400(authed_client, db_session):
    produto = _criar(db_session)

    response = authed_client.post(
        f"/produtos/{produto.id}/editar",
        data=_dados_produto(gerador_ativo="on", gerador_preco_min="50", gerador_preco_max="40"),
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_editar_produto_inexistente_continua_retornando_404(authed_client):
    response = authed_client.post("/produtos/999999/editar", data=_dados_produto(), follow_redirects=False)

    assert response.status_code == 404


def test_formulario_mostra_os_campos_do_gerador(authed_client):
    pagina = authed_client.get("/produtos/novo")

    assert 'name="gerador_ativo"' in pagina.text
    assert 'name="gerador_chance"' in pagina.text
    assert 'name="gerador_preco_min"' in pagina.text
    assert 'name="gerador_preco_max"' in pagina.text


def test_formulario_de_edicao_traz_a_configuracao_ja_salva(authed_client, db_session):
    produto = _criar(
        db_session, gerador_ativo=True, gerador_chance=65,
        gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00"),
    )

    pagina = authed_client.get(f"/produtos/{produto.id}/editar")

    assert 'value="65"' in pagina.text
    assert 'value="30.00"' in pagina.text
    assert 'value="45.00"' in pagina.text
    assert "checked" in pagina.text


def test_lista_mostra_a_configuracao_do_gerador_de_cada_produto(authed_client, db_session):
    _criar(
        db_session, gerador_ativo=True, gerador_chance=65,
        gerador_preco_min=Decimal("30.00"), gerador_preco_max=Decimal("45.00"),
    )

    pagina = authed_client.get("/produtos")

    assert 'data-label="Gerador"' in pagina.text
    assert "65%" in pagina.text
    assert "30.00 a 45.00" in pagina.text

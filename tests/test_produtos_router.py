from decimal import Decimal

from app.services import produtos_service


def test_listar_produtos_agrupados_por_categoria(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"),
    )

    response = authed_client.get("/produtos")

    assert response.status_code == 200
    assert "Diversos" in response.text
    assert "Refrigerante" in response.text


def test_criar_produto_via_formulario(authed_client):
    response = authed_client.post(
        "/produtos/novo",
        data={
            "codigo_interno": "10",
            "nome": "Suco de Laranja",
            "categoria_nome": "Sucos",
            "ncm": "20091900",
            "unidade": "UN",
            "preco_custo": "2.00",
            "preco_venda": "7.00",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/produtos")
    assert "Suco de Laranja" in listagem.text


def test_buscar_produtos_retorna_html_parcial(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )

    response = authed_client.get("/produtos/buscar", params={"termo": "Água"})

    assert response.status_code == 200
    assert "Água Mineral" in response.text

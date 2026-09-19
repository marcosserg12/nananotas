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


def test_listar_produtos_nao_mostra_mais_coluna_de_estoque(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"), estoque_atual=Decimal("10"),
    )

    response = authed_client.get("/produtos")

    assert response.status_code == 200
    assert "Estoque" not in response.text


def test_formulario_de_produto_nao_pede_mais_estoque(authed_client):
    response = authed_client.get("/produtos/novo")

    assert response.status_code == 200
    assert "estoque" not in response.text.lower()


def test_listar_produtos_tem_data_label_pra_tabela_responsiva_no_celular(authed_client, db_session):
    """Sem os `data-label`, a tabela vira uma lista de valores sem indicar
    qual coluna é qual quando o CSS a transforma em cartões empilhados no
    celular (ver `.tabela-scroll` em base.html)."""
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"),
    )

    response = authed_client.get("/produtos")

    assert response.status_code == 200
    assert 'data-label="Código"' in response.text
    assert 'data-label="Nome"' in response.text
    assert 'data-label="Preço venda"' in response.text


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


def test_criar_produto_via_formulario_com_estoque_inicial(authed_client, db_session):
    response = authed_client.post(
        "/produtos/novo",
        data={
            "codigo_interno": "11",
            "nome": "Caixa de Bombom",
            "categoria_nome": "Doces",
            "ncm": "18063200",
            "unidade": "UN",
            "preco_custo": "5.00",
            "preco_venda": "12.00",
            "estoque_atual": "50",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303

    produto = produtos_service.buscar_produtos(db_session, "Caixa de Bombom")[0]
    assert produto.estoque_atual == Decimal("50")


def test_editar_form_mostra_dados_atuais(authed_client, db_session):
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="20", nome="Pastel de Carne", categoria_nome="Salgados",
        ncm="19022000", unidade="UN", preco_venda=Decimal("6.00"),
    )

    response = authed_client.get(f"/produtos/{produto.id}/editar")

    assert response.status_code == 200
    assert "Pastel de Carne" in response.text
    assert "Salgados" in response.text


def test_editar_produto_via_formulario_atualiza_dados(authed_client, db_session):
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="21", nome="Pastel de Queijo", categoria_nome="Salgados",
        ncm="19022000", unidade="UN", preco_venda=Decimal("6.00"),
    )

    response = authed_client.post(
        f"/produtos/{produto.id}/editar",
        data={
            "codigo_interno": "21",
            "nome": "Pastel de Queijo Grande",
            "categoria_nome": "Salgados",
            "ncm": "19022000",
            "unidade": "UN",
            "preco_custo": "3.00",
            "preco_venda": "8.00",
            "estoque_atual": "15",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/produtos")
    assert "Pastel de Queijo Grande" in listagem.text
    assert "Pastel de Queijo</td>" not in listagem.text


def test_editar_produto_inexistente_retorna_404(authed_client):
    response = authed_client.get("/produtos/9999/editar")

    assert response.status_code == 404


def test_buscar_produtos_retorna_html_parcial(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )

    response = authed_client.get("/produtos/buscar", params={"termo": "Água"})

    assert response.status_code == 200
    assert "Água Mineral" in response.text


def test_buscar_produtos_com_termo_vazio_nao_lista_todos(authed_client, db_session):
    """Regressão de um bug real visto pela tela: limpar o campo de busca (ou
    nunca ter digitado nada) não pode fazer o dropdown mostrar todos os
    produtos cadastrados -- só deve reagir a uma busca de verdade."""
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )

    response = authed_client.get("/produtos/buscar", params={"termo": ""})

    assert response.status_code == 200
    assert "Água Mineral" not in response.text
    assert "<ul" not in response.text


def test_buscar_produtos_sem_resultado_mostra_mensagem(authed_client, db_session):
    response = authed_client.get("/produtos/buscar", params={"termo": "xyz-nao-existe"})

    assert response.status_code == 200
    assert "Nenhum produto encontrado" in response.text

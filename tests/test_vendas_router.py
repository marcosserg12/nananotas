from decimal import Decimal

from app.services import produtos_service


def test_criar_venda_via_formulario_redireciona_para_detalhe(authed_client, db_session):
    response = authed_client.get("/vendas/nova")
    assert response.status_code == 200

    consumidor = authed_client.get("/vendas/nova")
    assert "cliente_id" in consumidor.text

    from app.services import clientes_service

    cliente = clientes_service.garantir_consumidor_final(db_session)

    criar = authed_client.post("/vendas/nova", data={"cliente_id": cliente.id}, follow_redirects=False)
    assert criar.status_code == 303
    assert criar.headers["location"].startswith("/vendas/")


def test_adicionar_e_remover_item_na_venda(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta_add = authed_client.post(
        f"/vendas/{venda.id}/itens", data={"produto_id": produto.id, "quantidade": "2"}
    )
    assert resposta_add.status_code == 200
    assert "Lanche" in resposta_add.text
    assert "20.00" in resposta_add.text

    detalhe = authed_client.get(f"/vendas/{venda.id}")
    assert detalhe.status_code == 200
    assert "Lanche" in detalhe.text


def test_adicionar_item_com_preco_informado_sobrescreve_preco_de_cadastro(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = authed_client.post(
        f"/vendas/{venda.id}/itens",
        data={"produto_id": produto.id, "quantidade": "2", "preco_unitario": "8.00"},
    )

    assert resposta.status_code == 200
    assert "16.00" in resposta.text
    assert "20.00" not in resposta.text


def test_adicionar_item_com_preco_invalido_nao_quebra(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = authed_client.post(
        f"/vendas/{venda.id}/itens",
        data={"produto_id": produto.id, "quantidade": "1", "preco_unitario": "abc"},
    )

    assert resposta.status_code == 400
    assert "Preço" in resposta.text


def test_adicionar_item_com_quantidade_invalida_nao_quebra(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = authed_client.post(
        f"/vendas/{venda.id}/itens", data={"produto_id": produto.id, "quantidade": "abc"}
    )

    assert resposta.status_code == 400
    assert "Quantidade" in resposta.text


def test_remover_item_inexistente_nao_quebra(authed_client, db_session):
    resposta = authed_client.post("/vendas/itens/99999/remover")

    assert resposta.status_code == 404

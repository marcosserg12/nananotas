from decimal import Decimal

from app.models.parcela import Parcela
from app.models.venda import StatusVenda
from app.services import clientes_service, produtos_service, vendas_service


def test_confirmar_pagamento_marca_venda_como_paga_e_redireciona_para_nota(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/vendas/{venda.id}/nota"

    db_session.refresh(venda)
    assert venda.status == StatusVenda.PAGO


def test_confirmar_pagamento_no_cartao_grava_bandeira(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "cartao_credito", "numero_parcelas": "1", "valor_pago": "10.00", "bandeira": "06"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(venda)
    assert venda.bandeira == "06"


def test_confirmar_pagamento_no_cartao_sem_bandeira_retorna_400(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "cartao_debito", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "bandeira" in response.text.lower()


def test_confirmar_pagamento_em_dinheiro_nao_exige_bandeira(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_confirmar_pagamento_com_valor_pago_invalido_retorna_400(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "abc"},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_confirmar_pagamento_de_venda_ja_paga_retorna_400(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_reenvio_do_pagamento_em_venda_ja_paga_nao_altera_as_parcelas(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    primeira = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "2", "valor_pago": "10.00"},
        follow_redirects=False,
    )
    assert primeira.status_code == 303

    parcelas_antes = [
        (parcela.numero, str(parcela.valor))
        for parcela in db_session.query(Parcela)
        .filter(Parcela.venda_id == venda.id)
        .order_by(Parcela.numero)
        .all()
    ]
    assert len(parcelas_antes) == 2

    segunda = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "cartao_credito", "numero_parcelas": "3", "valor_pago": "10.00"},
        follow_redirects=False,
    )
    assert segunda.status_code == 400

    parcelas_depois = [
        (parcela.numero, str(parcela.valor))
        for parcela in db_session.query(Parcela)
        .filter(Parcela.venda_id == venda.id)
        .order_by(Parcela.numero)
        .all()
    ]
    assert parcelas_depois == parcelas_antes

    db_session.refresh(venda)
    assert venda.forma_pagamento == "dinheiro"

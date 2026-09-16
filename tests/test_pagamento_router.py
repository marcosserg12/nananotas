from decimal import Decimal

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

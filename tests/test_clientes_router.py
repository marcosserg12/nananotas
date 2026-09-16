def test_listar_clientes(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Maria Souza")

    response = authed_client.get("/clientes")

    assert response.status_code == 200
    assert "Maria Souza" in response.text


def test_criar_cliente_via_formulario(authed_client):
    response = authed_client.post(
        "/clientes/novo",
        data={"tipo_pessoa": "PJ", "nome": "Empresa ABC", "cpf_cnpj": "11222333000181"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/clientes")
    assert "Empresa ABC" in listagem.text


def test_buscar_clientes_retorna_html_parcial(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")

    response = authed_client.get("/clientes/buscar", params={"termo": "Carlos"})

    assert response.status_code == 200
    assert "Carlos Pereira" in response.text

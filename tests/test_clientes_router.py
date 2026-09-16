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


def test_editar_form_mostra_dados_atuais(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Joana Lima")

    response = authed_client.get(f"/clientes/{cliente.id}/editar")

    assert response.status_code == 200
    assert "Joana Lima" in response.text


def test_editar_cliente_via_formulario_atualiza_dados(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Joana Lima")

    response = authed_client.post(
        f"/clientes/{cliente.id}/editar",
        data={"tipo_pessoa": "PF", "nome": "Joana Lima Santos", "telefone": "61999998888"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/clientes")
    assert "Joana Lima Santos" in listagem.text


def test_editar_cliente_inexistente_retorna_404(authed_client):
    response = authed_client.get("/clientes/9999/editar")

    assert response.status_code == 404


def test_editar_consumidor_final_e_bloqueado(authed_client, db_session):
    from app.services import clientes_service

    consumidor = clientes_service.garantir_consumidor_final(db_session)

    resposta_form = authed_client.get(f"/clientes/{consumidor.id}/editar")
    resposta_post = authed_client.post(
        f"/clientes/{consumidor.id}/editar",
        data={"tipo_pessoa": "PF", "nome": "Outro nome"},
    )

    assert resposta_form.status_code == 400
    assert resposta_post.status_code == 400


def test_lista_de_clientes_nao_mostra_editar_para_consumidor_final(authed_client, db_session):
    from app.services import clientes_service

    clientes_service.garantir_consumidor_final(db_session)

    response = authed_client.get("/clientes")

    assert "AO CONSUMIDOR" in response.text

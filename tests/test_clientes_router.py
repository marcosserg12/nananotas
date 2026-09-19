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


def test_criar_cliente_via_formulario_com_endereco_estruturado(authed_client, db_session):
    response = authed_client.post(
        "/clientes/novo",
        data={
            "tipo_pessoa": "PJ",
            "nome": "Empresa ABC",
            "cpf_cnpj": "11222333000181",
            "tipo_inscricao_estadual": "normal",
            "endereco_cep": "70000000",
            "endereco_logradouro": "Rua das Flores",
            "endereco_numero": "123",
            "endereco_bairro": "Asa Sul",
            "endereco_cidade": "Brasília",
            "endereco_uf": "DF",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    from app.models.cliente import Cliente

    cliente = db_session.query(Cliente).filter(Cliente.nome == "Empresa ABC").one()
    assert cliente.endereco_logradouro == "Rua das Flores"
    assert cliente.endereco_uf == "DF"
    assert cliente.tipo_inscricao_estadual == "normal"


def test_buscar_clientes_retorna_html_parcial(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")

    response = authed_client.get("/clientes/buscar", params={"termo": "Carlos"})

    assert response.status_code == 200
    assert "Carlos Pereira" in response.text


def test_buscar_cnpj_retorna_dados_encontrados(authed_client, monkeypatch):
    from app.services import cnpj_lookup_service

    monkeypatch.setattr(
        cnpj_lookup_service,
        "buscar_dados_cnpj",
        lambda cnpj: {
            "razao_social": "Empresa ABC",
            "nome_fantasia": "",
            "logradouro": "Rua X",
            "numero": "10",
            "complemento": "",
            "bairro": "Centro",
            "cidade": "Brasília",
            "uf": "DF",
            "cep": "70000000",
        },
    )

    response = authed_client.get("/clientes/buscar-cnpj", params={"cnpj": "11222333000181"})

    assert response.status_code == 200
    assert response.json()["razao_social"] == "Empresa ABC"


def test_buscar_cnpj_nao_encontrado_retorna_400(authed_client, monkeypatch):
    from app.services import cnpj_lookup_service

    def levantar(cnpj):
        raise ValueError("CNPJ não encontrado")

    monkeypatch.setattr(cnpj_lookup_service, "buscar_dados_cnpj", levantar)

    response = authed_client.get("/clientes/buscar-cnpj", params={"cnpj": "00000000000000"})

    assert response.status_code == 400


def test_buscar_clientes_sem_resultado_oferece_cadastro_com_o_nome_buscado(authed_client, db_session):
    response = authed_client.get("/clientes/buscar", params={"termo": "Ninguem Com Esse Nome"})

    assert response.status_code == 200
    assert "Cadastrar" in response.text
    assert "/clientes/novo?nome=Ninguem" in response.text
    assert "voltar=/vendas/nova" in response.text


def test_novo_form_pre_preenche_nome_e_guarda_voltar(authed_client):
    response = authed_client.get("/clientes/novo", params={"nome": "Fulano Novo", "voltar": "/vendas/nova"})

    assert response.status_code == 200
    assert 'value="Fulano Novo"' in response.text
    assert 'name="voltar" value="/vendas/nova"' in response.text


def test_criar_cliente_com_voltar_redireciona_de_volta_com_cliente_selecionado(authed_client, db_session):
    response = authed_client.post(
        "/clientes/novo",
        data={"tipo_pessoa": "PF", "nome": "Fulano Novo", "voltar": "/vendas/nova"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    from app.models.cliente import Cliente

    cliente = db_session.query(Cliente).filter(Cliente.nome == "Fulano Novo").one()
    assert response.headers["location"] == f"/vendas/nova?cliente_id={cliente.id}"


def test_criar_cliente_com_voltar_para_url_externa_e_ignorado(authed_client):
    """`voltar` vem de um parâmetro de query controlado pelo navegador --
    não pode virar um redirecionamento aberto para fora do sistema."""
    response = authed_client.post(
        "/clientes/novo",
        data={"tipo_pessoa": "PF", "nome": "Fulano Malicioso", "voltar": "https://evil.example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/clientes"


def test_buscar_clientes_com_termo_vazio_nao_lista_todos(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")

    response = authed_client.get("/clientes/buscar", params={"termo": ""})

    assert response.status_code == 200
    assert "Carlos Pereira" not in response.text
    assert "<ul" not in response.text


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

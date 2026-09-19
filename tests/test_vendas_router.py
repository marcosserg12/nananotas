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


def test_nova_venda_com_cliente_id_pre_seleciona_esse_cliente(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Cliente Especifico")

    response = authed_client.get("/vendas/nova", params={"cliente_id": cliente.id})

    assert response.status_code == 200
    assert "Cliente Especifico" in response.text
    assert f'value="{cliente.id}"' in response.text


def test_nova_venda_com_cliente_id_inexistente_cai_para_consumidor_final(authed_client, db_session):
    response = authed_client.get("/vendas/nova", params={"cliente_id": 999999})

    assert response.status_code == 200
    assert "AO CONSUMIDOR" in response.text


def test_detalhe_da_venda_lista_produtos_ativos_em_datalist_pesquisavel(authed_client, db_session):
    """Regressão de UX: o campo de produto era uma busca com dropdown solto
    (sem largura fixa) que ficava aberto e desalinhado. Virou um campo de
    texto com <datalist> (código - nome), pesquisável nativamente pelo
    navegador, resolvido em JS para o produto_id real via `PRODUTOS`."""
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto_ativo = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    produto_inativo = produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Descontinuado", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("5.00"),
    )
    produtos_service.alternar_ativo(db_session, produto_inativo.id)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    response = authed_client.get(f"/vendas/{venda.id}")

    assert response.status_code == 200
    assert 'list="produtos_datalist"' in response.text
    assert '<option value="1 - Lanche">' in response.text
    assert f'"id": {produto_ativo.id}' in response.text
    assert "Descontinuado" not in response.text


def test_detalhe_da_venda_em_orcamento_oferece_excluir(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    response = authed_client.get(f"/vendas/{venda.id}")

    assert response.status_code == 200
    assert f'action="/vendas/{venda.id}/excluir"' in response.text


def test_detalhe_da_venda_paga_nao_oferece_mais_excluir(authed_client, db_session):
    from app.services import clientes_service, parcelas_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    response = authed_client.get(f"/vendas/{venda.id}")

    assert response.status_code == 200
    assert f'action="/vendas/{venda.id}/excluir"' not in response.text


def test_listar_orcamentos_mostra_venda_ainda_nao_faturada(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")
    venda = vendas_service.criar_venda(db_session, cliente.id)

    response = authed_client.get("/vendas/orcamentos")

    assert response.status_code == 200
    assert "Carlos Pereira" in response.text
    assert str(venda.numero_orcamento) in response.text


def test_listar_orcamentos_nao_e_capturado_pela_rota_de_detalhe_da_venda(authed_client):
    """Regressão do mesmo tipo de bug já visto com /vendas/notas: uma rota
    estática como /vendas/orcamentos precisa ser registrada antes de
    /vendas/{venda_id}, senão "orcamentos" é interpretado como um id de
    venda e o FastAPI recusa com 422 antes mesmo de chegar aqui."""
    response = authed_client.get("/vendas/orcamentos")

    assert response.status_code == 200


def test_excluir_venda_redireciona_para_lista_de_orcamentos(authed_client, db_session):
    from app.services import clientes_service, vendas_service
    from app.models.venda import StatusVenda

    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    response = authed_client.post(f"/vendas/{venda.id}/excluir", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/vendas/orcamentos"
    db_session.refresh(venda)
    assert venda.status == StatusVenda.CANCELADO


def test_excluir_venda_ja_cancelada_retorna_400(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    authed_client.post(f"/vendas/{venda.id}/excluir")

    response = authed_client.post(f"/vendas/{venda.id}/excluir", follow_redirects=False)

    assert response.status_code == 400


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


def test_adicionar_varios_itens_nao_aninha_o_wrapper_da_tabela_a_cada_swap(authed_client, db_session):
    """Regressão: o wrapper `<div id="itens-venda">` (adicionado pra tabela
    poder rolar na horizontal no celular) precisa manter o id no elemento
    de fora -- se o id ficasse na <table> de dentro, cada troca via htmx
    (hx-swap="outerHTML" no mesmo #itens-venda) empilharia um wrapper novo
    por dentro do anterior a cada item adicionado/removido."""
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = None
    for _ in range(3):
        resposta = authed_client.post(
            f"/vendas/{venda.id}/itens", data={"produto_id": produto.id, "quantidade": "1"}
        )
        assert resposta.status_code == 200

    assert resposta.text.count('id="itens-venda"') == 1
    assert resposta.text.count("tabela-scroll") == 1


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


def test_adicionar_item_sem_selecionar_produto_nao_quebra(authed_client, db_session):
    """Regressão de um bug real encontrado testando pela tela: submeter o
    formulário sem clicar num resultado da busca mandava `produto_id` em
    branco, e como o campo era `int` direto no Form, o FastAPI recusava com
    um 422 cru (sem mensagem em português) antes mesmo do código da rota
    rodar."""
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = authed_client.post(f"/vendas/{venda.id}/itens", data={"produto_id": "", "quantidade": "1"})

    assert resposta.status_code == 400
    assert "Selecione um produto" in resposta.text


def test_adicionar_item_com_produto_inexistente_nao_quebra(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta = authed_client.post(f"/vendas/{venda.id}/itens", data={"produto_id": "99999", "quantidade": "1"})

    assert resposta.status_code == 400


def test_remover_item_inexistente_nao_quebra(authed_client, db_session):
    resposta = authed_client.post("/vendas/itens/99999/remover")

    assert resposta.status_code == 404

from decimal import Decimal

from app.services import clientes_service, dashboard_service, parcelas_service, produtos_service, vendas_service


def test_painel_mostra_hora_convertida_para_brasilia_nao_utc_cru(authed_client, db_session):
    """Regressão: a tela mostrava `venda.data_venda` (gravado em UTC) direto
    com `.strftime()`, 3h adiantado em relação à hora real de Brasília."""
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    venda.data_venda = venda.data_venda.replace(hour=14, minute=30)
    db_session.commit()

    response = authed_client.get("/")

    assert response.status_code == 200
    assert "11:30" in response.text
    assert "14:30" not in response.text


def test_painel_mostra_botao_flutuante_de_nova_venda(authed_client):
    """"Nova Venda" é a ação mais usada do sistema -- fica sempre visível,
    como botão flutuante, em qualquer tela autenticada, não só no menu."""
    response = authed_client.get("/")

    assert response.status_code == 200
    assert '<a href="/vendas/nova" class="fab-nova-venda">' in response.text


def test_painel_mostra_botao_de_abrir_o_menu_no_celular(authed_client):
    """No celular, o menu ficava expandido quebrando em várias linhas.
    Agora fica recolhido atrás de um botão de menu (visível só em telas
    pequenas via `sm:hidden`), com os links num painel que abre/fecha."""
    response = authed_client.get("/")

    assert response.status_code == 200
    assert 'id="botao_menu"' in response.text
    assert 'id="menu_nav"' in response.text


def test_menu_do_celular_usa_classe_propria_para_abrir_fechar(authed_client):
    """Regressão: o menu usava a classe `hidden`/`sm:flex` do Tailwind pro
    JS alternar, mas nada garantia que a linha aberta (sem `hidden`) virasse
    coluna empilhada no celular -- sem uma regra de `flex-direction`
    amarrada a um `display:flex` incondicional, os itens só fluíam como
    texto normal e quebravam em várias linhas. Agora o JS alterna uma
    classe própria (`aberto`), sem disputa de especificidade com o
    Tailwind."""
    response = authed_client.get("/")

    assert response.status_code == 200
    assert 'menu.classList.toggle("aberto")' in response.text
    assert 'id="menu_nav">' in response.text  # não deve mais nascer com "hidden" na classe


def test_botao_flutuante_de_nova_venda_nao_aparece_sem_login(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert '<a href="/vendas/nova" class="fab-nova-venda">' not in response.text

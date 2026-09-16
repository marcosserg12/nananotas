from decimal import Decimal

from app.services import produtos_service


def test_criar_produto_cria_categoria_automaticamente(db_session):
    produto = produtos_service.criar_produto(
        db_session,
        codigo_interno="1",
        nome="Refeição Diversas",
        categoria_nome="Diversos",
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("15.00"),
    )

    assert produto.id is not None
    assert produto.categoria.nome == "Diversos"


def test_listar_produtos_por_categoria_agrupa_corretamente(db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )
    produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Suco Natural", categoria_nome="Sucos",
        ncm="20091900", unidade="UN", preco_venda=Decimal("8.00"),
    )

    grupos = produtos_service.listar_produtos_por_categoria(db_session)

    nomes_categorias = [categoria.nome for categoria, _ in grupos]
    assert "Água Mineral" in nomes_categorias
    assert "Sucos" in nomes_categorias


def test_alternar_ativo_inverte_status(db_session):
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Energético", categoria_nome="Diversos",
        ncm="22029900", unidade="UN", preco_venda=Decimal("6.00"),
    )
    assert produto.ativo is True

    produtos_service.alternar_ativo(db_session, produto.id)
    db_session.refresh(produto)

    assert produto.ativo is False


def test_buscar_produtos_por_nome_ou_codigo(db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="7", nome="Refrigerante Lata", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"),
    )

    por_nome = produtos_service.buscar_produtos(db_session, "Refrigerante")
    por_codigo = produtos_service.buscar_produtos(db_session, "7")

    assert len(por_nome) == 1
    assert len(por_codigo) == 1

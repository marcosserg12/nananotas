from app.models.cliente import TipoPessoa
from app.services import clientes_service


def test_garantir_consumidor_final_cria_uma_unica_vez(db_session):
    primeiro = clientes_service.garantir_consumidor_final(db_session)
    segundo = clientes_service.garantir_consumidor_final(db_session)

    assert primeiro.id == segundo.id
    assert primeiro.consumidor_final is True
    assert primeiro.nome == "AO CONSUMIDOR"


def test_criar_cliente_pf(db_session):
    cliente = clientes_service.criar_cliente(
        db_session, tipo_pessoa=TipoPessoa.PF, nome="João da Silva", cpf_cnpj="12345678900"
    )

    assert cliente.id is not None
    assert cliente.consumidor_final is False


def test_buscar_clientes_por_nome_ou_documento(db_session):
    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PJ, nome="Empresa XYZ", cpf_cnpj="11222333000181")

    por_nome = clientes_service.buscar_clientes(db_session, "Empresa")
    por_documento = clientes_service.buscar_clientes(db_session, "11222333")

    assert len(por_nome) == 1
    assert len(por_documento) == 1


def test_atualizar_cliente_padrao_consumidor_final_levanta_erro(db_session):
    consumidor = clientes_service.garantir_consumidor_final(db_session)

    try:
        clientes_service.atualizar_cliente(db_session, consumidor.id, nome="Outro nome")
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass

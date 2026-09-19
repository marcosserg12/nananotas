from datetime import date, datetime
from decimal import Decimal

from app.models.cliente import TipoPessoa
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.services import clientes_service, notas_service, produtos_service, vendas_service


def test_formatar_data_hora_local_converte_utc_para_brasilia():
    assert notas_service.formatar_data_hora_local(datetime(2026, 9, 18, 14, 30)) == "18/09/2026 11:30"


def test_formatar_data_hora_local_com_none_devolve_none():
    assert notas_service.formatar_data_hora_local(None) is None


def test_listar_notas_filtra_por_nome_do_cliente(db_session):
    cliente_a = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")
    cliente_b = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Joana Lima")
    venda_a = vendas_service.criar_venda(db_session, cliente_a.id)
    venda_b = vendas_service.criar_venda(db_session, cliente_b.id)
    nota_a = NotaFiscal(venda_id=venda_a.id, provedor="sefaz_direto", referencia="a", status=StatusNota.AUTORIZADA)
    nota_b = NotaFiscal(venda_id=venda_b.id, provedor="sefaz_direto", referencia="b", status=StatusNota.AUTORIZADA)
    db_session.add_all([nota_a, nota_b])
    db_session.commit()

    resultado = notas_service.listar_notas(db_session, cliente="carlos")

    assert [n.id for n in resultado] == [nota_a.id]


def test_listar_notas_filtra_por_data_de_autorizacao_em_brasilia(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda1 = vendas_service.criar_venda(db_session, cliente.id)
    venda2 = vendas_service.criar_venda(db_session, cliente.id)

    # 18/09 02:00 UTC = 17/09 23:00 em Brasília -- fica no dia 17, não no 18.
    nota1 = NotaFiscal(
        venda_id=venda1.id, provedor="sefaz_direto", referencia="1", status=StatusNota.AUTORIZADA,
        autorizado_em=datetime(2026, 9, 18, 2, 0),
    )
    # 18/09 14:00 UTC = 18/09 11:00 em Brasília -- fica no dia 18.
    nota2 = NotaFiscal(
        venda_id=venda2.id, provedor="sefaz_direto", referencia="2", status=StatusNota.AUTORIZADA,
        autorizado_em=datetime(2026, 9, 18, 14, 0),
    )
    db_session.add_all([nota1, nota2])
    db_session.commit()

    resultado = notas_service.listar_notas(db_session, data=date(2026, 9, 18))

    assert [n.id for n in resultado] == [nota2.id]


def test_listar_notas_com_filtro_de_data_ignora_notas_sem_autorizado_em(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    nota = NotaFiscal(venda_id=venda.id, provedor="sefaz_direto", referencia="p", status=StatusNota.PROCESSANDO)
    db_session.add(nota)
    db_session.commit()

    resultado = notas_service.listar_notas(db_session, data=date(2026, 9, 18))

    assert resultado == []


def test_listar_notas_ordena_das_mais_recentes_para_as_mais_antigas(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda1 = vendas_service.criar_venda(db_session, cliente.id)
    venda2 = vendas_service.criar_venda(db_session, cliente.id)

    nota1 = NotaFiscal(venda_id=venda1.id, provedor="sefaz_direto", referencia="v1", status=StatusNota.AUTORIZADA)
    nota2 = NotaFiscal(venda_id=venda2.id, provedor="sefaz_direto", referencia="v2", status=StatusNota.AUTORIZADA)
    db_session.add_all([nota1, nota2])
    db_session.commit()

    resultado = notas_service.listar_notas(db_session)

    assert [n.id for n in resultado] == [nota2.id, nota1.id]

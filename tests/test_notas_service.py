from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.cliente import TipoPessoa
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.services import clientes_service, email_service, notas_service, produtos_service, vendas_service


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


def test_enviar_email_nota_sem_chave_de_acesso_levanta_erro(db_session):
    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Sem Nota", email="a@b.com")
    venda = vendas_service.criar_venda(db_session, cliente.id)

    with pytest.raises(ValueError, match="ainda não autorizada"):
        notas_service.enviar_email_nota(db_session, venda.id)


def test_enviar_email_nota_com_sucesso_marca_email_enviado_em(db_session, monkeypatch):
    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Com Nota", email="a@b.com")
    venda = vendas_service.criar_venda(db_session, cliente.id)
    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia="v1", status=StatusNota.AUTORIZADA,
        chave_acesso="1" * 44,
    )
    db_session.add(nota)
    db_session.commit()

    chamadas = []
    monkeypatch.setattr(
        email_service, "enviar_nota_por_email", lambda v, n: chamadas.append((v.id, n.id))
    )

    resultado = notas_service.enviar_email_nota(db_session, venda.id)

    assert chamadas == [(venda.id, nota.id)]
    assert resultado.email_enviado_em is not None


def test_enviar_email_nota_propaga_erro_do_servico_de_email(db_session, monkeypatch):
    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Sem Email", email=None)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia="v1", status=StatusNota.AUTORIZADA,
        chave_acesso="2" * 44,
    )
    db_session.add(nota)
    db_session.commit()

    def _levanta_erro(v, n):
        raise ValueError("Este cliente não tem e-mail cadastrado")

    monkeypatch.setattr(email_service, "enviar_nota_por_email", _levanta_erro)

    with pytest.raises(ValueError, match="não tem e-mail cadastrado"):
        notas_service.enviar_email_nota(db_session, venda.id)

    db_session.refresh(nota)
    assert nota.email_enviado_em is None


class _ProviderCancelaOk:
    def cancelar(self, referencia, motivo):
        from app.services.fiscal.base import ResultadoFiscal
        return ResultadoFiscal(referencia=referencia, status="cancelada", protocolo_cancelamento="153260000000099")


class _ProviderCancelaRecusado:
    def cancelar(self, referencia, motivo):
        raise ValueError("A Sefaz não aceitou o cancelamento: prazo excedido. A nota continua válida.")


def _venda_com_nota_autorizada(db_session):
    cliente = clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Cancela", email=None)
    venda = vendas_service.criar_venda(db_session, cliente.id)
    nota = NotaFiscal(
        venda_id=venda.id, provedor="sefaz_direto", referencia="v1", status=StatusNota.AUTORIZADA,
        chave_acesso="3" * 44, protocolo="153260000000015", numero="1", serie="2",
    )
    db_session.add(nota)
    db_session.commit()
    return venda, nota


def test_cancelar_nota_guarda_comprovante_e_mantem_chave_e_protocolo_originais(db_session):
    venda, _ = _venda_com_nota_autorizada(db_session)

    nota = notas_service.cancelar_nota(db_session, venda.id, "Teste cancelado pelo estabelecimento", _ProviderCancelaOk())

    assert nota.status == StatusNota.CANCELADA
    assert nota.protocolo_cancelamento == "153260000000099"
    assert nota.motivo_cancelamento == "Teste cancelado pelo estabelecimento"
    assert nota.cancelada_em is not None
    assert nota.chave_acesso == "3" * 44
    assert nota.protocolo == "153260000000015"


def test_cancelar_nota_recusada_pela_sefaz_deixa_a_nota_autorizada_e_sem_comprovante(db_session):
    venda, _ = _venda_com_nota_autorizada(db_session)

    with pytest.raises(ValueError, match="prazo excedido"):
        notas_service.cancelar_nota(db_session, venda.id, "Teste cancelado pelo estabelecimento", _ProviderCancelaRecusado())

    nota = db_session.query(NotaFiscal).filter_by(venda_id=venda.id).one()
    assert nota.status == StatusNota.AUTORIZADA
    assert nota.protocolo_cancelamento is None
    assert nota.cancelada_em is None

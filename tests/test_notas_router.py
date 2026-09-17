from decimal import Decimal

import pytest

from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.main import app
from app.models.nota_fiscal import NotaFiscal
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


class FiscalProviderFalso(FiscalProvider):
    def __init__(self):
        self.emitidas = []
        self.canceladas = []

    def emitir(self, venda):
        self.emitidas.append(venda.id)
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe="https://exemplo.com/danfe/1",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="autorizada", numero="1")

    def cancelar(self, referencia, motivo):
        self.canceladas.append((referencia, motivo))
        return ResultadoFiscal(referencia=referencia, status="cancelada")


class FiscalProviderFalsoDuasEtapas(FiscalProvider):
    """Fake provider whose first `emitir` call comes back "processando" and whose
    second comes back "autorizada" — used to exercise the create-then-update path
    of `notas_service.emitir_nota` when a note is re-emitted for the same venda."""

    def __init__(self):
        self.chamadas = 0

    def emitir(self, venda):
        self.chamadas += 1
        if self.chamadas == 1:
            return ResultadoFiscal(referencia=f"venda-{venda.id}", status="processando")
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="2",
            serie="1",
            chave_acesso="2" * 44,
            protocolo="def456",
            url_danfe="https://exemplo.com/danfe/2",
        )

    def consultar(self, referencia):
        raise NotImplementedError

    def cancelar(self, referencia, motivo):
        raise NotImplementedError


@pytest.fixture()
def venda_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.gerar_parcelas(db_session, venda.id, "dinheiro", 1)
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
    return venda


@pytest.fixture()
def venda_nao_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    return venda


@pytest.fixture()
def authed_client_com_provider_falso(authed_client, db_session):
    provider_falso = FiscalProviderFalso()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_falso
    yield authed_client, provider_falso
    del app.dependency_overrides[get_fiscal_provider]


def test_emitir_nota_grava_dados_retornados_pelo_provedor(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 303
    assert provider_falso.emitidas == [venda_paga.id]

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text
    assert "https://exemplo.com/danfe/1" in pagina.text


def test_cancelar_nota_chama_provedor_com_motivo(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Erro de digitação"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider_falso.canceladas == [(f"venda-{venda_paga.id}", "Erro de digitação")]


def test_consultar_nota_inexistente_retorna_400(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/consultar", follow_redirects=False)

    assert response.status_code == 400


def test_emitir_nota_com_venda_nao_paga_retorna_400(authed_client_com_provider_falso, venda_nao_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_nao_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 400
    assert provider_falso.emitidas == []


def test_cancelar_nota_ja_cancelada_retorna_400(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")
    client.post(f"/vendas/{venda_paga.id}/nota/cancelar", data={"motivo": "Erro de digitação"})

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Tentativa de cancelamento duplicada"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert provider_falso.canceladas == [(f"venda-{venda_paga.id}", "Erro de digitação")]


def test_pagina_da_nota_mostra_as_parcelas_geradas(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota")

    assert response.status_code == 200
    assert "dinheiro" in response.text
    assert "10.00" in response.text
    assert "Em aberto" in response.text


def test_pagina_da_nota_sem_parcelas_nao_mostra_a_tabela(authed_client_com_provider_falso, venda_nao_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_nao_paga.id}/nota")

    assert response.status_code == 200
    assert "Vencimento" not in response.text


def test_marcar_nota_emitida_manualmente_com_chave_de_acesso(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/marcar-manual",
        data={"chave_acesso": "1" * 44},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider_falso.emitidas == []

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text
    assert "1" * 44 in pagina.text
    assert "manualmente" in pagina.text


def test_marcar_nota_emitida_manualmente_sem_chave_tambem_funciona(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/marcar-manual", follow_redirects=False)

    assert response.status_code == 303

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text


def test_marcar_nota_emitida_manualmente_em_venda_nao_paga_retorna_400(authed_client_com_provider_falso, venda_nao_paga):
    client, _ = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_nao_paga.id}/nota/marcar-manual", follow_redirects=False)

    assert response.status_code == 400


def test_ver_danfe_com_nota_autorizada_mostra_qrcode(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 200
    assert "data:image/png;base64," in response.text


def test_ver_danfe_sem_nota_autorizada_retorna_404(authed_client_com_provider_falso, venda_paga):
    client, _ = authed_client_com_provider_falso

    response = client.get(f"/vendas/{venda_paga.id}/nota/danfe")

    assert response.status_code == 404


def test_emitir_nota_duas_vezes_atualiza_registro_existente_em_vez_de_duplicar(
    authed_client_com_provider_falso, venda_paga, db_session
):
    client, _ = authed_client_com_provider_falso
    provider_duas_etapas = FiscalProviderFalsoDuasEtapas()
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_duas_etapas

    primeira = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)
    segunda = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert primeira.status_code == 303
    assert segunda.status_code == 303
    assert provider_duas_etapas.chamadas == 2

    notas = db_session.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_paga.id).all()
    assert len(notas) == 1
    assert notas[0].status.value == "autorizada"
    assert notas[0].numero == "2"

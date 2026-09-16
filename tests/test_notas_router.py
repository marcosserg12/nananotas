from decimal import Decimal

import pytest

from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.main import app
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services import clientes_service, produtos_service, vendas_service


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


@pytest.fixture()
def venda_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
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

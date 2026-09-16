from decimal import Decimal

import httpx
import pytest
import respx

from app.models.cliente import Cliente, TipoPessoa
from app.models.categoria import Categoria
from app.models.produto import Produto
from app.services.vendas_service import adicionar_item, criar_venda
from app.services.fiscal.focus_nfe import FocusNFeProvider


@pytest.fixture()
def venda_com_item(db_session):
    categoria = Categoria(nome="Lanches")
    db_session.add(categoria)
    db_session.commit()
    produto = Produto(
        codigo_interno="1",
        nome="LANCHES DIVERSAS",
        categoria_id=categoria.id,
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("15.00"),
        estoque_atual=Decimal("10"),
    )
    cliente = Cliente(tipo_pessoa=TipoPessoa.PF, nome="AO CONSUMIDOR", consumidor_final=True)
    db_session.add_all([produto, cliente])
    db_session.commit()
    venda = criar_venda(db_session, cliente.id)
    adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    db_session.refresh(venda)
    return venda


@pytest.fixture()
def provider():
    client = httpx.Client(base_url="https://homologacao.focusnfe.com.br", auth=("test-token", ""))
    return FocusNFeProvider(token="test-token", ambiente="homologacao", client=client)


@respx.mock
def test_emitir_retorna_processando(provider, venda_com_item):
    respx.post("https://homologacao.focusnfe.com.br/v2/nfce").mock(
        return_value=httpx.Response(202, json={"status": "processando_autorizacao"})
    )

    resultado = provider.emitir(venda_com_item)

    assert resultado.status == "processando"
    assert resultado.referencia == f"venda-{venda_com_item.id}"


@respx.mock
def test_consultar_retorna_autorizada_com_dados(provider):
    respx.get("https://homologacao.focusnfe.com.br/v2/nfce/venda-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "autorizado",
                "numero": "123",
                "serie": "1",
                "chave_nfe": "1" * 44,
                "protocolo_autorizacao": "abc123",
                "caminho_danfe": "https://homologacao.focusnfe.com.br/danfe/venda-1",
            },
        )
    )

    resultado = provider.consultar("venda-1")

    assert resultado.status == "autorizada"
    assert resultado.chave_acesso == "1" * 44
    assert resultado.url_danfe == "https://homologacao.focusnfe.com.br/danfe/venda-1"


@respx.mock
def test_cancelar_retorna_cancelada(provider):
    respx.delete("https://homologacao.focusnfe.com.br/v2/nfce/venda-1").mock(
        return_value=httpx.Response(200, json={"status": "cancelado"})
    )

    resultado = provider.cancelar("venda-1", "Erro de digitação")

    assert resultado.status == "cancelada"


@respx.mock
def test_emitir_com_erro_retorna_rejeitada_e_mensagem(provider, venda_com_item):
    respx.post("https://homologacao.focusnfe.com.br/v2/nfce").mock(
        return_value=httpx.Response(
            422, json={"status": "erro_autorizacao", "mensagem_sefaz": "CFOP inválido"}
        )
    )

    resultado = provider.emitir(venda_com_item)

    assert resultado.status == "rejeitada"
    assert resultado.mensagem_erro == "CFOP inválido"

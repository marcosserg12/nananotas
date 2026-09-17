from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.services import clientes_service, produtos_service, vendas_service
from app.services.fiscal.sefaz_direto.provider import SefazDiretoProvider


@pytest.fixture(autouse=True)
def emitente_configurado(monkeypatch):
    """Dados de emitente válidos (estruturalmente) para os testes -- sem
    isso, `xml_builder.montar_nfce_xml` (chamada de verdade em `emitir`,
    não mockada aqui) falha rápido por emitente incompleto antes mesmo de
    chegar na assinatura/webservice mockados. Mesmos valores usados em
    `tests/test_sefaz_xml_builder.py`."""
    monkeypatch.setattr(settings, "emitente_cnpj", "26.423.780/0001-76")
    monkeypatch.setattr(settings, "emitente_razao_social", "NANA LANCHES COMERCIO DE ALIMENTOS LTDA")
    monkeypatch.setattr(settings, "emitente_nome_fantasia", "Nana Lanches")
    monkeypatch.setattr(settings, "emitente_ie", "0000000000")
    monkeypatch.setattr(settings, "emitente_endereco_logradouro", "SRTVN Lote P Loja 145 - TERREO")
    monkeypatch.setattr(settings, "emitente_endereco_numero", "SN")
    monkeypatch.setattr(settings, "emitente_endereco_bairro", "Asa Norte")
    monkeypatch.setattr(settings, "emitente_endereco_municipio", "Brasília")
    monkeypatch.setattr(settings, "emitente_endereco_uf", "DF")
    monkeypatch.setattr(settings, "emitente_endereco_cep", "70719040")
    monkeypatch.setattr(settings, "sefaz_ambiente", "homologacao")
    return settings


@pytest.fixture(autouse=True)
def sessao_do_provider_aponta_para_o_db_de_teste(db_session):
    """`SefazDiretoProvider` abre sua própria `Session` (via `SessionLocal`)
    para operações que hoje não recebem uma `Session` de fora -- reservar
    numeração em `emitir`, buscar o `NotaFiscal` em `consultar`/`cancelar` --
    porque `FiscalProvider.emitir/consultar/cancelar` não recebem uma
    `Session` como parâmetro (mesmo padrão já usado pelo numeracao.py e
    replicado aqui). Em produção isso abre uma conexão real via
    `app.database.SessionLocal` (MySQL, configurado por `.env`); neste
    ambiente de teste não há um `.env`/MySQL configurado, então apontamos
    `SessionLocal` para uma *nova* `Session` presa ao mesmo engine sqlite em
    memória do fixture `db_session` (o engine usa `StaticPool`, então essa
    nova `Session` enxerga os mesmos dados via a mesma conexão física),
    em vez de deixar o provider tentar (e falhar) uma conexão de rede real
    toda vez que testamos `emitir`/`consultar`.

    Importante: não reaproveitamos `db_session` diretamente aqui -- o
    provider fecha a sessão que ele mesmo abre (`db.close()`, correto em
    produção, onde é uma sessão só sua, separada da sessão do chamador que
    carregou a `Venda`). Se apontássemos para o objeto `db_session` em si,
    esse `close()` expiraria/desvincularia as entidades que os testes
    criaram com `db_session` (ex.: `venda.itens`, acessado depois via lazy
    load dentro de `xml_builder`), quebrando os testes por um artefato só
    deste setup -- não um bug do provider."""
    fabrica = sessionmaker(bind=db_session.get_bind())
    with patch("app.services.fiscal.sefaz_direto.provider.SessionLocal", side_effect=fabrica):
        yield


def _venda_com_item(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("15.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    return venda


def test_emitir_com_autorizacao_retorna_resultado_autorizado(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {
            "status": "autorizado",
            "protocolo": "153260000000015",
            "chave_acesso": "5" * 44,
            "mensagem": "Autorizado o uso da NF-e",
        }
        resultado = provider.emitir(venda)

    assert resultado.status == "autorizada"
    assert resultado.chave_acesso == "5" * 44
    assert resultado.protocolo == "153260000000015"


def test_emitir_com_rejeicao_retorna_resultado_rejeitado_nunca_processando(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {"status": "rejeitado", "mensagem": "Rejeicao: Falha no Schema XML"}
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert "Falha no Schema" in resultado.mensagem_erro


def test_emitir_com_erro_de_assinatura_retorna_rejeitada_em_vez_de_lancar(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-errada-de-proposito")

    with patch(
        "app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml",
        side_effect=Exception("senha do certificado inválida"),
    ):
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert "senha" in resultado.mensagem_erro.lower() or "certificado" in resultado.mensagem_erro.lower()


def test_emitir_com_erro_de_rede_retorna_rejeitada_em_vez_de_lancar(db_session):
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch("app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar") as autorizar_mock:
        autorizar_mock.return_value = {"status": "erro", "mensagem": "Falha de conexão com a Sefaz: timeout"}
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert "conexão" in resultado.mensagem_erro.lower() or "conex" in resultado.mensagem_erro.lower()


def test_emitir_com_ambiente_invalido_levantando_keyerror_no_webservice_retorna_rejeitada(db_session):
    """`webservice_client.autorizar` faz `ENDPOINTS[ambiente][...]` sem
    validar `ambiente` -- um `SEFAZ_AMBIENTE` mal configurado (typo, valor
    fora de {"homologacao", "producao"}) faz isso levantar `KeyError`. Antes
    da correção deste teste, essa chamada ficava FORA do try/except de
    `emitir`, então o `KeyError` vazava cru para fora do provider,
    quebrando o contrato "nunca lança, sempre devolve ResultadoFiscal
    rejeitada"."""
    venda = _venda_com_item(db_session)
    provider = SefazDiretoProvider(certificado_path="tests/fixtures/certificado_teste.pfx", certificado_senha="senha-teste")

    with patch("app.services.fiscal.sefaz_direto.provider.assinatura.assinar_xml", return_value="<xml-assinado/>"), \
         patch(
             "app.services.fiscal.sefaz_direto.provider.webservice_client.autorizar",
             side_effect=KeyError("ambiente-invalido"),
         ):
        resultado = provider.emitir(venda)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert resultado.mensagem_erro


def _nota_autorizada(db_session, venda, chave_acesso="5" * 44, protocolo="153260000000015"):
    nota = NotaFiscal(
        venda_id=venda.id,
        provedor="sefaz_direto",
        referencia=f"nfce-venda-{venda.id}",
        status=StatusNota.AUTORIZADA,
        numero="1",
        serie="1",
        chave_acesso=chave_acesso,
        protocolo=protocolo,
    )
    db_session.add(nota)
    db_session.commit()
    return nota


def test_consultar_com_nota_autorizada_na_sefaz_retorna_autorizada(db_session):
    venda = _venda_com_item(db_session)
    nota = _nota_autorizada(db_session, venda)
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    with patch("app.services.fiscal.sefaz_direto.provider.webservice_client.consultar_protocolo") as consulta_mock:
        consulta_mock.return_value = {
            "status": "autorizado",
            "protocolo": nota.protocolo,
            "chave_acesso": nota.chave_acesso,
            "mensagem": "Autorizado o uso da NF-e",
        }
        resultado = provider.consultar(nota.referencia)

    consulta_mock.assert_called_once_with(nota.chave_acesso, ambiente=provider.ambiente)
    assert resultado.status == "autorizada"
    assert resultado.chave_acesso == nota.chave_acesso
    assert resultado.protocolo == nota.protocolo


def test_consultar_com_nota_cancelada_na_sefaz_retorna_cancelada(db_session):
    venda = _venda_com_item(db_session)
    nota = _nota_autorizada(db_session, venda)
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    with patch("app.services.fiscal.sefaz_direto.provider.webservice_client.consultar_protocolo") as consulta_mock:
        consulta_mock.return_value = {
            "status": "cancelado",
            "protocolo": "999",
            "chave_acesso": nota.chave_acesso,
            "mensagem": "Cancelamento homologado",
        }
        resultado = provider.consultar(nota.referencia)

    assert resultado.status == "cancelada"


def test_consultar_com_erro_ou_nao_encontrado_retorna_rejeitada_nunca_processando(db_session):
    venda = _venda_com_item(db_session)
    nota = _nota_autorizada(db_session, venda)
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    with patch("app.services.fiscal.sefaz_direto.provider.webservice_client.consultar_protocolo") as consulta_mock:
        consulta_mock.return_value = {
            "status": "nao_encontrado",
            "protocolo": None,
            "chave_acesso": None,
            "mensagem": "Consulta com dois digitos -- NF-e não consta na base de dados da SEFAZ",
        }
        resultado = provider.consultar(nota.referencia)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert resultado.mensagem_erro


def test_consultar_com_ambiente_invalido_levantando_keyerror_no_webservice_retorna_rejeitada(db_session):
    """Mesmo caso do `emitir` acima, para `consultar`: `webservice_client.
    consultar_protocolo` também faz `ENDPOINTS[ambiente][...]` sem validar
    `ambiente`, e antes da correção esse `KeyError` vazava cru para fora de
    `consultar` em vez de virar um `ResultadoFiscal` rejeitada."""
    venda = _venda_com_item(db_session)
    nota = _nota_autorizada(db_session, venda)
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    with patch(
        "app.services.fiscal.sefaz_direto.provider.webservice_client.consultar_protocolo",
        side_effect=KeyError("ambiente-invalido"),
    ):
        resultado = provider.consultar(nota.referencia)

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert resultado.mensagem_erro


def test_consultar_referencia_sem_nota_persistida_retorna_rejeitada_em_vez_de_lancar(db_session):
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    resultado = provider.consultar("nfce-venda-99999")

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert resultado.mensagem_erro


def test_consultar_referencia_em_formato_inesperado_retorna_rejeitada_em_vez_de_lancar(db_session):
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    resultado = provider.consultar("focus-nfe-referencia-de-outro-provedor")

    assert resultado.status == "rejeitada"
    assert resultado.status != "processando"
    assert resultado.mensagem_erro


def test_cancelar_nao_implementado_documenta_bloqueio_em_vez_de_falhar_silenciosamente(db_session):
    """`cancelar` ainda não está implementado (ver docstring do método em
    provider.py) -- falta um construtor de XML para o evento de
    cancelamento (que não existe em xml_builder.py) e `assinatura.assinar_xml`
    hoje só sabe assinar `infNFe`, não `infEvento`. Este teste documenta o
    comportamento atual: uma exceção clara e explícita (NotImplementedError
    com mensagem descrevendo o bloqueio), nunca um `ResultadoFiscal` com
    status "processando" nem um cancelamento fingido como bem-sucedido."""
    venda = _venda_com_item(db_session)
    nota = _nota_autorizada(db_session, venda)
    provider = SefazDiretoProvider(certificado_path="x", certificado_senha="y")

    with pytest.raises(NotImplementedError):
        provider.cancelar(nota.referencia, motivo="Erro de digitação no item")

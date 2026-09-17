import httpx
import respx

from app.services.fiscal.sefaz_direto import webservice_client

RESPOSTA_AUTORIZADA = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <retEnviNFe>
        <protNFe>
          <infProt>
            <cStat>100</cStat>
            <xMotivo>Autorizado o uso da NF-e</xMotivo>
            <chNFe>53260900000000000000650010000000011000000015</chNFe>
            <nProt>153260000000015</nProt>
          </infProt>
        </protNFe>
      </retEnviNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_REJEITADA = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4">
      <retEnviNFe>
        <protNFe>
          <infProt>
            <cStat>225</cStat>
            <xMotivo>Rejeicao: Falha no Schema XML</xMotivo>
          </infProt>
        </protNFe>
      </retEnviNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_CONSULTA_AUTORIZADA = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4">
      <retConsSitNFe>
        <protNFe>
          <infProt>
            <cStat>100</cStat>
            <xMotivo>Autorizado o uso da NF-e</xMotivo>
            <chNFe>53260900000000000000650010000000011000000015</chNFe>
            <nProt>153260000000015</nProt>
          </infProt>
        </protNFe>
      </retConsSitNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_CONSULTA_INEXISTENTE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4">
      <retConsSitNFe>
        <cStat>217</cStat>
        <xMotivo>NF-e não consta na base de dados da SEFAZ</xMotivo>
      </retConsSitNFe>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_CANCELAMENTO_HOMOLOGADO = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
      <retEnvEvento>
        <retEvento>
          <infEvento>
            <cStat>135</cStat>
            <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
            <chNFe>53260900000000000000650010000000011000000015</chNFe>
            <nProt>153260000000099</nProt>
          </infEvento>
        </retEvento>
      </retEnvEvento>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""

RESPOSTA_CANCELAMENTO_REJEITADO = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <nfeResultMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">
      <retEnvEvento>
        <retEvento>
          <infEvento>
            <cStat>573</cStat>
            <xMotivo>Rejeicao: Protocolo de autorizacao invalido</xMotivo>
          </infEvento>
        </retEvento>
      </retEnvEvento>
    </nfeResultMsg>
  </soap:Body>
</soap:Envelope>"""


@respx.mock
def test_autorizar_com_sucesso_retorna_status_autorizado():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_AUTORIZADA)
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "autorizado"
    assert resultado["protocolo"] == "153260000000015"
    assert resultado["chave_acesso"] == "53260900000000000000650010000000011000000015"


@respx.mock
def test_autorizar_com_rejeicao_retorna_status_rejeitado_com_motivo():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_REJEITADA)
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "rejeitado"
    assert "Falha no Schema" in resultado["mensagem"]


@respx.mock
def test_autorizar_com_erro_de_rede_retorna_status_erro_em_vez_de_lancar_excecao():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        side_effect=httpx.ConnectError("conexão recusada")
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="homologacao")

    assert resultado["status"] == "erro"
    assert resultado["mensagem"]


@respx.mock
def test_autorizar_envia_soapaction_e_envelope_com_xml_assinado():
    rota = respx.post(webservice_client.ENDPOINTS["homologacao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_AUTORIZADA)
    )

    webservice_client.autorizar("<infNFe-assinado-xyz/>", ambiente="homologacao")

    assert rota.called
    requisicao = rota.calls.last.request
    assert "infNFe-assinado-xyz" in requisicao.content.decode("utf-8")
    assert "nfeDadosMsg" in requisicao.content.decode("utf-8")
    content_type = requisicao.headers.get("content-type", "")
    soapaction = requisicao.headers.get("soapaction", "")
    assert "nfeAutorizacaoLote" in content_type or "nfeAutorizacaoLote" in soapaction


@respx.mock
def test_autorizar_usa_endpoint_de_producao_quando_ambiente_producao():
    rota = respx.post(webservice_client.ENDPOINTS["producao"]["autorizacao"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_AUTORIZADA)
    )

    resultado = webservice_client.autorizar("<xml-assinado-fake/>", ambiente="producao")

    assert rota.called
    assert resultado["status"] == "autorizado"


@respx.mock
def test_consultar_protocolo_autorizado_retorna_status_autorizado():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["consulta_protocolo"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_CONSULTA_AUTORIZADA)
    )

    resultado = webservice_client.consultar_protocolo(
        "53260900000000000000650010000000011000000015", ambiente="homologacao"
    )

    assert resultado["status"] == "autorizado"
    assert resultado["protocolo"] == "153260000000015"
    assert resultado["chave_acesso"] == "53260900000000000000650010000000011000000015"


@respx.mock
def test_consultar_protocolo_inexistente_retorna_status_nao_encontrado():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["consulta_protocolo"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_CONSULTA_INEXISTENTE)
    )

    resultado = webservice_client.consultar_protocolo(
        "53260900000000000000650010000000011000000015", ambiente="homologacao"
    )

    assert resultado["status"] == "nao_encontrado"
    assert "não consta" in resultado["mensagem"]


@respx.mock
def test_consultar_protocolo_com_erro_de_rede_retorna_status_erro():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["consulta_protocolo"]).mock(
        side_effect=httpx.ConnectTimeout("tempo esgotado")
    )

    resultado = webservice_client.consultar_protocolo(
        "53260900000000000000650010000000011000000015", ambiente="homologacao"
    )

    assert resultado["status"] == "erro"
    assert resultado["mensagem"]


@respx.mock
def test_cancelar_homologado_retorna_status_cancelado():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["recepcao_evento"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_CANCELAMENTO_HOMOLOGADO)
    )

    resultado = webservice_client.cancelar(
        chave_acesso="53260900000000000000650010000000011000000015",
        protocolo_autorizacao="153260000000015",
        motivo="Cancelamento solicitado pelo cliente por engano na emissao",
        xml_assinado_evento="<evento-assinado-fake/>",
        ambiente="homologacao",
    )

    assert resultado["status"] == "cancelado"
    assert resultado["protocolo"] == "153260000000099"


@respx.mock
def test_cancelar_rejeitado_retorna_status_rejeitado_com_motivo():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["recepcao_evento"]).mock(
        return_value=httpx.Response(200, text=RESPOSTA_CANCELAMENTO_REJEITADO)
    )

    resultado = webservice_client.cancelar(
        chave_acesso="53260900000000000000650010000000011000000015",
        protocolo_autorizacao="protocolo-invalido",
        motivo="Cancelamento solicitado pelo cliente por engano na emissao",
        xml_assinado_evento="<evento-assinado-fake/>",
        ambiente="homologacao",
    )

    assert resultado["status"] == "rejeitado"
    assert "Protocolo de autorizacao invalido" in resultado["mensagem"]


@respx.mock
def test_cancelar_com_erro_de_rede_retorna_status_erro_em_vez_de_lancar_excecao():
    respx.post(webservice_client.ENDPOINTS["homologacao"]["recepcao_evento"]).mock(
        side_effect=httpx.ConnectError("conexão recusada")
    )

    resultado = webservice_client.cancelar(
        chave_acesso="53260900000000000000650010000000011000000015",
        protocolo_autorizacao="153260000000015",
        motivo="Cancelamento solicitado pelo cliente por engano na emissao",
        xml_assinado_evento="<evento-assinado-fake/>",
        ambiente="homologacao",
    )

    assert resultado["status"] == "erro"
    assert resultado["mensagem"]

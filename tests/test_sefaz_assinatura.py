from xml.etree import ElementTree

from app.services.fiscal.sefaz_direto import assinatura

XML_TESTE = (
    '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
    '<infNFe Id="NFe12345678901234567890123456789012345678901234" versao="4.00">'
    "<ide><cUF>53</cUF></ide>"
    "</infNFe>"
    "</NFe>"
)


def test_assinar_xml_adiciona_elemento_signature():
    xml_assinado = assinatura.assinar_xml(XML_TESTE, "tests/fixtures/certificado_teste.pfx", "senha-teste")

    assert "Signature" in xml_assinado
    ElementTree.fromstring(xml_assinado)  # continua sendo XML bem-formado


def test_assinar_xml_com_senha_errada_levanta_erro_claro():
    try:
        assinatura.assinar_xml(XML_TESTE, "tests/fixtures/certificado_teste.pfx", "senha-errada")
        assert False, "deveria ter levantado uma exceção"
    except Exception as exc:
        assert "senha" in str(exc).lower() or "password" in str(exc).lower() or "invalid" in str(exc).lower()


def test_assinar_xml_com_certificado_inexistente_levanta_value_error_claro():
    try:
        assinatura.assinar_xml(XML_TESTE, "tests/fixtures/NAO_EXISTE.pfx", "senha-teste")
        assert False, "deveria ter levantado uma exceção"
    except TypeError:
        assert False, "não deveria vazar um TypeError cru da cryptography -- deve ser um ValueError claro"
    except ValueError as exc:
        mensagem = str(exc).lower()
        assert "não encontrado" in mensagem or "not found" in mensagem or "nao_existe.pfx" in mensagem

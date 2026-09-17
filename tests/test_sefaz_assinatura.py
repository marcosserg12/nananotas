from xml.etree import ElementTree

import signxml
from lxml import etree
from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod

from app.services.fiscal.sefaz_direto import assinatura
from erpbrasil.assinatura.certificado import Certificado

XML_TESTE = (
    '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
    '<infNFe Id="NFe12345678901234567890123456789012345678901234" versao="4.00">'
    "<ide><cUF>53</cUF></ide>"
    "</infNFe>"
    "</NFe>"
)

XML_TESTE_INUT = (
    '<inutNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
    '<infInut Id="ID53250264237800001766500010000000050000000060">'
    "<tpAmb>2</tpAmb><xServ>INUTILIZAR</xServ><cUF>53</cUF><ano>25</ano>"
    "<CNPJ>26423780000176</CNPJ><mod>65</mod><serie>1</serie>"
    "<nNFIni>5</nNFIni><nNFFin>5</nNFFin>"
    "<xJust>Falha de emissao detectada pelo sistema automaticamente</xJust>"
    "</infInut></inutNFe>"
)

# Mesma configuração RSA-SHA1 usada para assinar (ver módulo assinatura.py) --
# o signxml "puro" desencoraja RSA-SHA1 por padrão, então a verificação
# independente precisa declarar explicitamente que esse é o algoritmo
# esperado, do contrário rejeita a assinatura por política, não por ela
# estar errada.
_CONFIG_VERIFICACAO_RSA_SHA1 = SignatureConfiguration(
    require_x509=True,
    location=".//",
    expect_references=1,
    signature_methods=frozenset({SignatureMethod.RSA_SHA1}),
    digest_algorithms=frozenset({DigestAlgorithm.SHA1}),
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


def test_assinar_xml_com_nome_elemento_infinut_assina_o_elemento_correto():
    """Generalização introduzida na Task 8 para permitir assinar documentos
    Sefaz diferentes de infNFe (aqui, o pedido de inutilização, `infInut`).
    Verifica que o comportamento por elemento não-default funciona, sem
    tocar no comportamento default (`infNFe`) coberto pelos testes acima."""
    xml_assinado = assinatura.assinar_xml(
        XML_TESTE_INUT, "tests/fixtures/certificado_teste.pfx", "senha-teste", nome_elemento="infInut"
    )

    assert "Signature" in xml_assinado
    root = ElementTree.fromstring(xml_assinado)  # continua sendo XML bem-formado
    tags = [_nome_local(el.tag) for el in root]
    assert tags == ["infInut", "Signature"]  # Signature como irmão de infInut, na raiz


def test_assinar_xml_com_nome_elemento_infinut_produz_assinatura_criptograficamente_valida():
    """Verificação independente (signxml.XMLVerifier, não o próprio
    erpbrasil.assinatura) de que a assinatura de um elemento não-infNFe é
    real, não apenas "parece assinado" -- mesmo rigor descrito na docstring
    do módulo assinatura.py para o caso infNFe original, e inclui um teste
    de adulteração para confirmar que a verificação de fato protege a
    integridade do documento."""
    xml_assinado = assinatura.assinar_xml(
        XML_TESTE_INUT, "tests/fixtures/certificado_teste.pfx", "senha-teste", nome_elemento="infInut"
    )
    certificado = Certificado("tests/fixtures/certificado_teste.pfx", "senha-teste")

    root = etree.fromstring(xml_assinado.encode("utf-8"))
    resultado = signxml.XMLVerifier().verify(
        root, expect_config=_CONFIG_VERIFICACAO_RSA_SHA1, x509_cert=certificado._cert
    )
    assert resultado is not None

    xml_adulterado = xml_assinado.replace("<nNFIni>5</nNFIni>", "<nNFIni>6</nNFIni>")
    root_adulterado = etree.fromstring(xml_adulterado.encode("utf-8"))
    try:
        signxml.XMLVerifier().verify(
            root_adulterado, expect_config=_CONFIG_VERIFICACAO_RSA_SHA1, x509_cert=certificado._cert
        )
        assert False, "verificação deveria ter falhado sobre XML adulterado"
    except signxml.exceptions.SignXMLException:
        pass


def _nome_local(tag: str) -> str:
    return tag.split("}")[-1]

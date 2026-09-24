import os
from datetime import datetime

import nfelib
import pytest
import signxml
from erpbrasil.assinatura.certificado import Certificado
from lxml import etree
from signxml import DigestAlgorithm, SignatureConfiguration, SignatureMethod

from app.services.fiscal.sefaz_direto import assinatura, evento_cancelamento

CHAVE = "53260926423780000176650020000000011247514759"
PROTOCOLO = "253260545400036"
CERTIFICADO = "tests/fixtures/certificado_teste.pfx"
SENHA = "senha-teste"
XSD_ENVIO = os.path.join(
    os.path.dirname(nfelib.__file__), "nfe_evento_cancel", "schemas", "v1_0", "envEventoCancNFe_v1.00.xsd"
)
_CONFIG_RSA_SHA1 = SignatureConfiguration(
    require_x509=True,
    location=".//",
    expect_references=1,
    signature_methods=frozenset({SignatureMethod.RSA_SHA1}),
    digest_algorithms=frozenset({DigestAlgorithm.SHA1}),
)
JUSTIFICATIVA = "Nota emitida como teste, cancelada pelo estabelecimento"


def _evento(**extras):
    dados = dict(
        chave_acesso=CHAVE, protocolo=PROTOCOLO, justificativa=JUSTIFICATIVA,
        ambiente="producao", momento_utc=datetime(2026, 9, 24, 13, 30, 0),
    )
    dados.update(extras)
    return evento_cancelamento.montar_evento(**dados)


def _envio_assinado(**extras):
    evento = _evento(**extras)
    assinado = assinatura.assinar_xml(evento, CERTIFICADO, SENHA, nome_elemento="infEvento")
    return evento_cancelamento.montar_envio(assinado, "123456789012345")


def test_envio_assinado_e_valido_contra_o_esquema_oficial_da_sefaz():
    """O esquema `envEventoCancNFe_v1.00.xsd` (o mesmo que a Sefaz usa) é a
    referência: se o XML fugir dele por qualquer campo, o pedido seria
    rejeitado por schema antes de qualquer regra de negócio."""
    esquema = etree.XMLSchema(etree.parse(XSD_ENVIO))
    documento = etree.fromstring(_envio_assinado().encode("utf-8"))

    esquema.assertValid(documento)


def test_campos_do_evento_batem_com_a_nota_e_o_ambiente():
    raiz = etree.fromstring(_evento().encode("utf-8"))
    ns = {"n": "http://www.portalfiscal.inf.br/nfe"}

    def texto(tag):
        return raiz.find(f".//n:{tag}", ns).text

    assert raiz.find(".//n:infEvento", ns).get("Id") == f"ID110111{CHAVE}01"
    assert texto("cOrgao") == "53"
    assert texto("tpAmb") == "1"
    assert texto("CNPJ") == "26423780000176"
    assert texto("chNFe") == CHAVE
    assert texto("tpEvento") == "110111"
    assert texto("nSeqEvento") == "1"
    assert texto("descEvento") == "Cancelamento"
    assert texto("nProt") == PROTOCOLO
    assert texto("xJust") == JUSTIFICATIVA
    assert texto("dhEvento") == "2026-09-24T10:30:00-03:00"


def test_homologacao_usa_tpamb_2():
    raiz = etree.fromstring(_evento(ambiente="homologacao").encode("utf-8"))

    assert raiz.find(".//{http://www.portalfiscal.inf.br/nfe}tpAmb").text == "2"


def test_assinatura_do_evento_e_criptograficamente_valida_e_detecta_adulteracao():
    """Verificação independente (signxml.XMLVerifier, não a mesma biblioteca que
    assinou), e um teste de adulteração pra provar que a checagem protege de fato."""
    certificado = Certificado(CERTIFICADO, SENHA)
    envio = _envio_assinado()

    raiz = etree.fromstring(envio.encode("utf-8"))
    assert signxml.XMLVerifier().verify(raiz, expect_config=_CONFIG_RSA_SHA1, x509_cert=certificado._cert) is not None

    adulterado = etree.fromstring(envio.replace(PROTOCOLO, "999999999999999").encode("utf-8"))
    with pytest.raises(Exception):
        signxml.XMLVerifier().verify(adulterado, expect_config=_CONFIG_RSA_SHA1, x509_cert=certificado._cert)


def test_assinatura_fica_dentro_do_evento_como_irma_do_infevento():
    raiz = etree.fromstring(_envio_assinado().encode("utf-8"))
    ns = {"n": "http://www.portalfiscal.inf.br/nfe", "d": "http://www.w3.org/2000/09/xmldsig#"}

    evento = raiz.find("n:evento", ns)
    filhos = [etree.QName(f).localname for f in evento]

    assert filhos == ["infEvento", "Signature"]


def test_justificativa_tira_acentos_e_espacos_sobrando():
    assert (
        evento_cancelamento.normalizar_justificativa("  Cancelamento   por erro de digitação — item errado ")
        == "Cancelamento por erro de digitacao item errado"
    )


def test_justificativa_com_caracteres_especiais_de_xml_e_escapada():
    xml = _evento(justificativa="Cancelado a pedido: cliente & filhos <desistiu>")

    assert "&amp;" in xml and "&lt;desistiu&gt;" in xml
    etree.fromstring(xml.encode("utf-8"))  # continua XML bem formado


@pytest.mark.parametrize("texto", ["", "curta demais", "   muito     curto   "])
def test_justificativa_com_menos_de_15_caracteres_e_recusada(texto):
    with pytest.raises(ValueError, match="pelo menos 15"):
        evento_cancelamento.normalizar_justificativa(texto)


def test_justificativa_com_mais_de_255_caracteres_e_recusada():
    with pytest.raises(ValueError, match="no máximo 255"):
        evento_cancelamento.normalizar_justificativa("a" * 256)


@pytest.mark.parametrize("chave", ["123", "5" * 43, "a" * 44])
def test_chave_invalida_e_recusada(chave):
    with pytest.raises(ValueError, match="Chave de acesso inválida"):
        _evento(chave_acesso=chave)


@pytest.mark.parametrize("protocolo", ["", None, "abc"])
def test_sem_protocolo_valido_nao_monta_o_evento(protocolo):
    with pytest.raises(ValueError, match="protocolo"):
        _evento(protocolo=protocolo)

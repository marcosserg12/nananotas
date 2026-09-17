"""Assina o elemento `infNFe` do XML da NFC-e com o certificado A1 (.pfx).

A implementação usa `erpbrasil.assinatura` (pacote real instalado neste
ambiente, puxado pelo extra de assinatura da Task 1 -- ver
`requirements.txt`: `erpbrasil.assinatura>=1.7.0` e `signxml>=3.2.0`), que é o
wrapper padrão do ecossistema nfelib/erpbrasil em torno do `signxml` e
reintroduz o suporte a RSA-SHA1 que o `signxml` "puro" desencoraja (mas que
Sefaz ainda exige).

API real inspecionada por leitura do código-fonte instalado (não
documentação nem memória), em
`site-packages/erpbrasil/assinatura/{assinatura,certificado,excecoes}.py`
(versão 1.8.0, `erpbrasil.assinatura.__version__`):

- `erpbrasil.assinatura.certificado.Certificado(arquivo, senha,
  raise_expirado=True)`: `arquivo` pode ser um *path* (string) para um
  arquivo existente -- é o caso aqui. Internamente chama
  `cryptography.hazmat...pkcs12.load_key_and_certificates`; se a senha
  estiver errada (ou o arquivo não for um PKCS#12 válido), a `ValueError`
  da `cryptography` é capturada e relançada como
  `erpbrasil.assinatura.excecoes.CertificadoSenhaInvalida("Certificado ou
  senha inválida!!!")`. Expõe `.key` (objeto `RSAPrivateKey` da
  `cryptography`) e `.cert`/`._cert` (objeto `x509.Certificate` e sua forma
  PEM em bytes, respectivamente) após carregado com sucesso.
- `erpbrasil.assinatura.assinatura.XMLSignerWithSHA1`: subclasse de
  `signxml.XMLSigner` exportada pelo próprio módulo `assinatura.py` que
  apenas desabilita o aviso de "método depreciado" do `signxml` para poder
  usar `signature_algorithm="rsa-sha1"` / `digest_algorithm="sha1"`
  (exatamente a variante RSA-SHA1 enveloped exigida pela Sefaz).
- `erpbrasil.assinatura.assinatura.Assinatura(certificado).assina_xml2(
  xml_element, reference, getchildren=False)`: é o método de mais alto
  nível da biblioteca para assinar por `Id`, e foi a primeira opção
  tentada aqui. **Mas a inspeção não parou na leitura do código-fonte**: ao
  assinar o XML de teste deste módulo com `assina_xml2` e então verificar a
  assinatura resultante de forma independente com `signxml.XMLVerifier`
  (não o próprio `erpbrasil`, para evitar "a biblioteca validando a si
  mesma"), a verificação **falhou** com `InvalidSignature` na checagem
  RSA da `SignedInfo` (o dígest do `Reference` batia, mas a assinatura
  RSA sobre o `SignedInfo` canonicalizado, não). Isolando a causa: o
  problema é a linha `signer.namespaces = {None: signxml.namespaces.ds}`
  dentro de `assina_xml2`, que força o namespace do XMLDSig
  (`http://www.w3.org/2000/09/xmldsig#`) a ser o namespace *padrão* (sem
  prefixo) do elemento `<Signature>` em vez do prefixo `ds:` usado por
  padrão pelo `signxml`. Reproduzido em isolamento (mesmo par
  certificado/chave, mesmo XML, apenas essas duas linhas de configuração
  variando): com o prefixo `ds:` padrão do `signxml`, assinar+verificar
  bate; com o override de namespace do `assina_xml2`, a verificação falha
  de forma consistente e determinística neste ambiente (versões
  `erpbrasil.assinatura==1.8.0` / `signxml` instalada). Ou seja,
  `assina_xml2`, tal como instalado aqui, produz um `<Signature>` que
  *parece* uma assinatura válida (XML bem formado, elemento no lugar
  certo, `DigestValue` batendo) mas **não valida criptograficamente** --
  exatamente o tipo de falha silenciosa que a task pediu para nunca
  aceitar sem investigar.

  Por isso, esta função **não usa `Assinatura.assina_xml2`**. Em vez
  disso, usa `XMLSignerWithSHA1` diretamente (ainda código de
  `erpbrasil.assinatura`, só que a camada mais baixa, sem o wrapper
  `assina_xml2`/`Assinatura` que introduz o override de namespace
  problemático), chamando `.sign(...)` sobre a raiz do documento
  (`<NFe>`) com `reference_uri="#<Id do infNFe>"`. Em modo `enveloped`,
  o próprio `signxml` (confirmado lendo `signxml/signer.py`, função
  `sign()`: `doc_root.append(sig_root)`) anexa `<Signature>` como filho
  do elemento passado como dado a assinar -- então passar a raiz `<NFe>`
  já posiciona `<Signature>` como irmão de `<infNFe>`, dentro de `<NFe>`,
  sem necessidade de realocação manual. Isso bate com o schema real:
  `nfelib.nfe.bindings.v4_0.Nfe` (binding gerado pela `nfelib` a partir do
  XSD oficial) tem os campos `infNFe`, `infNFeSupl` e `signature` como
  irmãos -- `Signature` não é filho de `infNFe`. (O uso de prefixo `ds:`
  em vez de namespace padrão sem prefixo é irrelevante para conformidade:
  processadores XML cientes de namespace -- incluindo qualquer validador
  XMLDSig, e a própria Sefaz -- tratam `<ds:Signature
  xmlns:ds="...">`/`<Signature xmlns="...">` como equivalentes; o que
  importa é o namespace URI, não o prefixo literal.)

  Este achado foi verificado de forma independente e reprodutível (ver
  `tests/test_sefaz_assinatura.py` e o relatório desta task para o
  script de verificação usado com `signxml.XMLVerifier` diretamente,
  incluindo um teste de adulteração que confirma que alterar um valor no
  XML assinado quebra a verificação -- ou seja, a assinatura produzida
  por este módulo não é apenas "parece válida", ela de fato protege a
  integridade do documento).

- `Certificado`/`Assinatura` continuam sendo usados normalmente para
  carregar o certificado e obter mensagens de erro claras (senha errada,
  certificado expirado, arquivo ilegível) -- só o método de assinatura em
  si (`assina_xml2`) foi substituído por uma chamada direta a
  `XMLSignerWithSHA1.sign()`.
"""

import os

import signxml
from lxml import etree

from erpbrasil.assinatura.assinatura import XMLSignerWithSHA1
from erpbrasil.assinatura.certificado import Certificado
from erpbrasil.assinatura.excecoes import (
    CertificadoExpirado,
    CertificadoSenhaInvalida,
    ErroDeLeituraDeArquivo,
)

NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
_INF_NFE_TAG = f"{{{NFE_NAMESPACE}}}infNFe"

_C14N_ALGORITHM = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"


def _localizar_elemento(root: "etree._Element", tag_completa: str) -> "etree._Element | None":
    """Localiza o elemento com a tag `{namespace}nome` informada, seja ele a
    própria raiz do documento ou um descendente dela (o caso normal para
    `infNFe`: raiz `<NFe>`, `infNFe` como filho direto -- mas também o caso
    de outros documentos Sefaz assináveis, como `infInut` sob `<inutNFe>`)."""
    if root.tag == tag_completa:
        return root
    return root.find(f".//{tag_completa}")


def _localizar_inf_nfe(root: "etree._Element") -> "etree._Element | None":
    """Localiza o elemento `infNFe` a ser assinado. Mantida como wrapper
    fino sobre `_localizar_elemento` só por compatibilidade de nome com o
    que já existia; `assinar_xml` abaixo generaliza para outros elementos
    via o parâmetro `nome_elemento`."""
    return _localizar_elemento(root, _INF_NFE_TAG)


def assinar_xml(
    xml_texto: str, certificado_path: str, certificado_senha: str, nome_elemento: str = "infNFe"
) -> str:
    """Assina um elemento do XML (por padrão `infNFe`) usando o certificado
    A1 informado.

    `nome_elemento` generaliza esta função para assinar outros documentos
    Sefaz além da própria NFC-e -- por exemplo `infInut` (pedido de
    inutilização de numeração, Task 8) -- que usam exatamente o mesmo
    mecanismo de assinatura (RSA-SHA1 enveloped, por `Id`, `<Signature>`
    como irmão do elemento referenciado), só que com um elemento raiz de
    dados diferente. O padrão `"infNFe"` preserva o comportamento e a
    assinatura de chamada originais desta função (Task 4/6) inalterados
    para todo código existente.

    1. Carrega o certificado A1 (.pfx) de `certificado_path` com a senha
       `certificado_senha` (via `erpbrasil.assinatura.certificado.Certificado`).
    2. Assina o XML pelo atributo `Id` do elemento `nome_elemento` (RSA-SHA1,
       enveloped signature, via `erpbrasil.assinatura.assinatura.
       XMLSignerWithSHA1` -- ver docstring do módulo para por que não se
       usa `Assinatura.assina_xml2` aqui).
    3. Levanta uma exceção com mensagem clara (nunca falha silenciosamente)
       se o caminho do certificado não existir, a senha estiver errada, o
       certificado estiver expirado, o arquivo não puder ser lido, ou o
       XML de entrada não tiver um elemento `nome_elemento` com `Id` para
       referenciar.
    4. Retorna a string do XML assinado, com `<Signature>` como irmão do
       elemento `nome_elemento` (filho da raiz do documento), como o
       schema exige.
    """
    if not os.path.exists(certificado_path):
        # `erpbrasil.assinatura.certificado.Certificado` só trata `arquivo`
        # como um path se `os.path.exists(arquivo)` for verdadeiro; caso
        # contrário, uma string é tratada como o CONTEÚDO bruto do
        # certificado (não como um path inválido) e acaba sendo passada
        # como `str` para a API da `cryptography`, que espera bytes --
        # resultando em um `TypeError` genérico e confuso ("Cannot convert
        # ... instance to a buffer"), não em uma das exceções tipadas da
        # própria `erpbrasil.assinatura` (`CertificadoSenhaInvalida` etc.).
        # Um `SEFAZ_CERTIFICADO_PATH` mal configurado (typo, path errado no
        # deploy) é um cenário real de produção, então essa checagem
        # explícita evita esse `TypeError` pouco claro e falha cedo com uma
        # mensagem inequívoca.
        raise ValueError(f"Certificado não encontrado: {certificado_path}")

    try:
        certificado = Certificado(certificado_path, certificado_senha)
    except CertificadoSenhaInvalida as exc:
        raise ValueError(
            f"Senha do certificado A1 inválida (ou arquivo .pfx corrompido/não é PKCS#12 válido): {exc}"
        ) from exc
    except CertificadoExpirado as exc:
        raise ValueError(f"Certificado A1 expirado: {exc}") from exc
    except ErroDeLeituraDeArquivo as exc:
        raise ValueError(f"Não foi possível ler o arquivo do certificado A1 '{certificado_path}': {exc}") from exc

    try:
        root = etree.fromstring(xml_texto.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML de entrada mal formado, não é possível assinar: {exc}") from exc

    tag_completa = f"{{{NFE_NAMESPACE}}}{nome_elemento}"
    elemento = _localizar_elemento(root, tag_completa)
    if elemento is None:
        raise ValueError(f"XML de entrada não contém um elemento {nome_elemento} para assinar.")

    reference = elemento.get("Id")
    if not reference:
        raise ValueError(
            f"Elemento {nome_elemento} do XML de entrada não possui atributo Id para referenciar na assinatura."
        )

    signer = XMLSignerWithSHA1(
        method=signxml.methods.enveloped,
        signature_algorithm="rsa-sha1",
        digest_algorithm="sha1",
        c14n_algorithm=_C14N_ALGORITHM,
    )
    signed_root = signer.sign(
        root,
        key=certificado.key,
        cert=certificado._cert,
        reference_uri=f"#{reference}",
    )

    return etree.tostring(signed_root, encoding=str)

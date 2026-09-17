"""Cliente SOAP para os webservices da Sefaz-DF/SVRS (NFC-e modelo 65).

A Receita do DF delega o processamento de NFC-e ao SVRS (Sped Virtual RS),
por isso os endpoints usados aqui são os do SVRS (`*.svrs.rs.gov.br`), não
os do Portal da Receita do DF diretamente.

## Verificação do WSDL ao vivo (ver tarefa 5 do plano) -- IMPORTANTE

Antes de escrever este módulo, tentamos buscar ao vivo
`https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx?wsdl`
(e os WSDLs irmãos de consulta/evento). O servidor responde e é
genuinamente o portal da NFC-e/Sefaz-RS (a raiz `/` devolve 200 com o HTML
do portal), mas toda rota sob `/ws/*.asmx` -- incluindo com `?wsdl` -- devolve
**403 Forbidden** ("You do not have permission to view this directory or
page using the credentials that you supplied"), mesmo variando User-Agent.
O handshake TLS completa normalmente (via curl/schannel); o 403 acontece na
camada HTTP/IIS. Isso é consistente com o comportamento conhecido dos
webservices da NF-e/NFC-e nacionalmente: essas rotas exigem TLS mútuo com um
certificado cliente ICP-Brasil (e-CNPJ) válido apresentado no handshake --
não é um problema de rede/DNS/CA, e não é contornável sem um certificado A1
de produção, que não deve ser usado apenas para "espiar" um WSDL.

Portanto **a estrutura do envelope abaixo não foi confirmada contra o WSDL
ao vivo desta tarefa**. Ela é a mesma estrutura que o rascunho do plano já
apontava, e foi corroborada por uma segunda fonte nesta sessão: WSDLs
públicos do mesmo contrato nacional de NF-e/NFC-e (que todas as UFs,
incluindo o SVRS, implementam de forma padronizada) publicados em
bibliotecas open-source (ex.: ZeusAutomacao/DFe.NET, wmixvideo/nfe, gist
com NfeAutorizacao4.wsdl de outra UF) confirmam:
- namespace `http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4`
- elemento de requisição `nfeDadosMsg` e de resposta `nfeResultMsg`
- SOAPAction `.../NFeAutorizacao4/nfeAutorizacaoLote`
- para consulta de protocolo: namespace `NFeConsultaProtocolo4`,
  operação `nfeConsultaNF`
- para eventos (cancelamento): namespace `NFeRecepcaoEvento4`,
  operação `nfeRecepcaoEvento`

Isso é pesquisa secundária, não uma confirmação ao vivo. **Antes de qualquer
uso real (mesmo em homologação), este envelope precisa passar por um teste
de fumaça real contra a Sefaz com um certificado A1 válido**, porque só
nesse momento seria possível descobrir eventuais diferenças específicas do
SVRS (o SVRS é conhecido por, historicamente, ter pequenas particularidades
em relação ao contrato "padrão" de outras UFs).
"""

from xml.etree import ElementTree

import httpx

ENDPOINTS = {
    "homologacao": {
        "autorizacao": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "consulta_protocolo": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfce-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "inutilizacao": "https://nfce-homologacao.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "recepcao_evento": "https://nfce-homologacao.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
    "producao": {
        "autorizacao": "https://nfce.svrs.rs.gov.br/ws/NfeAutorizacao/NFeAutorizacao4.asmx",
        "consulta_protocolo": "https://nfce.svrs.rs.gov.br/ws/NfeConsulta/NfeConsulta4.asmx",
        "status_servico": "https://nfce.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx",
        "inutilizacao": "https://nfce.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx",
        "recepcao_evento": "https://nfce.svrs.rs.gov.br/ws/recepcaoevento/recepcaoevento4.asmx",
    },
}

# Namespaces/operações do contrato nacional de webservices da NF-e/NFC-e --
# ver nota acima: corroborados por pesquisa secundária, não pelo WSDL ao vivo.
_NAMESPACE_AUTORIZACAO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeAutorizacao4"
_OPERACAO_AUTORIZACAO = "nfeAutorizacaoLote"

_NAMESPACE_CONSULTA = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeConsultaProtocolo4"
_OPERACAO_CONSULTA = "nfeConsultaNF"

_NAMESPACE_RECEPCAO_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
_OPERACAO_RECEPCAO_EVENTO = "nfeRecepcaoEvento"

_TIMEOUT_PADRAO_SEGUNDOS = 30.0

_CODIGOS_CSTAT_AUTORIZADO = {"100"}
_CODIGOS_CSTAT_CANCELADO_NA_CONSULTA = {"101", "135", "151"}
_CODIGOS_CSTAT_NAO_ENCONTRADO = {"217", "218"}
_CODIGO_CSTAT_EVENTO_REGISTRADO = "135"


def _montar_envelope(xml_dados: str, namespace: str) -> str:
    """Envolve `xml_dados` (já pronto -- assinado quando aplicável) no
    envelope SOAP 1.2 padrão dos webservices da NF-e/NFC-e."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
        "<soap:Body>"
        f'<nfeDadosMsg xmlns="{namespace}">{xml_dados}</nfeDadosMsg>'
        "</soap:Body>"
        "</soap:Envelope>"
    )


def _cabecalhos_soap(namespace: str, operacao: str) -> dict:
    soap_action = f"{namespace}/{operacao}"
    return {
        # SOAP 1.2: a action vai como parâmetro do Content-Type. Mantemos
        # também o header SOAPAction (SOAP 1.1) por compatibilidade -- alguns
        # proxies/WAFs na frente de webservices de Sefaz ainda o inspecionam.
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{soap_action}"',
        "SOAPAction": soap_action,
    }


def _postar_envelope(
    url: str, xml_dados: str, namespace: str, operacao: str
) -> tuple[httpx.Response | None, str | None]:
    envelope = _montar_envelope(xml_dados, namespace)
    try:
        response = httpx.post(
            url,
            content=envelope.encode("utf-8"),
            headers=_cabecalhos_soap(namespace, operacao),
            timeout=_TIMEOUT_PADRAO_SEGUNDOS,
        )
    except httpx.HTTPError as exc:
        return None, f"Falha de comunicação com a Sefaz: {exc}"
    return response, None


def _nome_local(tag: str) -> str:
    return tag.split("}")[-1]


def _localizar_primeiro(elemento: "ElementTree.Element", nome: str) -> "ElementTree.Element | None":
    for filho in elemento.iter():
        if _nome_local(filho.tag) == nome:
            return filho
    return None


def _texto(elemento: "ElementTree.Element | None", nome: str) -> str | None:
    if elemento is None:
        return None
    encontrado = _localizar_primeiro(elemento, nome)
    return encontrado.text if encontrado is not None else None


def _parsear_resposta(response_text: str) -> tuple["ElementTree.Element | None", str | None]:
    try:
        return ElementTree.fromstring(response_text), None
    except ElementTree.ParseError as exc:
        return None, f"Resposta da Sefaz não é um XML válido: {exc}"


def autorizar(xml_assinado: str, ambiente: str = "homologacao") -> dict:
    """Envia o XML assinado da NFC-e para autorização (lote de 1 nota).

    Retorna um dict com `status` em {"autorizado", "rejeitado", "erro"},
    `protocolo`, `chave_acesso` e `mensagem`.
    """
    url = ENDPOINTS[ambiente]["autorizacao"]
    response, erro = _postar_envelope(url, xml_assinado, _NAMESPACE_AUTORIZACAO, _OPERACAO_AUTORIZACAO)
    if erro:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro}

    raiz, erro_parse = _parsear_resposta(response.text)
    if erro_parse:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro_parse}

    inf_prot = _localizar_primeiro(raiz, "infProt")
    origem = inf_prot if inf_prot is not None else raiz
    cstat = _texto(origem, "cStat")
    mensagem = _texto(origem, "xMotivo") or ""

    if cstat in _CODIGOS_CSTAT_AUTORIZADO:
        return {
            "status": "autorizado",
            "protocolo": _texto(origem, "nProt"),
            "chave_acesso": _texto(origem, "chNFe"),
            "mensagem": mensagem,
        }
    return {
        "status": "rejeitado",
        "protocolo": None,
        "chave_acesso": None,
        "mensagem": mensagem or "Rejeitado pela Sefaz sem motivo informado",
    }


def _tpamb(ambiente: str) -> str:
    return "1" if ambiente == "producao" else "2"


def _montar_cons_sit_nfe(chave_acesso: str, ambiente: str) -> str:
    return (
        '<consSitNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f"<tpAmb>{_tpamb(ambiente)}</tpAmb>"
        "<xServ>CONSULTAR</xServ>"
        f"<chNFe>{chave_acesso}</chNFe>"
        "</consSitNFe>"
    )


def consultar_protocolo(chave_acesso: str, ambiente: str = "homologacao") -> dict:
    """Consulta a situação de uma NFC-e já transmitida pela chave de acesso.

    Retorna um dict com `status` em
    {"autorizado", "cancelado", "nao_encontrado", "rejeitado", "erro"},
    `protocolo`, `chave_acesso` e `mensagem`.
    """
    url = ENDPOINTS[ambiente]["consulta_protocolo"]
    dados = _montar_cons_sit_nfe(chave_acesso, ambiente)
    response, erro = _postar_envelope(url, dados, _NAMESPACE_CONSULTA, _OPERACAO_CONSULTA)
    if erro:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro}

    raiz, erro_parse = _parsear_resposta(response.text)
    if erro_parse:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro_parse}

    inf_prot = _localizar_primeiro(raiz, "infProt")
    if inf_prot is not None:
        cstat = _texto(inf_prot, "cStat")
        mensagem = _texto(inf_prot, "xMotivo") or ""
        protocolo = _texto(inf_prot, "nProt")
        chave = _texto(inf_prot, "chNFe")
        if cstat in _CODIGOS_CSTAT_AUTORIZADO:
            return {"status": "autorizado", "protocolo": protocolo, "chave_acesso": chave, "mensagem": mensagem}
        if cstat in _CODIGOS_CSTAT_CANCELADO_NA_CONSULTA:
            return {"status": "cancelado", "protocolo": protocolo, "chave_acesso": chave, "mensagem": mensagem}
        return {
            "status": "rejeitado",
            "protocolo": None,
            "chave_acesso": None,
            "mensagem": mensagem or "Rejeitado pela Sefaz sem motivo informado",
        }

    # Sem <infProt>: a Sefaz não encontrou a nota (resposta mais rasa, sem
    # protocolo -- cStat/xMotivo direto sob <retConsSitNFe>).
    cstat = _texto(raiz, "cStat")
    mensagem = _texto(raiz, "xMotivo") or ""
    if cstat in _CODIGOS_CSTAT_NAO_ENCONTRADO:
        return {"status": "nao_encontrado", "protocolo": None, "chave_acesso": None, "mensagem": mensagem}
    return {
        "status": "erro",
        "protocolo": None,
        "chave_acesso": None,
        "mensagem": mensagem or "Resposta inesperada da Sefaz na consulta de protocolo",
    }


def cancelar(
    chave_acesso: str,
    protocolo_autorizacao: str,
    motivo: str,
    xml_assinado_evento: str,
    ambiente: str = "homologacao",
) -> dict:
    """Envia o evento de cancelamento (já montado e assinado pelo chamador
    -- ver `assinatura.assinar_xml` -- com `chave_acesso`, `protocolo_autorizacao`
    e `motivo` já embutidos no XML do evento) para o webservice de recepção
    de eventos.

    `chave_acesso`, `protocolo_autorizacao` e `motivo` não são usados para
    montar o envelope (o XML do evento já os contém, assinados); são aceitos
    aqui para manter uma assinatura de função autoexplicativa e simétrica ao
    fluxo completo de cancelamento, e para compor `chave_acesso` de fallback
    na resposta caso a Sefaz não a devolva.

    Retorna um dict com `status` em {"cancelado", "rejeitado", "erro"},
    `protocolo`, `chave_acesso` e `mensagem`.
    """
    url = ENDPOINTS[ambiente]["recepcao_evento"]
    response, erro = _postar_envelope(
        url, xml_assinado_evento, _NAMESPACE_RECEPCAO_EVENTO, _OPERACAO_RECEPCAO_EVENTO
    )
    if erro:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro}

    raiz, erro_parse = _parsear_resposta(response.text)
    if erro_parse:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro_parse}

    inf_evento = _localizar_primeiro(raiz, "infEvento")
    origem = inf_evento if inf_evento is not None else raiz
    cstat = _texto(origem, "cStat")
    mensagem = _texto(origem, "xMotivo") or ""

    if cstat == _CODIGO_CSTAT_EVENTO_REGISTRADO:
        return {
            "status": "cancelado",
            "protocolo": _texto(origem, "nProt"),
            "chave_acesso": _texto(origem, "chNFe") or chave_acesso,
            "mensagem": mensagem,
        }
    return {
        "status": "rejeitado",
        "protocolo": None,
        "chave_acesso": chave_acesso,
        "mensagem": mensagem or "Rejeitado pela Sefaz sem motivo informado",
    }

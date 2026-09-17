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

from datetime import datetime
from xml.etree import ElementTree

import httpx
from nfelib.nfe.bindings.v4_0 import InfInutXServ, InutNfe
from nfelib.nfe.bindings.v4_0.tipos_basico_v4_00 import Tamb, TcodUfIbge, Tmod

from app.config import settings
from app.services.fiscal.sefaz_direto import assinatura

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

# Diferente dos namespaces/operações acima (corroborados só por pesquisa
# secundária -- ver nota no topo do módulo), namespace e operação abaixo
# foram confirmados nesta task (Task 8) lendo o WSDL de verdade que já vem
# empacotado junto com a `nfelib` instalada neste ambiente
# (`site-packages/nfelib/nfe/wsdl/v4_0/nfeinutilizacao4.wsdl`):
# `NFeInutilizacao4` / `nfeInutilizacaoNF` batem com o que já estava em uso.
#
# O que esse WSDL NÃO confirma: o hostname de produção usado em
# `ENDPOINTS["producao"]["inutilizacao"]` abaixo. Esse WSDL empacotado é da
# infraestrutura genérica de NF-e (modelo 55) do SVRS -- seu
# `soap:address`/`soap12:address` aponta para
# `https://nfe.svrs.rs.gov.br/ws/nfeinutilizacao/nfeinutilizacao4.asmx`
# (subdomínio `nfe`), enquanto `ENDPOINTS["producao"]["inutilizacao"]` usa
# `https://nfce.svrs.rs.gov.br/...` (subdomínio `nfce`, específico de
# NFC-e/modelo 65, o mesmo padrão dos demais endpoints deste dicionário).
# Cruzado com `nfelib.nfe.client.v4_0.servers` nesta task: confirma que o
# WSDL empacotado é mesmo o genérico de NF-e, não um WSDL NFC-e-específico
# -- ou seja, ele NÃO corrobora o hostname usado abaixo. Esse hostname
# continua não verificado contra uma fonte ao vivo, a mesma ressalva já
# registrada para `autorizar`/`consultar_protocolo` na Task 5: exige teste
# de fumaça real em homologação antes de qualquer uso em produção (ver
# docstring no topo do módulo).
_NAMESPACE_INUTILIZACAO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeInutilizacao4"
_OPERACAO_INUTILIZACAO = "nfeInutilizacaoNF"

_TIMEOUT_PADRAO_SEGUNDOS = 30.0

_CODIGOS_CSTAT_AUTORIZADO = {"100"}
_CODIGOS_CSTAT_CANCELADO_NA_CONSULTA = {"101", "135", "151"}
_CODIGOS_CSTAT_NAO_ENCONTRADO = {"217", "218"}
_CODIGO_CSTAT_EVENTO_REGISTRADO = "135"
_CODIGO_CSTAT_INUTILIZADO = "102"

# cStat de LOTE (não de nota individual): "103" (lote recebido com sucesso,
# fluxo assíncrono normalmente ainda em processamento) e "104" (lote
# processado). Com indSinc=1 (sempre usado abaixo -- ver _montar_envi_nfe),
# a Sefaz deveria sempre responder de forma síncrona com <protNFe> já
# preenchido, nunca com um desses códigos "soltos" sem <infProt> -- mas
# tratamos esse caso defensivamente em vez de presumir que nunca acontece
# (achado "Important #10" da revisão final do branch).
_CODIGOS_CSTAT_LOTE = {"103", "104"}

# cUF (Distrito Federal) e mod (NFC-e) fixos -- mesmos valores hardcoded em
# `xml_builder.CUF_EMITENTE`/`Tmod.VALUE_65`, porque este sistema inteiro só
# emite NFC-e para um único emitente no DF (Nana Lanches), nunca NF-e (mod
# 55) nem outra UF.
_CUF_EMITENTE_INUTILIZACAO = TcodUfIbge.VALUE_53
_MOD_NFCE_INUTILIZACAO = Tmod.VALUE_65


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


def _gerar_id_lote() -> str:
    """Gera um `idLote` numérico razoavelmente único por envio (timestamp em
    milissegundos). O schema (`TEnviNFe.idLote`) só exige `[0-9]{1,15}` --
    não há semântica de negócio atribuída pela Sefaz além de "identificador
    do lote enviado pelo contribuinte", e este sistema não gerencia lotes de
    verdade (sempre envia 1 nota por lote -- ver `_montar_envi_nfe`)."""
    return str(int(datetime.now().timestamp() * 1000))


def _montar_envi_nfe(xml_nfe_assinado: str, id_lote: str) -> str:
    """Envolve o XML assinado da NFC-e no elemento raiz `enviNFe`
    (`TEnviNFe`, `enviNFe_v4.00.xsd`) -- o elemento de fato exigido pelo
    webservice de autorização como corpo do pedido, não um `<NFe>` cru (ver
    achado "Critical #2" da revisão final do branch: `enviNFe_v4.00.xsd`
    declara `enviNFe` como elemento global do tipo `TEnviNFe`
    -- `idLote`/`indSinc`/um-ou-mais `NFe`/atributo `versao` -- e um `<NFe>`
    solto na raiz falha a validação contra esse XSD; confirmado nesta task
    com `lxml.etree.XMLSchema` contra o XSD de fato empacotado na `nfelib`
    instalada -- ver `tests/test_sefaz_webservice_client.py` e o relatório
    desta task).

    `indSinc` é fixo em "1": NFC-e (modelo 65) deve sempre ser enviada em
    lote síncrono de uma nota só (pesquisa da Task 5, já assumida no
    parsing de resposta abaixo) -- diferente da NF-e (modelo 55), que aceita
    lotes assíncronos de até 50 notas (`TEnviNFe.NFe: max_occurs=50`, mas o
    uso aqui é sempre de exatamente 1).

    Construção por concatenação de string (mesmo estilo já usado neste
    módulo em `_montar_envelope`/`_montar_cons_sit_nfe`) em vez de montar um
    `EnviNfe`/`TenviNfe` da `nfelib` e resserializar: `xml_nfe_assinado` já
    é uma string XML pronta (assinada -- `<Signature>` já embutido por
    `assinatura.assinar_xml`), e resserializá-la via dataclass arriscaria
    reconstruir/reordenar/renamespacear a assinatura já calculada, invalidando
    o digest. Embutir a string assinada diretamente, sem tocar nela, evita
    esse risco.
    """
    return (
        '<enviNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">'
        f"<idLote>{id_lote}</idLote>"
        "<indSinc>1</indSinc>"
        f"{xml_nfe_assinado}"
        "</enviNFe>"
    )


def autorizar(xml_assinado: str, ambiente: str = "homologacao") -> dict:
    """Envia o XML assinado da NFC-e para autorização, envolto no envelope
    `enviNFe` obrigatório (lote síncrono de 1 nota -- ver `_montar_envi_nfe`).

    Retorna um dict com `status` em {"autorizado", "rejeitado", "erro"},
    `protocolo`, `chave_acesso` e `mensagem`.
    """
    url = ENDPOINTS[ambiente]["autorizacao"]
    envi_nfe = _montar_envi_nfe(xml_assinado, _gerar_id_lote())
    response, erro = _postar_envelope(url, envi_nfe, _NAMESPACE_AUTORIZACAO, _OPERACAO_AUTORIZACAO)
    if erro:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro}

    raiz, erro_parse = _parsear_resposta(response.text)
    if erro_parse:
        return {"status": "erro", "protocolo": None, "chave_acesso": None, "mensagem": erro_parse}

    inf_prot = _localizar_primeiro(raiz, "infProt")
    if inf_prot is None:
        # Sem <infProt>: pode ser um cStat de LOTE (103/104 -- ver
        # _CODIGOS_CSTAT_LOTE) em vez de um cStat de NOTA. Com indSinc=1 a
        # Sefaz deveria sempre responder com <infProt> preenchido, mas se
        # isso não acontecer não podemos presumir "rejeitado" -- a nota pode
        # muito bem ter sido autorizada e só não sabemos ainda. Tratado como
        # "erro" (situação indeterminada, precisa de acompanhamento via
        # consultar_protocolo), nunca como "rejeitado" (que sinalizaria,
        # incorretamente, que a nota definitivamente não foi aceita).
        cstat_lote = _texto(raiz, "cStat")
        if cstat_lote in _CODIGOS_CSTAT_LOTE:
            return {
                "status": "erro",
                "protocolo": None,
                "chave_acesso": None,
                "mensagem": (
                    f"Lote recebido pela Sefaz (cStat={cstat_lote}: "
                    f"{_texto(raiz, 'xMotivo') or 'sem motivo informado'}), mas sem protocolo da "
                    "nota (infProt) na resposta -- inesperado para envio síncrono (indSinc=1). "
                    "O status real da nota é desconhecido; consulte pela chave de acesso "
                    "(consultar_protocolo) antes de tratar esta emissão como definitivamente "
                    "rejeitada."
                ),
            }

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


def _somente_digitos(valor: str | None) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def _montar_id_inutilizacao(cnpj: str, ano: str, serie: int, numero_inicial: int, numero_final: int) -> str:
    """Monta o atributo `Id` de `infInut` (padrão `ID[0-9]{41}` confirmado
    via `dataclasses.fields(TinutNfe.InfInut)` nesta task): mesma lógica de
    concatenação com zero-padding da chave de acesso
    (`xml_builder._montar_chave_acesso`), só que sem código numérico
    aleatório nem dígito verificador -- `cUF(2) + ano(2) + CNPJ(14) +
    mod(2) + serie(3) + nNFIni(9) + nNFFin(9)` = 41 dígitos."""
    return (
        "ID"
        + "53"  # cUF -- Distrito Federal, fixo (ver _CUF_EMITENTE_INUTILIZACAO)
        + ano
        + cnpj.zfill(14)
        + "65"  # mod -- NFC-e, fixo (ver _MOD_NFCE_INUTILIZACAO)
        + str(serie).zfill(3)
        + str(numero_inicial).zfill(9)
        + str(numero_final).zfill(9)
    )


def _montar_inf_inut_xml(serie: int, numero_inicial: int, numero_final: int, justificativa: str, ambiente: str) -> str:
    """Monta (sem assinar) o XML do pedido de inutilização de numeração --
    elemento raiz `<inutNFe>`, dados em `infInut` -- usando as classes
    tipadas da `nfelib` (`InutNfe`/`InutNfe.InfInut`/`InfInutXServ`), no
    mesmo espírito de `xml_builder.montar_nfce_xml`: nenhum nome de
    campo/classe abaixo foi inventado, todos foram confirmados nesta task
    via `dataclasses.fields(InutNfe.InfInut)` contra o pacote de fato
    instalado neste ambiente. Ao contrário do `infEvento` de cancelamento
    (Task 6 -- `DetEvento` é um grupo `xs:any` sem tipagem), `infInut` é
    totalmente tipado na `nfelib`, então não há necessidade de montar XML
    bruto à mão aqui.
    """
    cnpj = _somente_digitos(settings.emitente_cnpj)
    if not cnpj:
        raise ValueError(
            "EMITENTE_CNPJ não configurado no .env -- necessário para montar o pedido de inutilização "
            "(campo obrigatório CNPJ de infInut)."
        )

    # "ano" (AA) não tem, hoje, uma origem melhor: os números pendentes de
    # inutilização (numeracao.numeros_reservados_nao_emitidos) não guardam a
    # data em que a reserva foi feita, só o número em si. Usar o ano
    # corrente (momento do pedido de inutilização) é a aproximação usual
    # para essa situação -- documentado aqui em vez de assumido em
    # silêncio; se a reserva falha e a inutilização é solicitada num ano
    # diferente do da reserva, revisar este valor manualmente.
    ano = datetime.now().strftime("%y")
    tp_amb = Tamb.VALUE_1 if ambiente == "producao" else Tamb.VALUE_2

    inf_inut = InutNfe.InfInut(
        tpAmb=tp_amb,
        xServ=InfInutXServ.INUTILIZAR,
        cUF=_CUF_EMITENTE_INUTILIZACAO,
        ano=ano,
        CNPJ=cnpj,
        mod=_MOD_NFCE_INUTILIZACAO,
        serie=str(serie),
        nNFIni=str(numero_inicial),
        nNFFin=str(numero_final),
        xJust=justificativa,
        Id=_montar_id_inutilizacao(cnpj, ano, serie, numero_inicial, numero_final),
    )
    return InutNfe(infInut=inf_inut, versao="4.00").to_xml()


def inutilizar(
    serie: int, numero_inicial: int, numero_final: int, justificativa: str, ambiente: str = "homologacao"
) -> dict:
    """Monta, assina e envia o pedido de inutilização de numeração para a
    faixa [numero_inicial, numero_final] da série informada -- usado para
    fechar formalmente, junto à Sefaz, um "buraco" na numeração deixado por
    números reservados (`numeracao.reservar_proximo_numero`) que nunca
    chegaram a ser emitidos com sucesso (ver `numeracao.
    registrar_falha_apos_reserva`).

    Ao contrário de `autorizar`/`cancelar` (que recebem XML já assinado,
    montado por quem chama -- tipicamente `SefazDiretoProvider`), esta
    função monta e assina o XML sozinha: não há, ainda, um fluxo/provider
    para inutilização (esta task não inclui um método correspondente em
    `SefazDiretoProvider` -- não fazia parte do escopo pedido), e as
    credenciais do certificado A1 (`settings.sefaz_certificado_path`/
    `.sefaz_certificado_senha`) e o CNPJ do emitente (`settings.
    emitente_cnpj`) já são configuração global única deste sistema (um
    emitente só, "Nana Lanches"), então não há razão para exigi-los como
    parâmetros extras aqui.

    Qualquer falha ao montar/assinar o XML (certificado ausente/senha
    errada/emitente não configurado) ou ao comunicar com a Sefaz vira
    `{"status": "erro", "mensagem": ...}` em vez de propagar a exceção --
    mesmo contrato de "nunca lança, sempre devolve um dict" já usado por
    `autorizar`/`consultar_protocolo`/`cancelar` acima.

    Retorna um dict com `status` em {"inutilizado", "erro"} e `mensagem`.
    """
    try:
        url = ENDPOINTS[ambiente]["inutilizacao"]
        xml_sem_assinar = _montar_inf_inut_xml(serie, numero_inicial, numero_final, justificativa, ambiente)
        xml_assinado = assinatura.assinar_xml(
            xml_sem_assinar,
            settings.sefaz_certificado_path,
            settings.sefaz_certificado_senha,
            nome_elemento="infInut",
        )
    except Exception as exc:
        return {"status": "erro", "mensagem": str(exc)}

    response, erro = _postar_envelope(url, xml_assinado, _NAMESPACE_INUTILIZACAO, _OPERACAO_INUTILIZACAO)
    if erro:
        return {"status": "erro", "mensagem": erro}

    raiz, erro_parse = _parsear_resposta(response.text)
    if erro_parse:
        return {"status": "erro", "mensagem": erro_parse}

    inf_inut = _localizar_primeiro(raiz, "infInut")
    origem = inf_inut if inf_inut is not None else raiz
    cstat = _texto(origem, "cStat")
    mensagem = _texto(origem, "xMotivo") or ""

    if cstat == _CODIGO_CSTAT_INUTILIZADO:
        return {"status": "inutilizado", "mensagem": mensagem}
    return {"status": "erro", "mensagem": mensagem or "Rejeitado pela Sefaz sem motivo informado"}

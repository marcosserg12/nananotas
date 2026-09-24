"""Monta o XML do evento de CANCELAMENTO da NFC-e (tpEvento 110111).

O layout segue o esquema oficial `envEventoCancNFe_v1.00.xsd` (empacotado com a
`nfelib`), que os testes usam pra validar a saída deste módulo. O evento é
assinado (RSA-SHA1, pelo `Id` do `infEvento`) por `assinatura.assinar_xml` com
`nome_elemento="infEvento"` e só depois embrulhado no `envEvento` -- a
assinatura precisa ficar DENTRO de `<evento>`, como irmã de `infEvento`.
"""

import re
import unicodedata
from datetime import datetime
from xml.sax.saxutils import escape

from app.services.fiscal.sefaz_direto.xml_builder import FUSO_BRASILIA

NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
TP_EVENTO_CANCELAMENTO = "110111"
JUSTIFICATIVA_MINIMA = 15
JUSTIFICATIVA_MAXIMA = 255


def normalizar_justificativa(texto: str) -> str:
    """A Sefaz exige de 15 a 255 caracteres, sem espaços sobrando e só com
    caracteres Latin-1 -- um travessão ("—") ou emoji faria o pedido ser
    rejeitado por schema. Tira acentos (é seguro e legível) e espaços extras."""
    sem_acentos = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"\s+", " ", sem_acentos).strip()
    if len(limpo) < JUSTIFICATIVA_MINIMA:
        raise ValueError(
            f"A justificativa do cancelamento precisa ter pelo menos {JUSTIFICATIVA_MINIMA} caracteres "
            "(regra da Sefaz) -- explique o motivo com um pouco mais de detalhe."
        )
    if len(limpo) > JUSTIFICATIVA_MAXIMA:
        raise ValueError(f"A justificativa do cancelamento pode ter no máximo {JUSTIFICATIVA_MAXIMA} caracteres.")
    return limpo


def montar_evento(
    *,
    chave_acesso: str,
    protocolo: str,
    justificativa: str,
    ambiente: str,
    momento_utc: datetime | None = None,
    sequencia: int = 1,
) -> str:
    """XML `<evento>` (ainda sem assinatura) de cancelamento da NFC-e."""
    if len(chave_acesso) != 44 or not chave_acesso.isdigit():
        raise ValueError("Chave de acesso inválida para cancelamento (precisa ter 44 dígitos)")
    if not protocolo or not protocolo.strip().isdigit():
        raise ValueError("A nota não tem protocolo de autorização válido -- não dá pra cancelar")
    justificativa = normalizar_justificativa(justificativa)

    momento = ((momento_utc or datetime.utcnow()) + FUSO_BRASILIA).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    tp_amb = "1" if ambiente == "producao" else "2"
    cnpj = chave_acesso[6:20]
    uf = chave_acesso[0:2]
    id_evento = f"ID{TP_EVENTO_CANCELAMENTO}{chave_acesso}{sequencia:02d}"

    return (
        f'<evento xmlns="{NFE_NAMESPACE}" versao="1.00">'
        f'<infEvento Id="{id_evento}">'
        f"<cOrgao>{uf}</cOrgao>"
        f"<tpAmb>{tp_amb}</tpAmb>"
        f"<CNPJ>{cnpj}</CNPJ>"
        f"<chNFe>{chave_acesso}</chNFe>"
        f"<dhEvento>{momento}</dhEvento>"
        f"<tpEvento>{TP_EVENTO_CANCELAMENTO}</tpEvento>"
        f"<nSeqEvento>{sequencia}</nSeqEvento>"
        "<verEvento>1.00</verEvento>"
        '<detEvento versao="1.00">'
        "<descEvento>Cancelamento</descEvento>"
        f"<nProt>{protocolo.strip()}</nProt>"
        f"<xJust>{escape(justificativa)}</xJust>"
        "</detEvento>"
        "</infEvento>"
        "</evento>"
    )


def montar_envio(evento_assinado: str, id_lote: str) -> str:
    """Embrulha o `<evento>` já assinado no `<envEvento>` que o webservice recebe."""
    return (
        f'<envEvento xmlns="{NFE_NAMESPACE}" versao="1.00">'
        f"<idLote>{id_lote}</idLote>"
        f"{evento_assinado}"
        "</envEvento>"
    )

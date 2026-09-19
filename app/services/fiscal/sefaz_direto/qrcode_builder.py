import base64
import hashlib
from io import BytesIO

import qrcode

_VERSAO_QRCODE = "2"
_BASE_URL = "http://www.fazenda.df.gov.br/nfce/qrcode?"

# URL de consulta MANUAL (digitando a chave de acesso), distinta da URL do
# QR Code (`_BASE_URL` acima) -- confirmada contra o DANFE real de uma nota
# emitida em produção pelo sistema anterior da Nana Lanches (mesmo CNPJ),
# que mostra exatamente "Consulte pela Chave de Acesso em:
# www.fazenda.df.gov.br/nfce/consulta". Antes desta correção,
# `montar_url_consulta_chave` devolvia por engano a mesma base do QR Code
# (`/nfce/qrcode`, sem a query string), que é o endpoint errado para
# digitação manual.
_URL_CONSULTA_MANUAL = "http://www.fazenda.df.gov.br/nfce/consulta"


def montar_url_consulta_chave() -> str:
    """URL de consulta manual da NFC-e pela chave de acesso (`urlChave`, o
    outro campo obrigatório de `infNFeSupl` além de `qrCode` -- ver
    Tnfe.InfNfe.Supl na nfelib)."""
    return _URL_CONSULTA_MANUAL


def montar_url_qrcode(chave_acesso: str, ambiente: str, csc_id: str, csc_token: str) -> str:
    """Monta a URL do QR Code da NFC-e (layout versão 2, usado na emissão on-line).

    Formula (chave|versao|tpAmb|cIdToken|hash, hash = SHA-1 maiúsculo dos parâmetros
    concatenados com o token do CSC) confirmada contra a implementação de referência
    da biblioteca sped-nfe (nfephp-org), que cita o Manual de Especificações Técnicas
    do DANFE NFC-e QR Code versão 5.0. Ver relatório da tarefa para detalhes.
    """
    tp_amb = "1" if ambiente == "producao" else "2"
    parametros_sem_hash = f"{chave_acesso}|{_VERSAO_QRCODE}|{tp_amb}|{csc_id}"
    hash_seguranca = hashlib.sha1(f"{parametros_sem_hash}{csc_token}".encode("utf-8")).hexdigest().upper()
    return f"{_BASE_URL}p={parametros_sem_hash}|{hash_seguranca}"


def gerar_imagem_qrcode_base64(url: str) -> str:
    imagem = qrcode.make(url)
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    codificado = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{codificado}"

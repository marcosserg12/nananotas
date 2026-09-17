import base64
import hashlib
from io import BytesIO

import qrcode

_VERSAO_QRCODE = "2"
_BASE_URL = "http://www.fazenda.df.gov.br/nfce/qrcode?"


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

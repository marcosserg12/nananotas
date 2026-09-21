"""Envia o cupom fiscal (DANFE em PDF) por e-mail pro cliente da venda --
usa `smtplib`/`email` da biblioteca padrão (sem dependência nova) contra o
servidor SMTP configurado em `.env` (nomes de variável no padrão Laravel,
`MAIL_*`, por familiaridade de quem mantém o projeto)."""

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.models.nota_fiscal import NotaFiscal
from app.models.venda import Venda
from app.services import danfe_pdf_service


def enviar_nota_por_email(venda: Venda, nota: NotaFiscal) -> None:
    if not settings.mail_host:
        raise ValueError("Envio de e-mail não está configurado (MAIL_HOST ausente no .env)")
    if not venda.cliente or not venda.cliente.email:
        raise ValueError("Este cliente não tem e-mail cadastrado")

    pdf_bytes = danfe_pdf_service.gerar_pdf_danfe(venda, nota)
    numero_nota = nota.numero or venda.numero_orcamento

    mensagem = EmailMessage()
    mensagem["Subject"] = f"Nana Lanches - Nota fiscal nº {numero_nota}"
    remetente_email = settings.mail_from_address or settings.mail_username
    mensagem["From"] = (
        f"{settings.mail_from_name} <{remetente_email}>" if settings.mail_from_name else remetente_email
    )
    mensagem["To"] = venda.cliente.email
    mensagem.set_content(
        f"Olá, {venda.cliente.nome}!\n\n"
        f"Segue em anexo a nota fiscal (cupom) da sua compra na Nana Lanches, "
        f"no valor de R$ {venda.valor_total:.2f}.\n\n"
        "Obrigado pela preferência!"
    )
    mensagem.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"nota-fiscal-{numero_nota}.pdf",
    )

    try:
        # MAIL_ENCRYPTION=ssl -> SSL direto (SMTPS, tipicamente porta 465);
        # qualquer outro valor ("tls", vazio etc.) -> STARTTLS (porta 587 é o
        # padrão mais comum, inclusive do Brevo/Sendinblue).
        if settings.mail_encryption.lower() == "ssl":
            with smtplib.SMTP_SSL(settings.mail_host, settings.mail_port, timeout=20) as servidor:
                if settings.mail_username:
                    servidor.login(settings.mail_username, settings.mail_password)
                servidor.send_message(mensagem)
        else:
            with smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=20) as servidor:
                servidor.starttls()
                if settings.mail_username:
                    servidor.login(settings.mail_username, settings.mail_password)
                servidor.send_message(mensagem)
    except Exception as exc:
        raise ValueError(f"Falha ao enviar e-mail: {exc}") from exc

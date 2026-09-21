from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.services import email_service


class _VendaFalsa:
    def __init__(self, cliente, valor_total=20.0, numero_orcamento=7):
        self.cliente = cliente
        self.valor_total = valor_total
        self.numero_orcamento = numero_orcamento


class _ClienteFalso:
    def __init__(self, nome="Cliente Teste", email=None):
        self.nome = nome
        self.email = email


class _NotaFalsa:
    def __init__(self, numero="10"):
        self.numero = numero


@pytest.fixture()
def mail_configurado(monkeypatch):
    monkeypatch.setattr(settings, "mail_host", "smtp-relay.brevo.com")
    monkeypatch.setattr(settings, "mail_port", 587)
    monkeypatch.setattr(settings, "mail_username", "conta@smtp-brevo.com")
    monkeypatch.setattr(settings, "mail_password", "chave-smtp")
    monkeypatch.setattr(settings, "mail_encryption", "tls")
    monkeypatch.setattr(settings, "mail_from_name", "Nana Lanches")
    monkeypatch.setattr(settings, "mail_from_address", "suporte@exemplo.com")


def test_enviar_sem_mail_configurado_levanta_erro(monkeypatch):
    monkeypatch.setattr(settings, "mail_host", "")
    venda = _VendaFalsa(cliente=_ClienteFalso(email="cliente@exemplo.com"))

    with pytest.raises(ValueError, match="não está configurado"):
        email_service.enviar_nota_por_email(venda, _NotaFalsa())


def test_enviar_sem_email_do_cliente_levanta_erro(mail_configurado):
    venda = _VendaFalsa(cliente=_ClienteFalso(email=None))

    with pytest.raises(ValueError, match="não tem e-mail cadastrado"):
        email_service.enviar_nota_por_email(venda, _NotaFalsa())


def test_enviar_com_sucesso_usa_starttls_quando_encryption_e_tls(mail_configurado, monkeypatch):
    venda = _VendaFalsa(cliente=_ClienteFalso(nome="Maria", email="cliente@exemplo.com"))
    monkeypatch.setattr(email_service.danfe_pdf_service, "gerar_pdf_danfe", lambda v, n: b"%PDF-fake%")

    servidor_falso = MagicMock()
    servidor_falso.__enter__ = MagicMock(return_value=servidor_falso)
    servidor_falso.__exit__ = MagicMock(return_value=False)
    smtp_mock = MagicMock(return_value=servidor_falso)
    monkeypatch.setattr(email_service.smtplib, "SMTP", smtp_mock)

    email_service.enviar_nota_por_email(venda, _NotaFalsa())

    smtp_mock.assert_called_once_with("smtp-relay.brevo.com", 587, timeout=20)
    servidor_falso.starttls.assert_called_once()
    servidor_falso.login.assert_called_once_with("conta@smtp-brevo.com", "chave-smtp")
    assert servidor_falso.send_message.call_count == 1
    mensagem_enviada = servidor_falso.send_message.call_args[0][0]
    assert mensagem_enviada["To"] == "cliente@exemplo.com"
    assert mensagem_enviada["From"] == "Nana Lanches <suporte@exemplo.com>"
    assert "Maria" in mensagem_enviada.get_body(preferencelist=("plain",)).get_content()


def test_enviar_com_sucesso_usa_ssl_direto_quando_encryption_e_ssl(mail_configurado, monkeypatch):
    monkeypatch.setattr(settings, "mail_encryption", "ssl")
    monkeypatch.setattr(settings, "mail_port", 465)
    venda = _VendaFalsa(cliente=_ClienteFalso(email="cliente@exemplo.com"))
    monkeypatch.setattr(email_service.danfe_pdf_service, "gerar_pdf_danfe", lambda v, n: b"%PDF-fake%")

    servidor_falso = MagicMock()
    servidor_falso.__enter__ = MagicMock(return_value=servidor_falso)
    servidor_falso.__exit__ = MagicMock(return_value=False)
    smtp_ssl_mock = MagicMock(return_value=servidor_falso)
    monkeypatch.setattr(email_service.smtplib, "SMTP_SSL", smtp_ssl_mock)

    email_service.enviar_nota_por_email(venda, _NotaFalsa())

    smtp_ssl_mock.assert_called_once_with("smtp-relay.brevo.com", 465, timeout=20)
    servidor_falso.login.assert_called_once()
    servidor_falso.send_message.assert_called_once()


def test_falha_no_envio_vira_valueerror_com_mensagem_clara(mail_configurado, monkeypatch):
    venda = _VendaFalsa(cliente=_ClienteFalso(email="cliente@exemplo.com"))
    monkeypatch.setattr(email_service.danfe_pdf_service, "gerar_pdf_danfe", lambda v, n: b"%PDF-fake%")

    def _smtp_quebrado(*args, **kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _smtp_quebrado)

    with pytest.raises(ValueError, match="Falha ao enviar e-mail"):
        email_service.enviar_nota_por_email(venda, _NotaFalsa())

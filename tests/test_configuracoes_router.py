from pathlib import Path

from app.config import settings
from app.services import certificado_service

CERTIFICADO_TESTE = Path("tests/fixtures/certificado_teste.pfx")
SENHA_TESTE = "senha-teste"


def _isolar_certificado(tmp_path, monkeypatch):
    caminho = tmp_path / "certificado_producao.pfx"
    monkeypatch.setattr(settings, "sefaz_certificado_path", str(caminho))
    monkeypatch.setattr(settings, "sefaz_certificado_senha", "senha-antiga")
    # A troca de verdade do .env é coberta pelos testes de
    # `certificado_service` -- aqui só confirmamos que a rota chama o
    # serviço certo, sem arriscar mexer no `.env` real do projeto.
    monkeypatch.setattr(certificado_service, "_atualizar_senha_no_env", lambda *a, **k: None)
    return caminho


def test_configuracoes_sem_login_redireciona(client):
    response = client.get("/configuracoes", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_configuracoes_mostra_que_nao_ha_certificado(authed_client, tmp_path, monkeypatch):
    _isolar_certificado(tmp_path, monkeypatch)

    response = authed_client.get("/configuracoes")

    assert response.status_code == 200
    assert "Nenhum certificado configurado" in response.text


def test_atualizar_certificado_com_sucesso_redireciona(authed_client, tmp_path, monkeypatch):
    caminho = _isolar_certificado(tmp_path, monkeypatch)

    response = authed_client.post(
        "/configuracoes/certificado",
        files={"arquivo": ("certificado.pfx", CERTIFICADO_TESTE.read_bytes(), "application/x-pkcs12")},
        data={"senha": SENHA_TESTE},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/configuracoes?sucesso=1"
    assert caminho.read_bytes() == CERTIFICADO_TESTE.read_bytes()


def test_atualizar_certificado_com_senha_errada_retorna_400(authed_client, tmp_path, monkeypatch):
    _isolar_certificado(tmp_path, monkeypatch)

    response = authed_client.post(
        "/configuracoes/certificado",
        files={"arquivo": ("certificado.pfx", CERTIFICADO_TESTE.read_bytes(), "application/x-pkcs12")},
        data={"senha": "senha-errada"},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_tela_mostra_link_da_pagina_apos_sucesso(authed_client, tmp_path, monkeypatch):
    _isolar_certificado(tmp_path, monkeypatch)

    response = authed_client.get("/configuracoes", params={"sucesso": "1"})

    assert response.status_code == 200
    assert "atualizado com sucesso" in response.text

from pathlib import Path

import pytest

from app.config import settings
from app.services import certificado_service

CERTIFICADO_TESTE = Path("tests/fixtures/certificado_teste.pfx")
SENHA_TESTE = "senha-teste"


@pytest.fixture()
def caminho_certificado_isolado(tmp_path, monkeypatch):
    """Aponta `settings.sefaz_certificado_path` pra um arquivo temporário,
    nunca pro certificado de verdade do projeto -- sem isso, os testes
    sobrescreveriam o certificado real da Nana Lanches."""
    caminho = tmp_path / "certificado_producao.pfx"
    monkeypatch.setattr(settings, "sefaz_certificado_path", str(caminho))
    monkeypatch.setattr(settings, "sefaz_certificado_senha", "senha-antiga")
    return caminho


def test_info_certificado_atual_quando_nao_existe(caminho_certificado_isolado):
    info = certificado_service.info_certificado_atual()

    assert info["existe"] is False


def test_info_certificado_atual_quando_existe(caminho_certificado_isolado):
    caminho_certificado_isolado.write_bytes(CERTIFICADO_TESTE.read_bytes())

    info = certificado_service.info_certificado_atual()

    assert info["existe"] is True
    assert info["tamanho_kb"] > 0
    assert info["modificado_em"]


def test_substituir_certificado_com_senha_correta_troca_o_arquivo(caminho_certificado_isolado, tmp_path):
    env_falso = tmp_path / ".env"
    env_falso.write_text("SEFAZ_CERTIFICADO_SENHA=senha-antiga\nOUTRA_CHAVE=valor\n", encoding="utf-8")

    certificado_service.substituir_certificado(
        CERTIFICADO_TESTE.read_bytes(), SENHA_TESTE, caminho_env=env_falso
    )

    assert caminho_certificado_isolado.read_bytes() == CERTIFICADO_TESTE.read_bytes()
    assert settings.sefaz_certificado_senha == SENHA_TESTE
    assert "SEFAZ_CERTIFICADO_SENHA=senha-teste" in env_falso.read_text(encoding="utf-8")
    assert "OUTRA_CHAVE=valor" in env_falso.read_text(encoding="utf-8")


def test_substituir_certificado_guarda_backup_do_anterior(caminho_certificado_isolado, tmp_path):
    conteudo_antigo = b"conteudo-do-certificado-anterior"
    caminho_certificado_isolado.write_bytes(conteudo_antigo)
    env_falso = tmp_path / ".env"
    env_falso.write_text("SEFAZ_CERTIFICADO_SENHA=senha-antiga\n", encoding="utf-8")

    certificado_service.substituir_certificado(
        CERTIFICADO_TESTE.read_bytes(), SENHA_TESTE, caminho_env=env_falso
    )

    caminho_backup = caminho_certificado_isolado.with_name(caminho_certificado_isolado.name + ".bak")
    assert caminho_backup.read_bytes() == conteudo_antigo


def test_substituir_certificado_com_senha_errada_nao_mexe_no_arquivo_atual(caminho_certificado_isolado, tmp_path):
    conteudo_antigo = b"conteudo-do-certificado-anterior"
    caminho_certificado_isolado.write_bytes(conteudo_antigo)
    env_falso = tmp_path / ".env"
    env_falso.write_text("SEFAZ_CERTIFICADO_SENHA=senha-antiga\n", encoding="utf-8")

    with pytest.raises(ValueError, match="senha informada"):
        certificado_service.substituir_certificado(
            CERTIFICADO_TESTE.read_bytes(), "senha-errada", caminho_env=env_falso
        )

    assert caminho_certificado_isolado.read_bytes() == conteudo_antigo
    assert settings.sefaz_certificado_senha == "senha-antiga"
    assert "SEFAZ_CERTIFICADO_SENHA=senha-antiga" in env_falso.read_text(encoding="utf-8")


def test_substituir_certificado_sem_arquivo_levanta_erro(caminho_certificado_isolado):
    with pytest.raises(ValueError, match="Nenhum arquivo"):
        certificado_service.substituir_certificado(b"", SENHA_TESTE)


def test_substituir_certificado_nao_deixa_arquivo_temporario_apos_falha(caminho_certificado_isolado):
    with pytest.raises(ValueError):
        certificado_service.substituir_certificado(CERTIFICADO_TESTE.read_bytes(), "senha-errada")

    caminho_temp = caminho_certificado_isolado.with_name(caminho_certificado_isolado.name + ".novo")
    assert not caminho_temp.exists()

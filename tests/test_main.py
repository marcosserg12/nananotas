import pytest

from app.main import verificar_secret_key_configurada


def test_secret_key_padrao_fora_do_pytest_levanta_erro():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        verificar_secret_key_configurada("change-me", sob_pytest=False)


def test_secret_key_padrao_sob_pytest_nao_levanta_erro():
    verificar_secret_key_configurada("change-me", sob_pytest=True)


def test_secret_key_customizada_nao_levanta_erro_mesmo_fora_do_pytest():
    verificar_secret_key_configurada("uma-chave-aleatoria-longa", sob_pytest=False)

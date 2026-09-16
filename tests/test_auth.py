from app.auth import autenticar, hash_senha, verificar_senha
from app.models.usuario import Usuario


def test_hash_e_verificar_senha():
    hash_gerado = hash_senha("segredo123")
    assert hash_gerado != "segredo123"
    assert verificar_senha("segredo123", hash_gerado) is True
    assert verificar_senha("errada", hash_gerado) is False


def test_autenticar_com_credenciais_validas(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "segredo123")

    assert usuario is not None
    assert usuario.username == "pai"


def test_autenticar_com_senha_invalida_retorna_none(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "errada")

    assert usuario is None


def test_autenticar_usuario_inativo_retorna_none(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=False))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "segredo123")

    assert usuario is None

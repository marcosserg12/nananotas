from app.models.usuario import Usuario


def test_criar_usuario(db_session):
    usuario = Usuario(username="pai", senha_hash="hash", ativo=True)
    db_session.add(usuario)
    db_session.commit()

    encontrado = db_session.query(Usuario).filter(Usuario.username == "pai").first()
    assert encontrado is not None
    assert encontrado.ativo is True

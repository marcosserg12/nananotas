from app.models.cliente import Cliente
from app.seed import criar_usuario_admin, seed_inicial


def test_criar_usuario_admin_e_idempotente(db_session):
    usuario1 = criar_usuario_admin(db_session, "pai", "senha123")
    usuario2 = criar_usuario_admin(db_session, "pai", "outrasenha")

    assert usuario1.id == usuario2.id


def test_seed_inicial_cria_admin_e_consumidor_final(db_session):
    seed_inicial(db_session, "pai", "senha123")

    consumidor = db_session.query(Cliente).filter(Cliente.consumidor_final.is_(True)).first()
    assert consumidor is not None
    assert consumidor.nome == "AO CONSUMIDOR"

from app.auth import hash_senha
from app.models.usuario import Usuario


def test_login_com_credenciais_validas_redireciona_para_painel(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    response = client.post("/login", data={"username": "pai", "senha": "segredo123"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_com_senha_invalida_mostra_erro(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    response = client.post("/login", data={"username": "pai", "senha": "errada"})

    assert response.status_code == 401
    assert "inv" in response.text.lower()


def test_rota_protegida_sem_login_redireciona(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_logout_limpa_sessao_e_redireciona(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()
    client.post("/login", data={"username": "pai", "senha": "segredo123"})

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    protegida = client.get("/", follow_redirects=False)
    assert protegida.status_code == 303

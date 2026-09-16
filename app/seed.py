from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models.usuario import Usuario


def criar_usuario_admin(db: Session, username: str, senha: str) -> Usuario:
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return existente
    usuario = Usuario(username=username, senha_hash=hash_senha(senha), ativo=True)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


if __name__ == "__main__":
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        username = input("Usuário admin: ")
        senha = input("Senha: ")
        criar_usuario_admin(db, username, senha)
        print("Usuário criado com sucesso.")
    finally:
        db.close()

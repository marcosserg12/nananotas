from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models.usuario import Usuario
from app.services.clientes_service import garantir_consumidor_final


def criar_usuario_admin(db: Session, username: str, senha: str) -> Usuario:
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return existente
    usuario = Usuario(username=username, senha_hash=hash_senha(senha), ativo=True)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def seed_inicial(db: Session, admin_username: str, admin_senha: str) -> None:
    criar_usuario_admin(db, admin_username, admin_senha)
    garantir_consumidor_final(db)


if __name__ == "__main__":
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        username = input("Usuário admin: ")
        senha = input("Senha: ")
        seed_inicial(db, username, senha)
        print("Dados iniciais criados com sucesso.")
    finally:
        db.close()

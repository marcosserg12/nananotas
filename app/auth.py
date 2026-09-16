from fastapi import Depends, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class NotAuthenticatedError(Exception):
    pass


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def autenticar(db: Session, username: str, senha: str) -> Usuario | None:
    usuario = db.query(Usuario).filter(Usuario.username == username, Usuario.ativo.is_(True)).first()
    if usuario is None or not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    user_id = request.session.get("user_id")
    usuario = db.get(Usuario, user_id) if user_id else None
    if usuario is None:
        raise NotAuthenticatedError()
    return usuario

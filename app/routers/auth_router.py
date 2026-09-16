from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import autenticar
from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    usuario = autenticar(db, username, senha)
    if usuario is None:
        return templates.TemplateResponse(
            "login.html", {"request": request, "erro": "Usuário ou senha inválidos"}, status_code=401
        )
    request.session["user_id"] = usuario.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

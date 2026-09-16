from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.models.usuario import Usuario

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def painel(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "usuario": usuario})

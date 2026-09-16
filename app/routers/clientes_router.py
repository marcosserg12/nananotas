from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.cliente import Cliente, TipoPessoa
from app.models.usuario import Usuario
from app.services import clientes_service

router = APIRouter(prefix="/clientes")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    clientes = clientes_service.listar_clientes(db)
    return templates.TemplateResponse("clientes/list.html", {"request": request, "clientes": clientes})


@router.get("/novo", response_class=HTMLResponse)
def novo_form(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("clientes/form.html", {"request": request, "cliente": None})


@router.post("/novo")
def criar(
    tipo_pessoa: str = Form(...),
    nome: str = Form(...),
    cpf_cnpj: str = Form(""),
    ie: str = Form(""),
    endereco: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    clientes_service.criar_cliente(
        db,
        tipo_pessoa=TipoPessoa(tipo_pessoa),
        nome=nome,
        cpf_cnpj=cpf_cnpj or None,
        ie=ie or None,
        endereco=endereco or None,
        telefone=telefone or None,
        email=email or None,
    )
    return RedirectResponse(url="/clientes", status_code=303)


@router.get("/{cliente_id}/editar", response_class=HTMLResponse)
def editar_form(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if cliente.consumidor_final:
        raise HTTPException(status_code=400, detail="Cliente padrão Consumidor Final não pode ser editado")
    return templates.TemplateResponse("clientes/form.html", {"request": request, "cliente": cliente})


@router.post("/{cliente_id}/editar")
def editar(
    cliente_id: int,
    tipo_pessoa: str = Form(...),
    nome: str = Form(...),
    cpf_cnpj: str = Form(""),
    ie: str = Form(""),
    endereco: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if cliente.consumidor_final:
        raise HTTPException(status_code=400, detail="Cliente padrão Consumidor Final não pode ser editado")
    clientes_service.atualizar_cliente(
        db,
        cliente_id,
        tipo_pessoa=TipoPessoa(tipo_pessoa),
        nome=nome,
        cpf_cnpj=cpf_cnpj or None,
        ie=ie or None,
        endereco=endereco or None,
        telefone=telefone or None,
        email=email or None,
    )
    return RedirectResponse(url="/clientes", status_code=303)


@router.get("/buscar", response_class=HTMLResponse)
def buscar(
    request: Request,
    termo: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    clientes = clientes_service.buscar_clientes(db, termo) if termo else []
    return templates.TemplateResponse("clientes/_resultado_busca.html", {"request": request, "clientes": clientes})

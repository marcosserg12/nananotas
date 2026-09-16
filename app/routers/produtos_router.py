from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.usuario import Usuario
from app.services import produtos_service

router = APIRouter(prefix="/produtos")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    grupos = produtos_service.listar_produtos_por_categoria(db)
    return templates.TemplateResponse("produtos/list.html", {"request": request, "grupos": grupos})


@router.get("/novo", response_class=HTMLResponse)
def novo_form(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("produtos/form.html", {"request": request})


@router.post("/novo")
def criar(
    codigo_interno: str = Form(...),
    nome: str = Form(...),
    categoria_nome: str = Form(...),
    ncm: str = Form(...),
    unidade: str = Form("UN"),
    preco_venda: str = Form(...),
    codigo_fabricante: str = Form(""),
    preco_custo: str = Form("0"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    produtos_service.criar_produto(
        db,
        codigo_interno=codigo_interno,
        nome=nome,
        categoria_nome=categoria_nome,
        ncm=ncm,
        unidade=unidade,
        preco_venda=Decimal(preco_venda),
        codigo_fabricante=codigo_fabricante or None,
        preco_custo=Decimal(preco_custo or "0"),
    )
    return RedirectResponse(url="/produtos", status_code=303)


@router.post("/{produto_id}/alternar-ativo")
def alternar_ativo(produto_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    produtos_service.alternar_ativo(db, produto_id)
    return RedirectResponse(url="/produtos", status_code=303)


@router.get("/buscar", response_class=HTMLResponse)
def buscar(
    request: Request,
    termo: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    produtos = produtos_service.buscar_produtos(db, termo) if termo else []
    return templates.TemplateResponse("produtos/_resultado_busca.html", {"request": request, "produtos": produtos})

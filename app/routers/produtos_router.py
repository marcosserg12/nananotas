from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.dinheiro import parse_reais
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.services import produtos_service

router = APIRouter(prefix="/produtos")
templates = Jinja2Templates(directory="app/templates")


def _config_gerador_do_form(
    gerador_ativo: str, gerador_chance: str, gerador_preco_min: str, gerador_preco_max: str
) -> dict:
    try:
        chance = int((gerador_chance or "100").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Chance de aparecer inválida")
    try:
        preco_min = parse_reais(gerador_preco_min) if gerador_preco_min.strip() else None
        preco_max = parse_reais(gerador_preco_max) if gerador_preco_max.strip() else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Preço do gerador: {exc}")
    return {
        "gerador_ativo": gerador_ativo.strip().lower() in ("on", "true", "1", "sim"),
        "gerador_chance": chance,
        "gerador_preco_min": preco_min,
        "gerador_preco_max": preco_max,
    }


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    grupos = produtos_service.listar_produtos_por_categoria(db)
    return templates.TemplateResponse("produtos/list.html", {"request": request, "grupos": grupos})


@router.get("/novo", response_class=HTMLResponse)
def novo_form(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("produtos/form.html", {"request": request, "produto": None})


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
    estoque_atual: str = Form("0"),
    gerador_ativo: str = Form(""),
    gerador_chance: str = Form("100"),
    gerador_preco_min: str = Form(""),
    gerador_preco_max: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    config_gerador = _config_gerador_do_form(gerador_ativo, gerador_chance, gerador_preco_min, gerador_preco_max)
    try:
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
            estoque_atual=Decimal(estoque_atual or "0"),
            **config_gerador,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/produtos", status_code=303)


@router.get("/{produto_id}/editar", response_class=HTMLResponse)
def editar_form(
    produto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return templates.TemplateResponse("produtos/form.html", {"request": request, "produto": produto})


@router.post("/{produto_id}/editar")
def editar(
    produto_id: int,
    codigo_interno: str = Form(...),
    nome: str = Form(...),
    categoria_nome: str = Form(...),
    ncm: str = Form(...),
    unidade: str = Form("UN"),
    preco_venda: str = Form(...),
    codigo_fabricante: str = Form(""),
    preco_custo: str = Form("0"),
    estoque_atual: str = Form("0"),
    gerador_ativo: str = Form(""),
    gerador_chance: str = Form("100"),
    gerador_preco_min: str = Form(""),
    gerador_preco_max: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    config_gerador = _config_gerador_do_form(gerador_ativo, gerador_chance, gerador_preco_min, gerador_preco_max)
    categoria = produtos_service.obter_ou_criar_categoria(db, categoria_nome)
    try:
        produtos_service.atualizar_produto(
            db,
            produto_id,
            codigo_interno=codigo_interno,
            nome=nome,
            categoria_id=categoria.id,
            ncm=ncm,
            unidade=unidade,
            preco_venda=Decimal(preco_venda),
            codigo_fabricante=codigo_fabricante or None,
            preco_custo=Decimal(preco_custo or "0"),
            estoque_atual=Decimal(estoque_atual or "0"),
            **config_gerador,
        )
    except ValueError as exc:
        status = 404 if str(exc) == "Produto não encontrado" else 400
        raise HTTPException(status_code=status, detail=str(exc))
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
    return templates.TemplateResponse(
        "produtos/_resultado_busca.html", {"request": request, "produtos": produtos, "termo": termo}
    )

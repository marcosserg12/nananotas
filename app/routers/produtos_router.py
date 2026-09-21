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


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    grupos = produtos_service.listar_produtos_por_categoria(db)
    return templates.TemplateResponse("produtos/list.html", {"request": request, "grupos": grupos})


def _linhas_do_gerador(produtos: list[Produto], digitado: dict[int, dict] | None = None) -> list[dict]:
    """Uma linha por produto pra tela do gerador: o que a pessoa acabou de
    digitar (quando a gravação falhou e a tela volta com o erro) ou, senão, o
    que está salvo no banco."""
    linhas = []
    for produto in produtos:
        if digitado and produto.id in digitado:
            valores = digitado[produto.id]
        else:
            valores = {
                "chance": str(produto.gerador_chance),
                "preco_min": f"{produto.gerador_preco_min:.2f}" if produto.gerador_preco_min is not None else "",
                "preco_max": f"{produto.gerador_preco_max:.2f}" if produto.gerador_preco_max is not None else "",
            }
        linhas.append({"produto": produto, **valores})
    return linhas


@router.get("/gerador", response_class=HTMLResponse)
def gerador_form(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    produtos = produtos_service.listar_produtos_ativos(db)
    return templates.TemplateResponse(
        "produtos/gerador.html", {"request": request, "linhas": _linhas_do_gerador(produtos), "erro": None}
    )


@router.post("/gerador")
async def gerador_salvar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    dados = await request.form()
    produtos = produtos_service.listar_produtos_ativos(db)
    digitado: dict[int, dict] = {}
    configs: list[dict] = []
    erro: str | None = None

    for produto in produtos:
        bruto = {
            "chance": str(dados.get(f"chance_{produto.id}", "")).strip(),
            "preco_min": str(dados.get(f"min_{produto.id}", "")).strip(),
            "preco_max": str(dados.get(f"max_{produto.id}", "")).strip(),
        }
        digitado[produto.id] = bruto
        if erro:
            continue
        try:
            chance = int(bruto["chance"] or "100")
        except ValueError:
            erro = f"{produto.nome}: chance inválida (use um número inteiro de 1 a 100)"
            continue
        try:
            configs.append(
                {
                    "produto_id": produto.id,
                    "chance": chance,
                    "preco_min": parse_reais(bruto["preco_min"]) if bruto["preco_min"] else None,
                    "preco_max": parse_reais(bruto["preco_max"]) if bruto["preco_max"] else None,
                }
            )
        except ValueError as exc:
            erro = f"{produto.nome}: {exc}"

    if erro is None:
        try:
            produtos_service.salvar_config_gerador(db, configs)
        except ValueError as exc:
            erro = str(exc)

    if erro is not None:
        return templates.TemplateResponse(
            "produtos/gerador.html",
            {"request": request, "linhas": _linhas_do_gerador(produtos, digitado), "erro": erro},
            status_code=400,
        )
    return RedirectResponse(url="/produtos/gerador?salvo=1", status_code=303)


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
        estoque_atual=Decimal(estoque_atual or "0"),
    )
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
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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

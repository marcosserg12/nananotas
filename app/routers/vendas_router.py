from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.usuario import Usuario
from app.models.venda import StatusVenda, Venda, VendaItem
from app.services import clientes_service, parcelas_service, vendas_service

router = APIRouter(prefix="/vendas")
templates = Jinja2Templates(directory="app/templates")


@router.get("/nova", response_class=HTMLResponse)
def nova_form(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    cliente_padrao = clientes_service.garantir_consumidor_final(db)
    return templates.TemplateResponse("vendas/nova.html", {"request": request, "cliente_padrao": cliente_padrao})


@router.post("/nova")
def criar(cliente_id: int = Form(...), db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = vendas_service.criar_venda(db, cliente_id)
    return RedirectResponse(url=f"/vendas/{venda.id}", status_code=303)


@router.get("/{venda_id}", response_class=HTMLResponse)
def detalhe(venda_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/detalhe.html", {"request": request, "venda": venda})


@router.post("/{venda_id}/itens", response_class=HTMLResponse)
def adicionar_item(
    venda_id: int,
    request: Request,
    produto_id: str = Form(""),
    quantidade: str = Form("1"),
    preco_unitario: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    # `produto_id` só é preenchido quando o vendedor clica num resultado da
    # busca (ver produtos/_resultado_busca.html); submeter o formulário sem
    # selecionar nada manda esse campo em branco. Antes disso era declarado
    # como `int` direto no Form, e o FastAPI recusava com um 422 cru (sem
    # mensagem em português) antes mesmo de chegar aqui -- agora tratamos
    # como um erro de validação normal, igual quantidade/preço.
    if not produto_id.strip():
        raise HTTPException(status_code=400, detail="Selecione um produto na busca antes de adicionar")
    try:
        produto_id_int = int(produto_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Produto inválido")

    try:
        quantidade_decimal = Decimal(quantidade)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Quantidade inválida")

    preco_unitario_decimal = None
    if preco_unitario:
        try:
            preco_unitario_decimal = Decimal(preco_unitario)
        except InvalidOperation:
            raise HTTPException(status_code=400, detail="Preço inválido")

    try:
        vendas_service.adicionar_item(db, venda_id, produto_id_int, quantidade_decimal, preco_unitario_decimal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/_itens.html", {"request": request, "venda": venda})


@router.post("/itens/{item_id}/remover", response_class=HTMLResponse)
def remover_item(item_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    item = db.get(VendaItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    venda_id = item.venda_id
    vendas_service.remover_item(db, item_id)
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/_itens.html", {"request": request, "venda": venda})


@router.get("/{venda_id}/pagamento", response_class=HTMLResponse)
def pagamento_form(venda_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/pagamento.html", {"request": request, "venda": venda})


@router.post("/{venda_id}/pagamento")
def confirmar_pagamento(
    venda_id: int,
    forma_pagamento: str = Form(...),
    numero_parcelas: int = Form(1),
    valor_pago: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        valor_pago_decimal = Decimal(valor_pago)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Valor pago inválido")

    venda = db.get(Venda, venda_id)
    if venda is None:
        raise HTTPException(status_code=400, detail="Venda não encontrada")
    if venda.status != StatusVenda.ORCAMENTO:
        raise HTTPException(status_code=400, detail="Venda já foi confirmada ou cancelada")

    try:
        parcelas_service.gerar_parcelas(db, venda_id, forma_pagamento, numero_parcelas)
        parcelas_service.confirmar_venda(db, venda_id, valor_pago_decimal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)

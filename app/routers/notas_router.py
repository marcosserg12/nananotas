from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.models.nota_fiscal import NotaFiscal
from app.models.parcela import Parcela
from app.models.usuario import Usuario
from app.models.venda import Venda
from app.services import notas_service
from app.services.fiscal.base import FiscalProvider

router = APIRouter(prefix="/vendas")
templates = Jinja2Templates(directory="app/templates")


@router.get("/{venda_id}/nota", response_class=HTMLResponse)
def ver_nota(venda_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    parcelas = db.query(Parcela).filter(Parcela.venda_id == venda_id).order_by(Parcela.numero).all()
    return templates.TemplateResponse(
        "vendas/nota.html", {"request": request, "venda": venda, "nota": nota, "parcelas": parcelas}
    )


@router.post("/{venda_id}/nota/emitir")
def emitir(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    try:
        notas_service.emitir_nota(db, venda_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)


@router.post("/{venda_id}/nota/consultar")
def consultar(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    try:
        notas_service.consultar_nota(db, venda_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)


@router.post("/{venda_id}/nota/cancelar")
def cancelar(
    venda_id: int,
    motivo: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    try:
        notas_service.cancelar_nota(db, venda_id, motivo, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)

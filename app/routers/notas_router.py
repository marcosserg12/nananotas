from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.constants import BANDEIRAS_CARTAO, FORMAS_PAGAMENTO_LABELS
from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.models.nota_fiscal import NotaFiscal
from app.models.parcela import Parcela
from app.models.usuario import Usuario
from app.models.venda import Venda
from app.services import danfe_pdf_service, notas_service, vendas_service
from app.services.fiscal.base import FiscalProvider

router = APIRouter(prefix="/vendas")
templates = Jinja2Templates(directory="app/templates")


@router.get("/notas", response_class=HTMLResponse)
def listar_notas(
    request: Request,
    cliente: str = "",
    data: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    data_filtro = None
    if data:
        try:
            data_filtro = datetime.strptime(data, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Data inválida")

    notas = notas_service.listar_notas(db, cliente=cliente or None, data=data_filtro)
    return templates.TemplateResponse(
        "vendas/notas_list.html",
        {
            "request": request,
            "notas": notas,
            "formatar_data_hora_local": notas_service.formatar_data_hora_local,
            "filtro_cliente": cliente,
            "filtro_data": data,
        },
    )


@router.get("/{venda_id}/nota", response_class=HTMLResponse)
def ver_nota(venda_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    parcelas = db.query(Parcela).filter(Parcela.venda_id == venda_id).order_by(Parcela.numero).all()
    return templates.TemplateResponse(
        "vendas/nota.html",
        {
            "request": request,
            "venda": venda,
            "nota": nota,
            "parcelas": parcelas,
            "bandeiras": BANDEIRAS_CARTAO,
            "formas_pagamento": FORMAS_PAGAMENTO_LABELS,
            "formatar_data_hora_local": notas_service.formatar_data_hora_local,
            "formatar_quantidade": vendas_service.formatar_quantidade,
        },
    )


@router.post("/{venda_id}/nota/emitir")
def emitir(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    try:
        nota = notas_service.emitir_nota(db, venda_id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        # Melhor esforço: cliente sem e-mail cadastrado, SMTP não configurado
        # ou uma falha de envio não podem derrubar a emissão, que já teve
        # sucesso -- quem quiser garantir o envio usa o botão de reenviar,
        # que já mostra o motivo da falha.
        notas_service.enviar_email_nota(db, venda_id)
    except ValueError:
        pass
    # `?emitido=1` só quando saiu um cupom de verdade pra abrir (nota
    # autorizada com DANFE) -- nota.html usa isso pra abrir o cupom numa
    # segunda aba automaticamente, sem precisar clicar em "Imprimir cupom"
    # depois. Numa rejeição não tem cupom nenhum pra abrir.
    sufixo = "?emitido=1" if nota.url_danfe else ""
    return RedirectResponse(url=f"/vendas/{venda_id}/nota{sufixo}", status_code=303)


@router.post("/{venda_id}/nota/reenviar-email")
def reenviar_email(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        notas_service.enviar_email_nota(db, venda_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota?email_enviado=1", status_code=303)


@router.post("/{venda_id}/nota/marcar-manual")
def marcar_manual(
    venda_id: int,
    chave_acesso: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        notas_service.marcar_nota_emitida_manualmente(db, venda_id, chave_acesso or None)
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


@router.get("/{venda_id}/nota/danfe")
def ver_danfe(venda_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    venda = db.get(Venda, venda_id)
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None or not nota.chave_acesso:
        raise HTTPException(status_code=404, detail="Nota fiscal ainda não autorizada")

    pdf_bytes = danfe_pdf_service.gerar_pdf_danfe(venda, nota)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="danfe-nfce-{nota.numero or venda.numero_orcamento}.pdf"'},
    )


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

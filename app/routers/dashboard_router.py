import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.usuario import Usuario
from app.services import dashboard_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def painel(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    vendas = dashboard_service.vendas_do_dia(db)
    total = dashboard_service.total_vendido_no_dia(db)
    for venda in vendas:
        venda.hora_local = dashboard_service.formatar_hora_local(venda.data_venda)

    semana = dashboard_service.vendas_por_dia_semana(db)
    meses = dashboard_service.vendas_por_mes(db)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "usuario": usuario,
            "vendas": vendas,
            "total": total,
            "grafico_semana_json": json.dumps(semana),
            "grafico_meses_json": json.dumps(meses),
        },
    )

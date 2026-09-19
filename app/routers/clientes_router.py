from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.cliente import Cliente, TipoPessoa
from app.models.usuario import Usuario
from app.services import clientes_service, cnpj_lookup_service

router = APIRouter(prefix="/clientes")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    clientes = clientes_service.listar_clientes(db)
    return templates.TemplateResponse("clientes/list.html", {"request": request, "clientes": clientes})


def _voltar_seguro(voltar: str) -> str:
    """Só aceita caminhos relativos internos (ex: "/vendas/nova") como
    destino de redirecionamento pós-cadastro -- nunca uma URL absoluta, para
    não abrir um redirecionamento para fora do sistema a partir de um
    parâmetro de query controlado pelo navegador do usuário."""
    if voltar.startswith("/") and not voltar.startswith("//"):
        return voltar
    return ""


@router.get("/novo", response_class=HTMLResponse)
def novo_form(
    request: Request,
    nome: str = "",
    voltar: str = "",
    usuario: Usuario = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "clientes/form.html",
        {"request": request, "cliente": None, "nome_sugerido": nome, "voltar": _voltar_seguro(voltar)},
    )


@router.post("/novo")
def criar(
    tipo_pessoa: str = Form(...),
    nome: str = Form(...),
    cpf_cnpj: str = Form(""),
    ie: str = Form(""),
    tipo_inscricao_estadual: str = Form(""),
    endereco_cep: str = Form(""),
    endereco_logradouro: str = Form(""),
    endereco_numero: str = Form(""),
    endereco_complemento: str = Form(""),
    endereco_bairro: str = Form(""),
    endereco_cidade: str = Form(""),
    endereco_uf: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    voltar: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    cliente = clientes_service.criar_cliente(
        db,
        tipo_pessoa=TipoPessoa(tipo_pessoa),
        nome=nome,
        cpf_cnpj=cpf_cnpj or None,
        ie=ie or None,
        tipo_inscricao_estadual=tipo_inscricao_estadual or None,
        endereco_cep=endereco_cep or None,
        endereco_logradouro=endereco_logradouro or None,
        endereco_numero=endereco_numero or None,
        endereco_complemento=endereco_complemento or None,
        endereco_bairro=endereco_bairro or None,
        endereco_cidade=endereco_cidade or None,
        endereco_uf=endereco_uf or None,
        telefone=telefone or None,
        email=email or None,
    )
    voltar_seguro = _voltar_seguro(voltar)
    if voltar_seguro:
        return RedirectResponse(url=f"{voltar_seguro}?cliente_id={cliente.id}", status_code=303)
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
    tipo_inscricao_estadual: str = Form(""),
    endereco_cep: str = Form(""),
    endereco_logradouro: str = Form(""),
    endereco_numero: str = Form(""),
    endereco_complemento: str = Form(""),
    endereco_bairro: str = Form(""),
    endereco_cidade: str = Form(""),
    endereco_uf: str = Form(""),
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
        tipo_inscricao_estadual=tipo_inscricao_estadual or None,
        endereco_cep=endereco_cep or None,
        endereco_logradouro=endereco_logradouro or None,
        endereco_numero=endereco_numero or None,
        endereco_complemento=endereco_complemento or None,
        endereco_bairro=endereco_bairro or None,
        endereco_cidade=endereco_cidade or None,
        endereco_uf=endereco_uf or None,
        telefone=telefone or None,
        email=email or None,
    )
    return RedirectResponse(url="/clientes", status_code=303)


@router.get("/buscar-cnpj")
def buscar_cnpj(cnpj: str, usuario: Usuario = Depends(get_current_user)):
    try:
        dados = cnpj_lookup_service.buscar_dados_cnpj(cnpj)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return dados


@router.get("/buscar", response_class=HTMLResponse)
def buscar(
    request: Request,
    termo: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    clientes = clientes_service.buscar_clientes(db, termo) if termo else []
    return templates.TemplateResponse(
        "clientes/_resultado_busca.html", {"request": request, "clientes": clientes, "termo": termo}
    )

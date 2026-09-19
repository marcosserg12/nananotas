from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.models.usuario import Usuario
from app.services import certificado_service

router = APIRouter(prefix="/configuracoes")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def index(request: Request, usuario: Usuario = Depends(get_current_user)):
    certificado = certificado_service.info_certificado_atual()
    return templates.TemplateResponse("configuracoes/index.html", {"request": request, "certificado": certificado})


@router.post("/certificado")
def atualizar_certificado(
    arquivo: UploadFile = File(...),
    senha: str = Form(...),
    usuario: Usuario = Depends(get_current_user),
):
    conteudo = arquivo.file.read()
    try:
        certificado_service.substituir_certificado(conteudo, senha)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/configuracoes?sucesso=1", status_code=303)


@router.get("/certificado/baixar")
def baixar_certificado(usuario: Usuario = Depends(get_current_user)):
    try:
        caminho = certificado_service.caminho_certificado_para_download()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(caminho, media_type="application/x-pkcs12", filename=caminho.name)

import sys

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.auth import NotAuthenticatedError
from app.config import settings
from app.routers import (
    auth_router,
    clientes_router,
    dashboard_router,
    notas_router,
    produtos_router,
    vendas_router,
)

app = FastAPI(title="Nana Lanches")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)


def verificar_secret_key_configurada(secret_key: str, sob_pytest: bool) -> None:
    """Recusa iniciar com a SECRET_KEY padrão fora do ambiente de testes.

    Sem isso, uma implantação sem `.env` (ou sem `SECRET_KEY` definido nele)
    assinaria os cookies de sessão com um valor publicamente conhecido,
    permitindo forjar sessões autenticadas. A checagem é pulada sob pytest
    porque o ambiente de testes não possui (nem precisa de) um `.env`.
    """
    if secret_key == "change-me" and not sob_pytest:
        raise RuntimeError(
            "SECRET_KEY não configurado — defina uma chave aleatória em .env "
            "antes de rodar em produção."
        )


verificar_secret_key_configurada(settings.secret_key, "pytest" in sys.modules)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(produtos_router.router)
app.include_router(clientes_router.router)
app.include_router(vendas_router.router)
app.include_router(notas_router.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedError):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}

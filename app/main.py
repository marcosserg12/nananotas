from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.auth import NotAuthenticatedError
from app.config import settings
from app.routers import auth_router, clientes_router, dashboard_router, produtos_router, vendas_router

app = FastAPI(title="Nana Lanches")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(produtos_router.router)
app.include_router(clientes_router.router)
app.include_router(vendas_router.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedError):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}

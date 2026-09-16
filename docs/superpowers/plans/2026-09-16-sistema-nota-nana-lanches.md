# Sistema Nana Lanches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python web system for Nana Lanches that manages products, customers, sales/payments, and emits legally valid NFC-e fiscal notes through the Focus NFe API.

**Architecture:** FastAPI backend + SQLAlchemy ORM + MySQL database, server-rendered Jinja2 templates with HTMX for dynamic interactions and Tailwind CSS (via CDN) for a responsive UI. Fiscal emission goes through a `FiscalProvider` abstraction with a `FocusNFeProvider` implementation, so the provider can be swapped later without touching the rest of the app.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, PyMySQL, pydantic-settings, passlib[bcrypt], Jinja2, HTMX (CDN), Tailwind CSS (CDN), httpx, pytest, respx.

**Spec:** `docs/superpowers/specs/2026-09-16-sistema-nota-nana-lanches-design.md`

## Global Constraints

- Python 3.12+ only; all commands in this plan run from the project root (`c:/laragon/www/sistema_nota_pai`).
- Database: MySQL on `SEU_SERVIDOR_MYSQL:3306`, database `nana_lanches`, user `nana_lanches_user` — created during Task 11, credentials only ever live in a local `.env` (never committed, never hardcoded).
- All automated tests run against an in-memory SQLite database (see `tests/conftest.py` in Task 2) — no test may require network access to the real MySQL server or to Focus NFe.
- All user-facing text (labels, buttons, messages) is in Portuguese (pt-BR), matching the reference system the user's father currently uses.
- No local static asset build step: Tailwind CSS and HTMX are loaded from CDN `<script>` tags in `app/templates/base.html`.
- Every task must leave `pytest` green before moving to the next task.

---

### Task 1: Project scaffold & health check

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/database.py`
- Create: `app/main.py`
- Test: `tests/test_config.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: `app.config.settings` (a `Settings` instance with `.database_url` property), `app.database.Base`, `app.database.engine`, `app.database.SessionLocal`, `app.database.get_db()` generator, `app.main.app` (FastAPI instance).

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
sqlalchemy==2.0.35
alembic==1.13.3
pymysql==1.1.1
pydantic-settings==2.5.2
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0
jinja2==3.1.4
python-multipart==0.0.12
httpx==0.27.2
pytest==8.3.3
respx==0.21.1
```

- [ ] **Step 2: Create `.env.example`**

```
DB_CONNECTION=mysql
DB_HOST=SEU_SERVIDOR_MYSQL
DB_PORT=3306
DB_DATABASE=nana_lanches
DB_USERNAME=nana_lanches_user
DB_PASSWORD=
SECRET_KEY=change-me-to-a-random-string
FOCUS_NFE_TOKEN=
FOCUS_NFE_AMBIENTE=homologacao
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.venv/
venv/
*.db
.pytest_cache/
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`

- [ ] **Step 5: Write failing test for config**

`tests/test_config.py`:

```python
from app.config import Settings


def test_database_url_built_from_parts():
    settings = Settings(
        db_host="example.com",
        db_port=3306,
        db_database="testdb",
        db_username="user",
        db_password="secret",
    )
    assert settings.database_url == "mysql+pymysql://user:secret@example.com:3306/testdb"
```

- [ ] **Step 6: Write failing test for health endpoint**

`tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_config.py tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 8: Create `app/__init__.py`**

Empty file.

- [ ] **Step 9: Create `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_connection: str = "mysql"
    db_host: str = "localhost"
    db_port: int = 3306
    db_database: str = "nana_lanches"
    db_username: str = "nana_lanches_user"
    db_password: str = ""
    secret_key: str = "change-me"
    focus_nfe_token: str = ""
    focus_nfe_ambiente: str = "homologacao"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_database}"
        )


settings = Settings()
```

- [ ] **Step 10: Create `app/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 11: Create `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Nana Lanches")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_health.py -v`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add requirements.txt .env.example .gitignore app tests
git commit -m "feat: project scaffold with config, database setup, and health check"
```

---

### Task 2: Database test infrastructure + Usuario model

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/usuario.py`
- Create: `tests/conftest.py`
- Test: `tests/test_usuario_model.py`

**Interfaces:**
- Consumes: `app.database.Base`, `app.database.get_db`, `app.main.app` (Task 1).
- Produces: `app.models.Usuario` (columns: `id`, `username`, `senha_hash`, `ativo`), pytest fixtures `db_session` and `client` available to every subsequent test file automatically via `conftest.py`.

- [ ] **Step 1: Write failing test for the Usuario model**

`tests/test_usuario_model.py`:

```python
from app.models.usuario import Usuario


def test_criar_usuario(db_session):
    usuario = Usuario(username="pai", senha_hash="hash", ativo=True)
    db_session.add(usuario)
    db_session.commit()

    encontrado = db_session.query(Usuario).filter(Usuario.username == "pai").first()
    assert encontrado is not None
    assert encontrado.ativo is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_usuario_model.py -v`
Expected: FAIL — `db_session` fixture not found / `app.models.usuario` module not found.

- [ ] **Step 3: Create `app/models/usuario.py`**

```python
from sqlalchemy import Boolean, Column, Integer, String

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    ativo = Column(Boolean, nullable=False, default=True)
```

- [ ] **Step 4: Create `app/models/__init__.py`**

```python
from app.models.usuario import Usuario

__all__ = ["Usuario"]
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 -- registers all models on Base.metadata
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_usuario_model.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/models tests/conftest.py tests/test_usuario_model.py
git commit -m "feat: add Usuario model and shared SQLite test fixtures"
```

---

### Task 3: Authentication (login/logout) + base layout

**Files:**
- Create: `app/auth.py`
- Create: `app/seed.py`
- Create: `app/routers/__init__.py`
- Create: `app/routers/auth_router.py`
- Create: `app/routers/dashboard_router.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/templates/dashboard.html`
- Modify: `app/main.py`
- Test: `tests/test_auth.py`
- Test: `tests/test_auth_router.py`

**Interfaces:**
- Consumes: `app.models.usuario.Usuario`, `db_session`/`client` fixtures (Task 2).
- Produces: `app.auth.hash_senha(senha) -> str`, `app.auth.verificar_senha(senha, hash) -> bool`, `app.auth.autenticar(db, username, senha) -> Usuario | None`, `app.auth.get_current_user(request, db) -> Usuario` (raises `app.auth.NotAuthenticatedError`), `app.seed.criar_usuario_admin(db, username, senha) -> Usuario`. Protected route `GET /` (dashboard placeholder). Routes `GET/POST /login`, `POST /logout`.

- [ ] **Step 1: Write failing tests for password hashing and authentication**

`tests/test_auth.py`:

```python
from app.auth import autenticar, hash_senha, verificar_senha
from app.models.usuario import Usuario


def test_hash_e_verificar_senha():
    hash_gerado = hash_senha("segredo123")
    assert hash_gerado != "segredo123"
    assert verificar_senha("segredo123", hash_gerado) is True
    assert verificar_senha("errada", hash_gerado) is False


def test_autenticar_com_credenciais_validas(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "segredo123")

    assert usuario is not None
    assert usuario.username == "pai"


def test_autenticar_com_senha_invalida_retorna_none(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "errada")

    assert usuario is None


def test_autenticar_usuario_inativo_retorna_none(db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=False))
    db_session.commit()

    usuario = autenticar(db_session, "pai", "segredo123")

    assert usuario is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL — `app.auth` module not found.

- [ ] **Step 3: Create `app/auth.py`**

```python
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.usuario import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class NotAuthenticatedError(Exception):
    pass


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def autenticar(db: Session, username: str, senha: str) -> Usuario | None:
    usuario = db.query(Usuario).filter(Usuario.username == username, Usuario.ativo.is_(True)).first()
    if usuario is None or not verificar_senha(senha, usuario.senha_hash):
        return None
    return usuario


def get_current_user(request, db: Session) -> Usuario:
    user_id = request.session.get("user_id")
    usuario = db.get(Usuario, user_id) if user_id else None
    if usuario is None:
        raise NotAuthenticatedError()
    return usuario
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 5: Wire `get_current_user` as a real FastAPI dependency**

Replace the plain function signature in `app/auth.py` with FastAPI-injectable parameters. Modify the last function in `app/auth.py` to:

```python
from fastapi import Depends, Request

from app.database import get_db


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    user_id = request.session.get("user_id")
    usuario = db.get(Usuario, user_id) if user_id else None
    if usuario is None:
        raise NotAuthenticatedError()
    return usuario
```

Add `from fastapi import Depends, Request` and `from app.database import get_db` to the top imports of `app/auth.py` (alongside the existing imports).

- [ ] **Step 6: Write failing router tests**

`tests/test_auth_router.py`:

```python
from app.auth import hash_senha
from app.models.usuario import Usuario


def test_login_com_credenciais_validas_redireciona_para_painel(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    response = client.post("/login", data={"username": "pai", "senha": "segredo123"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_com_senha_invalida_mostra_erro(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()

    response = client.post("/login", data={"username": "pai", "senha": "errada"})

    assert response.status_code == 401
    assert "inv" in response.text.lower()


def test_rota_protegida_sem_login_redireciona(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_logout_limpa_sessao_e_redireciona(client, db_session):
    db_session.add(Usuario(username="pai", senha_hash=hash_senha("segredo123"), ativo=True))
    db_session.commit()
    client.post("/login", data={"username": "pai", "senha": "segredo123"})

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

    protegida = client.get("/", follow_redirects=False)
    assert protegida.status_code == 303
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_auth_router.py -v`
Expected: FAIL — no routers, no `/` route registered yet.

- [ ] **Step 8: Create `app/routers/__init__.py`**

Empty file.

- [ ] **Step 9: Create `app/routers/auth_router.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import autenticar
from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    usuario = autenticar(db, username, senha)
    if usuario is None:
        return templates.TemplateResponse(
            "login.html", {"request": request, "erro": "Usuário ou senha inválidos"}, status_code=401
        )
    request.session["user_id"] = usuario.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
```

- [ ] **Step 10: Create `app/routers/dashboard_router.py`**

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.models.usuario import Usuario

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def painel(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "usuario": usuario})
```

- [ ] **Step 11: Create `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Nana Lanches{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 text-gray-900">
    {% if request.session.get("user_id") %}
    <nav class="bg-slate-800 text-white px-4 py-3 flex flex-wrap gap-4 items-center">
        <span class="font-bold">Nana Lanches</span>
        <a href="/" class="hover:underline">Painel</a>
        <a href="/produtos" class="hover:underline">Produtos</a>
        <a href="/clientes" class="hover:underline">Clientes</a>
        <a href="/vendas/nova" class="hover:underline">Nova Venda</a>
        <form method="post" action="/logout" class="ml-auto">
            <button type="submit" class="hover:underline">Sair</button>
        </form>
    </nav>
    {% endif %}
    <main class="p-4 max-w-6xl mx-auto">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 12: Create `app/templates/login.html`**

```html
{% extends "base.html" %}
{% block title %}Entrar - Nana Lanches{% endblock %}
{% block content %}
<div class="max-w-sm mx-auto mt-16 bg-white p-6 rounded-lg shadow">
    <h1 class="text-xl font-bold mb-4">Nana Lanches</h1>
    {% if erro %}
    <p class="text-red-600 mb-4">{{ erro }}</p>
    {% endif %}
    <form method="post" action="/login" class="space-y-4">
        <div>
            <label class="block text-sm font-medium">Usuário</label>
            <input type="text" name="username" required class="w-full border rounded px-3 py-2">
        </div>
        <div>
            <label class="block text-sm font-medium">Senha</label>
            <input type="password" name="senha" required class="w-full border rounded px-3 py-2">
        </div>
        <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded">Entrar</button>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 13: Create `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Painel - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold">Bem-vindo, {{ usuario.username }}</h1>
{% endblock %}
```

- [ ] **Step 14: Modify `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.auth import NotAuthenticatedError
from app.config import settings
from app.routers import auth_router, dashboard_router

app = FastAPI(title="Nana Lanches")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedError):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 15: Create `app/seed.py`**

```python
from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models.usuario import Usuario


def criar_usuario_admin(db: Session, username: str, senha: str) -> Usuario:
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return existente
    usuario = Usuario(username=username, senha_hash=hash_senha(senha), ativo=True)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


if __name__ == "__main__":
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        username = input("Usuário admin: ")
        senha = input("Senha: ")
        criar_usuario_admin(db, username, senha)
        print("Usuário criado com sucesso.")
    finally:
        db.close()
```

- [ ] **Step 16: Run tests to verify they pass**

Run: `pytest tests/test_auth.py tests/test_auth_router.py -v`
Expected: PASS

- [ ] **Step 17: Commit**

```bash
git add app/auth.py app/seed.py app/routers app/templates app/main.py tests/test_auth.py tests/test_auth_router.py
git commit -m "feat: add login/logout session auth and protected dashboard route"
```

---

### Task 4: Products (Categoria + Produto)

**Files:**
- Create: `app/models/categoria.py`
- Create: `app/models/produto.py`
- Create: `app/services/__init__.py`
- Create: `app/services/produtos_service.py`
- Create: `app/routers/produtos_router.py`
- Create: `app/templates/produtos/list.html`
- Create: `app/templates/produtos/form.html`
- Create: `app/templates/produtos/_resultado_busca.html`
- Modify: `app/models/__init__.py`
- Modify: `app/main.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_produtos_service.py`
- Test: `tests/test_produtos_router.py`

**Interfaces:**
- Consumes: `app.database.Base`, `authed_client`/`db_session` fixtures.
- Produces: `app.models.Categoria`, `app.models.Produto` (fields: `codigo_interno`, `nome`, `codigo_fabricante`, `categoria_id`, `ncm`, `unidade`, `preco_custo`, `preco_venda`, `preco_atacado`, `estoque_atual`, `ativo`). `app.services.produtos_service.criar_produto(...)`, `.listar_produtos_por_categoria(db) -> list[tuple[Categoria, list[Produto]]]`, `.atualizar_produto(db, produto_id, **campos)`, `.alternar_ativo(db, produto_id)`, `.buscar_produtos(db, termo) -> list[Produto]`. Routes: `GET/POST /produtos`, `GET/POST /produtos/novo`, `POST /produtos/{id}/alternar-ativo`, `GET /produtos/buscar`. Test fixture `authed_client` (added to `conftest.py`, reused by all later router tests).

- [ ] **Step 1: Write failing tests for the products service**

`tests/test_produtos_service.py`:

```python
from decimal import Decimal

from app.services import produtos_service


def test_criar_produto_cria_categoria_automaticamente(db_session):
    produto = produtos_service.criar_produto(
        db_session,
        codigo_interno="1",
        nome="Refeição Diversas",
        categoria_nome="Diversos",
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("15.00"),
    )

    assert produto.id is not None
    assert produto.categoria.nome == "Diversos"


def test_listar_produtos_por_categoria_agrupa_corretamente(db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )
    produtos_service.criar_produto(
        db_session, codigo_interno="2", nome="Suco Natural", categoria_nome="Sucos",
        ncm="20091900", unidade="UN", preco_venda=Decimal("8.00"),
    )

    grupos = produtos_service.listar_produtos_por_categoria(db_session)

    nomes_categorias = [categoria.nome for categoria, _ in grupos]
    assert "Água Mineral" in nomes_categorias
    assert "Sucos" in nomes_categorias


def test_alternar_ativo_inverte_status(db_session):
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Energético", categoria_nome="Diversos",
        ncm="22029900", unidade="UN", preco_venda=Decimal("6.00"),
    )
    assert produto.ativo is True

    produtos_service.alternar_ativo(db_session, produto.id)
    db_session.refresh(produto)

    assert produto.ativo is False


def test_buscar_produtos_por_nome_ou_codigo(db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="7", nome="Refrigerante Lata", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"),
    )

    por_nome = produtos_service.buscar_produtos(db_session, "Refrigerante")
    por_codigo = produtos_service.buscar_produtos(db_session, "7")

    assert len(por_nome) == 1
    assert len(por_codigo) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_produtos_service.py -v`
Expected: FAIL — `app.services.produtos_service` not found.

- [ ] **Step 3: Create `app/models/categoria.py`**

```python
from sqlalchemy import Column, Integer, String

from app.database import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True)
    nome = Column(String(100), unique=True, nullable=False)
```

- [ ] **Step 4: Create `app/models/produto.py`**

```python
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class Produto(Base):
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True)
    codigo_interno = Column(String(50), nullable=False)
    nome = Column(String(200), nullable=False)
    codigo_fabricante = Column(String(50), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    ncm = Column(String(8), nullable=False)
    unidade = Column(String(6), nullable=False, default="UN")
    preco_custo = Column(Numeric(10, 2), nullable=False, default=0)
    preco_venda = Column(Numeric(10, 2), nullable=False)
    preco_atacado = Column(Numeric(10, 2), nullable=True)
    estoque_atual = Column(Numeric(10, 2), nullable=False, default=0)
    ativo = Column(Boolean, nullable=False, default=True)

    categoria = relationship("Categoria")
```

- [ ] **Step 5: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.produto import Produto
from app.models.usuario import Usuario

__all__ = ["Categoria", "Produto", "Usuario"]
```

- [ ] **Step 6: Create `app/services/__init__.py`**

Empty file.

- [ ] **Step 7: Create `app/services/produtos_service.py`**

```python
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.categoria import Categoria
from app.models.produto import Produto


def listar_produtos_por_categoria(db: Session) -> list[tuple[Categoria, list[Produto]]]:
    categorias = db.query(Categoria).order_by(Categoria.nome).all()
    resultado = []
    for categoria in categorias:
        produtos = (
            db.query(Produto)
            .filter(Produto.categoria_id == categoria.id)
            .order_by(Produto.nome)
            .all()
        )
        resultado.append((categoria, produtos))
    return resultado


def obter_ou_criar_categoria(db: Session, nome: str) -> Categoria:
    categoria = db.query(Categoria).filter(Categoria.nome == nome).first()
    if categoria is None:
        categoria = Categoria(nome=nome)
        db.add(categoria)
        db.commit()
        db.refresh(categoria)
    return categoria


def criar_produto(
    db: Session,
    *,
    codigo_interno: str,
    nome: str,
    categoria_nome: str,
    ncm: str,
    unidade: str,
    preco_venda: Decimal,
    codigo_fabricante: str | None = None,
    preco_custo: Decimal = Decimal("0"),
    preco_atacado: Decimal | None = None,
    estoque_atual: Decimal = Decimal("0"),
) -> Produto:
    categoria = obter_ou_criar_categoria(db, categoria_nome)
    produto = Produto(
        codigo_interno=codigo_interno,
        nome=nome,
        codigo_fabricante=codigo_fabricante,
        categoria_id=categoria.id,
        ncm=ncm,
        unidade=unidade,
        preco_custo=preco_custo,
        preco_venda=preco_venda,
        preco_atacado=preco_atacado,
        estoque_atual=estoque_atual,
        ativo=True,
    )
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto


def atualizar_produto(db: Session, produto_id: int, **campos) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    for campo, valor in campos.items():
        setattr(produto, campo, valor)
    db.commit()
    db.refresh(produto)
    return produto


def alternar_ativo(db: Session, produto_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    produto.ativo = not produto.ativo
    db.commit()
    db.refresh(produto)
    return produto


def buscar_produtos(db: Session, termo: str) -> list[Produto]:
    padrao = f"%{termo}%"
    return (
        db.query(Produto)
        .filter(Produto.ativo.is_(True))
        .filter((Produto.nome.ilike(padrao)) | (Produto.codigo_interno.ilike(padrao)))
        .order_by(Produto.nome)
        .limit(10)
        .all()
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_produtos_service.py -v`
Expected: PASS

- [ ] **Step 9: Modify `tests/conftest.py`** — add an authenticated-client fixture reused by all router tests from here on

Append to `tests/conftest.py`:

```python
from app.auth import hash_senha
from app.models.usuario import Usuario


@pytest.fixture()
def authed_client(client, db_session):
    db_session.add(Usuario(username="admin", senha_hash=hash_senha("senha123"), ativo=True))
    db_session.commit()
    client.post("/login", data={"username": "admin", "senha": "senha123"})
    return client
```

- [ ] **Step 10: Write failing router tests**

`tests/test_produtos_router.py`:

```python
from decimal import Decimal

from app.services import produtos_service


def test_listar_produtos_agrupados_por_categoria(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Refrigerante", categoria_nome="Diversos",
        ncm="22021000", unidade="UN", preco_venda=Decimal("5.00"),
    )

    response = authed_client.get("/produtos")

    assert response.status_code == 200
    assert "Diversos" in response.text
    assert "Refrigerante" in response.text


def test_criar_produto_via_formulario(authed_client):
    response = authed_client.post(
        "/produtos/novo",
        data={
            "codigo_interno": "10",
            "nome": "Suco de Laranja",
            "categoria_nome": "Sucos",
            "ncm": "20091900",
            "unidade": "UN",
            "preco_custo": "2.00",
            "preco_venda": "7.00",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/produtos")
    assert "Suco de Laranja" in listagem.text


def test_buscar_produtos_retorna_html_parcial(authed_client, db_session):
    produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Água Mineral", categoria_nome="Água Mineral",
        ncm="22011000", unidade="UN", preco_venda=Decimal("3.00"),
    )

    response = authed_client.get("/produtos/buscar", params={"termo": "Água"})

    assert response.status_code == 200
    assert "Água Mineral" in response.text
```

- [ ] **Step 11: Run tests to verify they fail**

Run: `pytest tests/test_produtos_router.py -v`
Expected: FAIL — no `/produtos` routes registered.

- [ ] **Step 12: Create `app/routers/produtos_router.py`**

```python
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.usuario import Usuario
from app.services import produtos_service

router = APIRouter(prefix="/produtos")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    grupos = produtos_service.listar_produtos_por_categoria(db)
    return templates.TemplateResponse("produtos/list.html", {"request": request, "grupos": grupos})


@router.get("/novo", response_class=HTMLResponse)
def novo_form(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("produtos/form.html", {"request": request})


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
    )
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
    return templates.TemplateResponse("produtos/_resultado_busca.html", {"request": request, "produtos": produtos})
```

- [ ] **Step 13: Create `app/templates/produtos/list.html`**

```html
{% extends "base.html" %}
{% block title %}Produtos - Nana Lanches{% endblock %}
{% block content %}
<div class="flex justify-between items-center mb-4">
    <h1 class="text-2xl font-bold">Produtos</h1>
    <a href="/produtos/novo" class="bg-slate-800 text-white px-4 py-2 rounded">+ Novo produto</a>
</div>
{% for categoria, produtos in grupos %}
<h2 class="text-lg font-semibold mt-6 mb-2">{{ categoria.nome }}</h2>
<table class="w-full bg-white rounded shadow overflow-hidden mb-4">
    <thead class="bg-slate-100 text-left">
        <tr>
            <th class="p-2">Código</th>
            <th class="p-2">Nome</th>
            <th class="p-2">Estoque</th>
            <th class="p-2">Preço venda</th>
            <th class="p-2">Ativo</th>
            <th class="p-2"></th>
        </tr>
    </thead>
    <tbody>
        {% for produto in produtos %}
        <tr class="border-t">
            <td class="p-2">{{ produto.codigo_interno }}</td>
            <td class="p-2">{{ produto.nome }}</td>
            <td class="p-2">{{ produto.estoque_atual }}</td>
            <td class="p-2">R$ {{ "%.2f"|format(produto.preco_venda) }}</td>
            <td class="p-2">{{ "Sim" if produto.ativo else "Não" }}</td>
            <td class="p-2">
                <form method="post" action="/produtos/{{ produto.id }}/alternar-ativo">
                    <button type="submit" class="text-slate-600 underline">
                        {{ "Desativar" if produto.ativo else "Ativar" }}
                    </button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endfor %}
{% endblock %}
```

- [ ] **Step 14: Create `app/templates/produtos/form.html`**

```html
{% extends "base.html" %}
{% block title %}Novo produto - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Novo produto</h1>
<form method="post" action="/produtos/novo" class="bg-white p-6 rounded shadow space-y-4 max-w-lg">
    <div>
        <label class="block text-sm font-medium">Código interno</label>
        <input type="text" name="codigo_interno" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Nome</label>
        <input type="text" name="nome" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Categoria</label>
        <input type="text" name="categoria_nome" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Código do fabricante</label>
        <input type="text" name="codigo_fabricante" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">NCM</label>
        <input type="text" name="ncm" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Unidade</label>
        <input type="text" name="unidade" value="UN" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Preço de custo</label>
        <input type="text" name="preco_custo" value="0" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Preço de venda</label>
        <input type="text" name="preco_venda" required class="w-full border rounded px-3 py-2">
    </div>
    <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded">Salvar</button>
</form>
{% endblock %}
```

- [ ] **Step 15: Create `app/templates/produtos/_resultado_busca.html`**

```html
<ul class="border rounded bg-white divide-y">
    {% for produto in produtos %}
    <li class="p-2 hover:bg-slate-50 cursor-pointer"
        onclick="document.getElementById('produto_id').value='{{ produto.id }}'; document.getElementById('produto_busca').value='{{ produto.nome }} ({{ produto.codigo_interno }})'; document.getElementById('resultado_busca').innerHTML='';">
        {{ produto.nome }} — {{ produto.codigo_interno }} — R$ {{ "%.2f"|format(produto.preco_venda) }}
    </li>
    {% endfor %}
</ul>
```

- [ ] **Step 16: Modify `app/main.py`** — register the products router

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.auth import NotAuthenticatedError
from app.config import settings
from app.routers import auth_router, dashboard_router, produtos_router

app = FastAPI(title="Nana Lanches")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(produtos_router.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedError):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 17: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 18: Commit**

```bash
git add app/models app/services app/routers/produtos_router.py app/templates/produtos app/main.py tests
git commit -m "feat: add product catalog with categories, CRUD, and search"
```

---

### Task 5: Customers (Cliente PF/PJ)

**Files:**
- Create: `app/models/cliente.py`
- Create: `app/services/clientes_service.py`
- Create: `app/routers/clientes_router.py`
- Create: `app/templates/clientes/list.html`
- Create: `app/templates/clientes/form.html`
- Create: `app/templates/clientes/_resultado_busca.html`
- Modify: `app/models/__init__.py`
- Modify: `app/main.py`
- Test: `tests/test_clientes_service.py`
- Test: `tests/test_clientes_router.py`

**Interfaces:**
- Consumes: `authed_client`/`db_session` fixtures (Task 2/4).
- Produces: `app.models.Cliente` (`tipo_pessoa`, `nome`, `cpf_cnpj`, `ie`, `endereco`, `telefone`, `email`, `consumidor_final`), `app.models.cliente.TipoPessoa` enum (`PF`, `PJ`). `app.services.clientes_service.garantir_consumidor_final(db) -> Cliente` (used by Task 6's sales flow), `.listar_clientes(db)`, `.criar_cliente(...)`, `.atualizar_cliente(db, cliente_id, **campos)`, `.buscar_clientes(db, termo)`. Routes: `GET/POST /clientes`, `GET/POST /clientes/novo`, `GET /clientes/buscar`.

- [ ] **Step 1: Write failing tests for the customers service**

`tests/test_clientes_service.py`:

```python
from app.models.cliente import TipoPessoa
from app.services import clientes_service


def test_garantir_consumidor_final_cria_uma_unica_vez(db_session):
    primeiro = clientes_service.garantir_consumidor_final(db_session)
    segundo = clientes_service.garantir_consumidor_final(db_session)

    assert primeiro.id == segundo.id
    assert primeiro.consumidor_final is True
    assert primeiro.nome == "AO CONSUMIDOR"


def test_criar_cliente_pf(db_session):
    cliente = clientes_service.criar_cliente(
        db_session, tipo_pessoa=TipoPessoa.PF, nome="João da Silva", cpf_cnpj="12345678900"
    )

    assert cliente.id is not None
    assert cliente.consumidor_final is False


def test_buscar_clientes_por_nome_ou_documento(db_session):
    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PJ, nome="Empresa XYZ", cpf_cnpj="11222333000181")

    por_nome = clientes_service.buscar_clientes(db_session, "Empresa")
    por_documento = clientes_service.buscar_clientes(db_session, "11222333")

    assert len(por_nome) == 1
    assert len(por_documento) == 1


def test_atualizar_cliente_padrao_consumidor_final_levanta_erro(db_session):
    consumidor = clientes_service.garantir_consumidor_final(db_session)

    try:
        clientes_service.atualizar_cliente(db_session, consumidor.id, nome="Outro nome")
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_clientes_service.py -v`
Expected: FAIL — `app.services.clientes_service` not found.

- [ ] **Step 3: Create `app/models/cliente.py`**

```python
import enum

from sqlalchemy import Boolean, Column, Enum, Integer, String

from app.database import Base


class TipoPessoa(str, enum.Enum):
    PF = "PF"
    PJ = "PJ"


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True)
    tipo_pessoa = Column(Enum(TipoPessoa), nullable=False, default=TipoPessoa.PF)
    nome = Column(String(200), nullable=False)
    cpf_cnpj = Column(String(18), nullable=True)
    ie = Column(String(20), nullable=True)
    endereco = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    email = Column(String(120), nullable=True)
    consumidor_final = Column(Boolean, nullable=False, default=False)
```

- [ ] **Step 4: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.cliente import Cliente, TipoPessoa
from app.models.produto import Produto
from app.models.usuario import Usuario

__all__ = ["Categoria", "Cliente", "TipoPessoa", "Produto", "Usuario"]
```

- [ ] **Step 5: Create `app/services/clientes_service.py`**

```python
from sqlalchemy.orm import Session

from app.models.cliente import Cliente, TipoPessoa

NOME_CONSUMIDOR_FINAL = "AO CONSUMIDOR"


def garantir_consumidor_final(db: Session) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.consumidor_final.is_(True)).first()
    if cliente is None:
        cliente = Cliente(nome=NOME_CONSUMIDOR_FINAL, tipo_pessoa=TipoPessoa.PF, consumidor_final=True)
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
    return cliente


def listar_clientes(db: Session) -> list[Cliente]:
    return db.query(Cliente).order_by(Cliente.nome).all()


def criar_cliente(
    db: Session,
    *,
    tipo_pessoa: TipoPessoa,
    nome: str,
    cpf_cnpj: str | None = None,
    ie: str | None = None,
    endereco: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
) -> Cliente:
    cliente = Cliente(
        tipo_pessoa=tipo_pessoa,
        nome=nome,
        cpf_cnpj=cpf_cnpj,
        ie=ie,
        endereco=endereco,
        telefone=telefone,
        email=email,
        consumidor_final=False,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def atualizar_cliente(db: Session, cliente_id: int, **campos) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError("Cliente não encontrado")
    if cliente.consumidor_final:
        raise ValueError("Cliente padrão Consumidor Final não pode ser editado")
    for campo, valor in campos.items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


def buscar_clientes(db: Session, termo: str) -> list[Cliente]:
    padrao = f"%{termo}%"
    return (
        db.query(Cliente)
        .filter((Cliente.nome.ilike(padrao)) | (Cliente.cpf_cnpj.ilike(padrao)))
        .order_by(Cliente.nome)
        .limit(10)
        .all()
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_clientes_service.py -v`
Expected: PASS

- [ ] **Step 7: Write failing router tests**

`tests/test_clientes_router.py`:

```python
def test_listar_clientes(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Maria Souza")

    response = authed_client.get("/clientes")

    assert response.status_code == 200
    assert "Maria Souza" in response.text


def test_criar_cliente_via_formulario(authed_client):
    response = authed_client.post(
        "/clientes/novo",
        data={"tipo_pessoa": "PJ", "nome": "Empresa ABC", "cpf_cnpj": "11222333000181"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    listagem = authed_client.get("/clientes")
    assert "Empresa ABC" in listagem.text


def test_buscar_clientes_retorna_html_parcial(authed_client, db_session):
    from app.models.cliente import TipoPessoa
    from app.services import clientes_service

    clientes_service.criar_cliente(db_session, tipo_pessoa=TipoPessoa.PF, nome="Carlos Pereira")

    response = authed_client.get("/clientes/buscar", params={"termo": "Carlos"})

    assert response.status_code == 200
    assert "Carlos Pereira" in response.text
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `pytest tests/test_clientes_router.py -v`
Expected: FAIL — no `/clientes` routes registered.

- [ ] **Step 9: Create `app/routers/clientes_router.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.cliente import TipoPessoa
from app.models.usuario import Usuario
from app.services import clientes_service

router = APIRouter(prefix="/clientes")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    clientes = clientes_service.listar_clientes(db)
    return templates.TemplateResponse("clientes/list.html", {"request": request, "clientes": clientes})


@router.get("/novo", response_class=HTMLResponse)
def novo_form(request: Request, usuario: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse("clientes/form.html", {"request": request})


@router.post("/novo")
def criar(
    tipo_pessoa: str = Form(...),
    nome: str = Form(...),
    cpf_cnpj: str = Form(""),
    ie: str = Form(""),
    endereco: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    clientes_service.criar_cliente(
        db,
        tipo_pessoa=TipoPessoa(tipo_pessoa),
        nome=nome,
        cpf_cnpj=cpf_cnpj or None,
        ie=ie or None,
        endereco=endereco or None,
        telefone=telefone or None,
        email=email or None,
    )
    return RedirectResponse(url="/clientes", status_code=303)


@router.get("/buscar", response_class=HTMLResponse)
def buscar(
    request: Request,
    termo: str = "",
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    clientes = clientes_service.buscar_clientes(db, termo) if termo else []
    return templates.TemplateResponse("clientes/_resultado_busca.html", {"request": request, "clientes": clientes})
```

- [ ] **Step 10: Create `app/templates/clientes/list.html`**

```html
{% extends "base.html" %}
{% block title %}Clientes - Nana Lanches{% endblock %}
{% block content %}
<div class="flex justify-between items-center mb-4">
    <h1 class="text-2xl font-bold">Clientes</h1>
    <a href="/clientes/novo" class="bg-slate-800 text-white px-4 py-2 rounded">+ Novo cliente</a>
</div>
<table class="w-full bg-white rounded shadow overflow-hidden">
    <thead class="bg-slate-100 text-left">
        <tr>
            <th class="p-2">Nome</th>
            <th class="p-2">Tipo</th>
            <th class="p-2">CPF/CNPJ</th>
            <th class="p-2">Telefone</th>
        </tr>
    </thead>
    <tbody>
        {% for cliente in clientes %}
        <tr class="border-t">
            <td class="p-2">{{ cliente.nome }}</td>
            <td class="p-2">{{ cliente.tipo_pessoa.value }}</td>
            <td class="p-2">{{ cliente.cpf_cnpj or "-" }}</td>
            <td class="p-2">{{ cliente.telefone or "-" }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 11: Create `app/templates/clientes/form.html`**

```html
{% extends "base.html" %}
{% block title %}Novo cliente - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Novo cliente</h1>
<form method="post" action="/clientes/novo" class="bg-white p-6 rounded shadow space-y-4 max-w-lg">
    <div>
        <label class="block text-sm font-medium">Tipo</label>
        <select name="tipo_pessoa" class="w-full border rounded px-3 py-2">
            <option value="PF">Pessoa Física</option>
            <option value="PJ">Pessoa Jurídica</option>
        </select>
    </div>
    <div>
        <label class="block text-sm font-medium">Nome / Razão Social</label>
        <input type="text" name="nome" required class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">CPF/CNPJ</label>
        <input type="text" name="cpf_cnpj" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Inscrição Estadual</label>
        <input type="text" name="ie" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Endereço</label>
        <input type="text" name="endereco" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Telefone</label>
        <input type="text" name="telefone" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">E-mail</label>
        <input type="email" name="email" class="w-full border rounded px-3 py-2">
    </div>
    <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded">Salvar</button>
</form>
{% endblock %}
```

- [ ] **Step 12: Create `app/templates/clientes/_resultado_busca.html`**

```html
<ul class="border rounded bg-white divide-y">
    {% for cliente in clientes %}
    <li class="p-2 hover:bg-slate-50 cursor-pointer"
        onclick="document.getElementById('cliente_id').value='{{ cliente.id }}'; document.getElementById('cliente_busca').value='{{ cliente.nome }}'; document.getElementById('resultado_busca_cliente').innerHTML='';">
        {{ cliente.nome }} {% if cliente.cpf_cnpj %}— {{ cliente.cpf_cnpj }}{% endif %}
    </li>
    {% endfor %}
</ul>
```

- [ ] **Step 13: Modify `app/main.py`** — register the customers router

```python
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from app.auth import NotAuthenticatedError
from app.config import settings
from app.routers import auth_router, clientes_router, dashboard_router, produtos_router

app = FastAPI(title="Nana Lanches")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(produtos_router.router)
app.include_router(clientes_router.router)


@app.exception_handler(NotAuthenticatedError)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedError):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 15: Commit**

```bash
git add app/models/cliente.py app/services/clientes_service.py app/routers/clientes_router.py app/templates/clientes app/models/__init__.py app/main.py tests
git commit -m "feat: add PF/PJ customer registration with default Consumidor Final"
```

---

### Task 6: Sales — start a sale, add/remove items

**Files:**
- Create: `app/models/venda.py`
- Create: `app/services/vendas_service.py`
- Create: `app/routers/vendas_router.py`
- Create: `app/templates/vendas/nova.html`
- Create: `app/templates/vendas/detalhe.html`
- Create: `app/templates/vendas/_itens.html`
- Modify: `app/models/__init__.py`
- Modify: `app/main.py`
- Test: `tests/test_vendas_service.py`
- Test: `tests/test_vendas_router.py`

**Interfaces:**
- Consumes: `app.models.Cliente`, `app.models.Produto`, `app.services.clientes_service.garantir_consumidor_final`, `app.services.produtos_service.criar_produto` (Tasks 4/5).
- Produces: `app.models.Venda` (`numero_orcamento`, `cliente_id`, `data_venda`, `status`, `forma_pagamento`, `valor_total`, `valor_pago`, `troco`), `app.models.venda.StatusVenda` enum (`ORCAMENTO`, `PAGO`, `CANCELADO`), `app.models.VendaItem` (`venda_id`, `produto_id`, `quantidade`, `preco_unitario`). `app.services.vendas_service.criar_venda(db, cliente_id) -> Venda`, `.adicionar_item(db, venda_id, produto_id, quantidade: Decimal) -> VendaItem`, `.remover_item(db, item_id) -> None`, `.recalcular_total(db, venda_id) -> Decimal`. Routes: `GET/POST /vendas/nova`, `GET /vendas/{id}`, `POST /vendas/{id}/itens`, `POST /vendas/itens/{item_id}/remover`. `Venda.status` and `Venda.valor_total` are consumed by Task 7 (payment) and Task 8 (fiscal payload).

- [ ] **Step 1: Write failing tests for the sales service**

`tests/test_vendas_service.py`:

```python
from decimal import Decimal

from app.models.venda import StatusVenda
from app.services import clientes_service, produtos_service, vendas_service


def _criar_produto(db_session, preco="10.00"):
    return produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco),
    )


def test_criar_venda_gera_numero_de_orcamento_sequencial(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)

    venda1 = vendas_service.criar_venda(db_session, cliente.id)
    venda2 = vendas_service.criar_venda(db_session, cliente.id)

    assert venda1.numero_orcamento == 1
    assert venda2.numero_orcamento == 2
    assert venda1.status == StatusVenda.ORCAMENTO


def test_adicionar_item_usa_preco_do_produto_e_recalcula_total(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session, preco="10.00")
    venda = vendas_service.criar_venda(db_session, cliente.id)

    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))
    db_session.refresh(venda)

    assert venda.valor_total == Decimal("20.00")
    assert len(venda.itens) == 1


def test_remover_item_recalcula_total(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = _criar_produto(db_session, preco="10.00")
    venda = vendas_service.criar_venda(db_session, cliente.id)
    item = vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("2"))

    vendas_service.remover_item(db_session, item.id)
    db_session.refresh(venda)

    assert venda.valor_total == Decimal("0")
    assert len(venda.itens) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vendas_service.py -v`
Expected: FAIL — `app.services.vendas_service` not found.

- [ ] **Step 3: Create `app/models/venda.py`**

```python
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class StatusVenda(str, enum.Enum):
    ORCAMENTO = "orcamento"
    PAGO = "pago"
    CANCELADO = "cancelado"


class Venda(Base):
    __tablename__ = "vendas"

    id = Column(Integer, primary_key=True)
    numero_orcamento = Column(Integer, unique=True, nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    data_venda = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(Enum(StatusVenda), nullable=False, default=StatusVenda.ORCAMENTO)
    forma_pagamento = Column(String(30), nullable=True)
    valor_total = Column(Numeric(10, 2), nullable=False, default=0)
    valor_pago = Column(Numeric(10, 2), nullable=True)
    troco = Column(Numeric(10, 2), nullable=True)

    cliente = relationship("Cliente")
    itens = relationship("VendaItem", back_populates="venda", cascade="all, delete-orphan")


class VendaItem(Base):
    __tablename__ = "venda_itens"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), nullable=False)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    quantidade = Column(Numeric(10, 2), nullable=False, default=1)
    preco_unitario = Column(Numeric(10, 2), nullable=False)

    venda = relationship("Venda", back_populates="itens")
    produto = relationship("Produto")
```

- [ ] **Step 4: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.cliente import Cliente, TipoPessoa
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.models.venda import StatusVenda, Venda, VendaItem

__all__ = [
    "Categoria",
    "Cliente",
    "TipoPessoa",
    "Produto",
    "Usuario",
    "StatusVenda",
    "Venda",
    "VendaItem",
]
```

- [ ] **Step 5: Create `app/services/vendas_service.py`**

```python
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.produto import Produto
from app.models.venda import StatusVenda, Venda, VendaItem


def proximo_numero_orcamento(db: Session) -> int:
    ultimo = db.query(Venda).order_by(Venda.numero_orcamento.desc()).first()
    return (ultimo.numero_orcamento + 1) if ultimo else 1


def criar_venda(db: Session, cliente_id: int) -> Venda:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise ValueError("Cliente não encontrado")
    venda = Venda(
        numero_orcamento=proximo_numero_orcamento(db),
        cliente_id=cliente_id,
        status=StatusVenda.ORCAMENTO,
        valor_total=Decimal("0"),
    )
    db.add(venda)
    db.commit()
    db.refresh(venda)
    return venda


def adicionar_item(db: Session, venda_id: int, produto_id: int, quantidade: Decimal) -> VendaItem:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    produto = db.get(Produto, produto_id)
    if produto is None:
        raise ValueError("Produto não encontrado")
    item = VendaItem(
        venda_id=venda_id,
        produto_id=produto_id,
        quantidade=quantidade,
        preco_unitario=produto.preco_venda,
    )
    db.add(item)
    db.commit()
    recalcular_total(db, venda_id)
    db.refresh(item)
    return item


def remover_item(db: Session, item_id: int) -> None:
    item = db.get(VendaItem, item_id)
    if item is None:
        raise ValueError("Item não encontrado")
    venda_id = item.venda_id
    db.delete(item)
    db.commit()
    recalcular_total(db, venda_id)


def recalcular_total(db: Session, venda_id: int) -> Decimal:
    venda = db.get(Venda, venda_id)
    total = sum((item.quantidade * item.preco_unitario for item in venda.itens), Decimal("0"))
    venda.valor_total = total
    db.commit()
    return total
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_vendas_service.py -v`
Expected: PASS

- [ ] **Step 7: Write failing router tests**

`tests/test_vendas_router.py`:

```python
from decimal import Decimal

from app.services import produtos_service


def test_criar_venda_via_formulario_redireciona_para_detalhe(authed_client, db_session):
    response = authed_client.get("/vendas/nova")
    assert response.status_code == 200

    consumidor = authed_client.get("/vendas/nova")
    assert "cliente_id" in consumidor.text

    from app.services import clientes_service

    cliente = clientes_service.garantir_consumidor_final(db_session)

    criar = authed_client.post("/vendas/nova", data={"cliente_id": cliente.id}, follow_redirects=False)
    assert criar.status_code == 303
    assert criar.headers["location"].startswith("/vendas/")


def test_adicionar_e_remover_item_na_venda(authed_client, db_session):
    from app.services import clientes_service, vendas_service

    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)

    resposta_add = authed_client.post(
        f"/vendas/{venda.id}/itens", data={"produto_id": produto.id, "quantidade": "2"}
    )
    assert resposta_add.status_code == 200
    assert "Lanche" in resposta_add.text
    assert "20.00" in resposta_add.text

    detalhe = authed_client.get(f"/vendas/{venda.id}")
    assert detalhe.status_code == 200
    assert "Lanche" in detalhe.text
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `pytest tests/test_vendas_router.py -v`
Expected: FAIL — no `/vendas` routes registered.

- [ ] **Step 9: Create `app/routers/vendas_router.py`**

```python
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.usuario import Usuario
from app.models.venda import Venda, VendaItem
from app.services import clientes_service, vendas_service

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
    produto_id: int = Form(...),
    quantidade: str = Form("1"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    vendas_service.adicionar_item(db, venda_id, produto_id, Decimal(quantidade))
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/_itens.html", {"request": request, "venda": venda})


@router.post("/itens/{item_id}/remover", response_class=HTMLResponse)
def remover_item(item_id: int, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    item = db.get(VendaItem, item_id)
    venda_id = item.venda_id
    vendas_service.remover_item(db, item_id)
    venda = db.get(Venda, venda_id)
    return templates.TemplateResponse("vendas/_itens.html", {"request": request, "venda": venda})
```

- [ ] **Step 10: Create `app/templates/vendas/nova.html`**

```html
{% extends "base.html" %}
{% block title %}Nova Venda - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Nova Venda</h1>
<form method="post" action="/vendas/nova" class="bg-white p-6 rounded shadow space-y-4 max-w-lg">
    <div class="relative">
        <label class="block text-sm font-medium">Cliente</label>
        <input type="text" id="cliente_busca" value="{{ cliente_padrao.nome }}"
               hx-get="/clientes/buscar" hx-trigger="keyup changed delay:300ms" hx-target="#resultado_busca_cliente"
               name="termo" class="w-full border rounded px-3 py-2" autocomplete="off">
        <input type="hidden" id="cliente_id" name="cliente_id" value="{{ cliente_padrao.id }}">
        <div id="resultado_busca_cliente" class="absolute z-10 w-full"></div>
    </div>
    <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded">Iniciar venda</button>
</form>
{% endblock %}
```

- [ ] **Step 11: Create `app/templates/vendas/detalhe.html`**

```html
{% extends "base.html" %}
{% block title %}Orçamento {{ venda.numero_orcamento }} - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-1">Orçamento nº {{ venda.numero_orcamento }}</h1>
<p class="text-slate-600 mb-4">Cliente: {{ venda.cliente.nome }} — Status: {{ venda.status.value }}</p>

<div class="bg-white p-4 rounded shadow mb-4 relative">
    <h2 class="font-semibold mb-2">Adicionar produto</h2>
    <form hx-post="/vendas/{{ venda.id }}/itens" hx-target="#itens-venda" hx-swap="outerHTML" class="flex flex-wrap gap-2 items-end">
        <div class="relative">
            <label class="block text-sm">Produto</label>
            <input type="text" id="produto_busca" hx-get="/produtos/buscar" hx-trigger="keyup changed delay:300ms"
                   hx-target="#resultado_busca" name="termo" class="border rounded px-3 py-2" autocomplete="off">
            <input type="hidden" id="produto_id" name="produto_id">
            <div id="resultado_busca" class="absolute z-10"></div>
        </div>
        <div>
            <label class="block text-sm">Quantidade</label>
            <input type="text" name="quantidade" value="1" class="border rounded px-3 py-2 w-24">
        </div>
        <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded">Adicionar</button>
    </form>
</div>

{% include "vendas/_itens.html" %}

{% if venda.status.value == "orcamento" %}
<a href="/vendas/{{ venda.id }}/pagamento" class="inline-block mt-4 bg-emerald-700 text-white px-4 py-2 rounded">
    Ir para pagamento
</a>
{% else %}
<a href="/vendas/{{ venda.id }}/nota" class="inline-block mt-4 bg-emerald-700 text-white px-4 py-2 rounded">
    Ver nota fiscal
</a>
{% endif %}
{% endblock %}
```

- [ ] **Step 12: Create `app/templates/vendas/_itens.html`**

```html
<table id="itens-venda" class="w-full bg-white rounded shadow overflow-hidden">
    <thead class="bg-slate-100 text-left">
        <tr>
            <th class="p-2">Produto</th>
            <th class="p-2">Qtd</th>
            <th class="p-2">Preço unit.</th>
            <th class="p-2">Total</th>
            <th class="p-2"></th>
        </tr>
    </thead>
    <tbody>
        {% for item in venda.itens %}
        <tr class="border-t">
            <td class="p-2">{{ item.produto.nome }}</td>
            <td class="p-2">{{ item.quantidade }}</td>
            <td class="p-2">R$ {{ "%.2f"|format(item.preco_unitario) }}</td>
            <td class="p-2">R$ {{ "%.2f"|format(item.quantidade * item.preco_unitario) }}</td>
            <td class="p-2">
                <button hx-post="/vendas/itens/{{ item.id }}/remover" hx-target="#itens-venda" hx-swap="outerHTML"
                        class="text-red-600 underline">Remover</button>
            </td>
        </tr>
        {% endfor %}
    </tbody>
    <tfoot>
        <tr class="border-t font-bold">
            <td class="p-2" colspan="3">Total</td>
            <td class="p-2" colspan="2">R$ {{ "%.2f"|format(venda.valor_total) }}</td>
        </tr>
    </tfoot>
</table>
```

- [ ] **Step 13: Modify `app/main.py`** — register the sales router

```python
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
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 15: Commit**

```bash
git add app/models/venda.py app/services/vendas_service.py app/routers/vendas_router.py app/templates/vendas app/models/__init__.py app/main.py tests
git commit -m "feat: add sale creation with item search, add, and remove via HTMX"
```

---

### Task 7: Payment, installments, and stock deduction

**Files:**
- Create: `app/models/parcela.py`
- Create: `app/services/parcelas_service.py`
- Create: `app/templates/vendas/pagamento.html`
- Modify: `app/models/__init__.py`
- Modify: `app/routers/vendas_router.py`
- Test: `tests/test_parcelas_service.py`
- Test: `tests/test_pagamento_router.py`

**Interfaces:**
- Consumes: `app.models.Venda`, `app.models.venda.StatusVenda`, `app.models.Produto`, `app.services.vendas_service.criar_venda`/`.adicionar_item` (Task 6).
- Produces: `app.models.Parcela` (`venda_id`, `numero`, `valor`, `vencimento`, `status`), `app.models.parcela.StatusParcela` enum (`ABERTO`, `PAGO`). `app.services.parcelas_service.gerar_parcelas(db, venda_id, forma_pagamento, numero_parcelas, primeiro_vencimento=None) -> list[Parcela]`, `.confirmar_venda(db, venda_id, valor_pago: Decimal) -> Venda` (deducts `Produto.estoque_atual`, sets `Venda.status = PAGO`). Routes: `GET/POST /vendas/{id}/pagamento` — on success, `Venda.status` becomes `PAGO`, which Task 8/9 rely on before fiscal emission is allowed.

- [ ] **Step 1: Write failing tests for the payment service**

`tests/test_parcelas_service.py`:

```python
from decimal import Decimal

from app.models.venda import StatusVenda
from app.services import clientes_service, parcelas_service, produtos_service, vendas_service


def _venda_com_item(db_session, preco="10.00", quantidade="3", estoque="10"):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco), estoque_atual=Decimal(estoque),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal(quantidade))
    return venda, produto


def test_gerar_parcelas_divide_valor_e_ajusta_arredondamento(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1")  # total = 10.00

    parcelas = parcelas_service.gerar_parcelas(db_session, venda.id, "cartao_credito", 3)

    assert len(parcelas) == 3
    assert sum(p.valor for p in parcelas) == Decimal("10.00")
    assert parcelas[0].numero == 1
    assert parcelas[-1].numero == 3


def test_confirmar_venda_baixa_estoque_e_marca_como_paga(db_session):
    venda, produto = _venda_com_item(db_session, preco="10.00", quantidade="2", estoque="10")

    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("20.00"))
    db_session.refresh(venda)
    db_session.refresh(produto)

    assert venda.status == StatusVenda.PAGO
    assert produto.estoque_atual == Decimal("8")
    assert venda.troco == Decimal("0")


def test_confirmar_venda_calcula_troco(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1", estoque="10")

    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("15.00"))
    db_session.refresh(venda)

    assert venda.troco == Decimal("5.00")


def test_confirmar_venda_ja_paga_levanta_erro(db_session):
    venda, _ = _venda_com_item(db_session, preco="10.00", quantidade="1", estoque="10")
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))

    try:
        parcelas_service.confirmar_venda(db_session, venda.id, Decimal("10.00"))
        assert False, "deveria ter levantado ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parcelas_service.py -v`
Expected: FAIL — `app.services.parcelas_service` not found.

- [ ] **Step 3: Create `app/models/parcela.py`**

```python
import enum
from datetime import date

from sqlalchemy import Column, Date, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.orm import relationship

from app.database import Base


class StatusParcela(str, enum.Enum):
    ABERTO = "aberto"
    PAGO = "pago"


class Parcela(Base):
    __tablename__ = "parcelas"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), nullable=False)
    numero = Column(Integer, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    vencimento = Column(Date, nullable=False)
    status = Column(Enum(StatusParcela), nullable=False, default=StatusParcela.ABERTO)

    venda = relationship("Venda")
```

- [ ] **Step 4: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.cliente import Cliente, TipoPessoa
from app.models.parcela import Parcela, StatusParcela
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.models.venda import StatusVenda, Venda, VendaItem

__all__ = [
    "Categoria",
    "Cliente",
    "TipoPessoa",
    "Parcela",
    "StatusParcela",
    "Produto",
    "Usuario",
    "StatusVenda",
    "Venda",
    "VendaItem",
]
```

- [ ] **Step 5: Create `app/services/parcelas_service.py`**

```python
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.parcela import Parcela
from app.models.produto import Produto
from app.models.venda import StatusVenda, Venda


def gerar_parcelas(
    db: Session,
    venda_id: int,
    forma_pagamento: str,
    numero_parcelas: int,
    primeiro_vencimento: date | None = None,
) -> list[Parcela]:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if numero_parcelas < 1:
        raise ValueError("Número de parcelas deve ser ao menos 1")

    db.query(Parcela).filter(Parcela.venda_id == venda_id).delete()

    valor_parcela = (venda.valor_total / numero_parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valores = [valor_parcela] * numero_parcelas
    diferenca = venda.valor_total - (valor_parcela * numero_parcelas)
    valores[-1] += diferenca

    base = primeiro_vencimento or date.today()
    parcelas = []
    for i, valor in enumerate(valores, start=1):
        parcela = Parcela(
            venda_id=venda_id,
            numero=i,
            valor=valor,
            vencimento=base + timedelta(days=30 * (i - 1)),
        )
        db.add(parcela)
        parcelas.append(parcela)

    venda.forma_pagamento = forma_pagamento
    db.commit()
    for parcela in parcelas:
        db.refresh(parcela)
    return parcelas


def confirmar_venda(db: Session, venda_id: int, valor_pago: Decimal) -> Venda:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")
    if venda.status != StatusVenda.ORCAMENTO:
        raise ValueError("Venda já foi confirmada ou cancelada")

    for item in venda.itens:
        produto = db.get(Produto, item.produto_id)
        produto.estoque_atual = produto.estoque_atual - item.quantidade

    venda.valor_pago = valor_pago
    venda.troco = max(valor_pago - venda.valor_total, Decimal("0"))
    venda.status = StatusVenda.PAGO
    db.commit()
    db.refresh(venda)
    return venda
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_parcelas_service.py -v`
Expected: PASS

- [ ] **Step 7: Write failing router test**

`tests/test_pagamento_router.py`:

```python
from decimal import Decimal

from app.models.venda import StatusVenda
from app.services import clientes_service, produtos_service, vendas_service


def test_confirmar_pagamento_marca_venda_como_paga_e_redireciona_para_nota(authed_client, db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))

    response = authed_client.post(
        f"/vendas/{venda.id}/pagamento",
        data={"forma_pagamento": "dinheiro", "numero_parcelas": "1", "valor_pago": "10.00"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/vendas/{venda.id}/nota"

    db_session.refresh(venda)
    assert venda.status == StatusVenda.PAGO
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/test_pagamento_router.py -v`
Expected: FAIL — no `/vendas/{id}/pagamento` route registered.

- [ ] **Step 9: Modify `app/routers/vendas_router.py`** — add the payment routes

Add these imports at the top (alongside the existing ones):

```python
from app.services import clientes_service, parcelas_service, vendas_service
```

Append these two routes at the end of `app/routers/vendas_router.py`:

```python
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
    parcelas_service.gerar_parcelas(db, venda_id, forma_pagamento, numero_parcelas)
    parcelas_service.confirmar_venda(db, venda_id, Decimal(valor_pago))
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)
```

- [ ] **Step 10: Create `app/templates/vendas/pagamento.html`**

```html
{% extends "base.html" %}
{% block title %}Pagamento - Orçamento {{ venda.numero_orcamento }}{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Pagamento — Orçamento nº {{ venda.numero_orcamento }}</h1>
<p class="text-xl mb-4">Valor total: <strong>R$ {{ "%.2f"|format(venda.valor_total) }}</strong></p>
<form method="post" action="/vendas/{{ venda.id }}/pagamento" class="bg-white p-6 rounded shadow space-y-4 max-w-lg">
    <div>
        <label class="block text-sm font-medium">Forma de pagamento</label>
        <select name="forma_pagamento" class="w-full border rounded px-3 py-2">
            <option value="dinheiro">Dinheiro</option>
            <option value="cartao_credito">Cartão de Crédito</option>
            <option value="cartao_debito">Cartão de Débito</option>
            <option value="pix">Pix</option>
        </select>
    </div>
    <div>
        <label class="block text-sm font-medium">Parcelas</label>
        <input type="number" name="numero_parcelas" value="1" min="1" class="w-full border rounded px-3 py-2">
    </div>
    <div>
        <label class="block text-sm font-medium">Valor pago</label>
        <input type="text" name="valor_pago" value="{{ venda.valor_total }}" class="w-full border rounded px-3 py-2">
    </div>
    <button type="submit" class="bg-emerald-700 text-white px-4 py-2 rounded">Confirmar venda</button>
</form>
{% endblock %}
```

Note: this template links forward to `/vendas/{{ venda.id }}/nota`, which is created in Task 9. Until Task 9 is done, that link 404s if clicked manually — this is expected and does not affect this task's tests (the redirect target route is created before any manual end-to-end check happens).

- [ ] **Step 11: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 12: Commit**

```bash
git add app/models/parcela.py app/services/parcelas_service.py app/templates/vendas/pagamento.html app/models/__init__.py app/routers/vendas_router.py tests
git commit -m "feat: add payment step with installment generation and stock deduction"
```

---

### Task 8: Fiscal provider abstraction + Focus NFe implementation

**Files:**
- Create: `app/models/nota_fiscal.py`
- Create: `app/services/fiscal/__init__.py`
- Create: `app/services/fiscal/base.py`
- Create: `app/services/fiscal/focus_nfe.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_focus_nfe.py`

**Interfaces:**
- Consumes: `app.models.Venda`, `app.models.VendaItem`, `app.config.settings` (Tasks 1, 6).
- Produces: `app.models.NotaFiscal` (`venda_id`, `provedor`, `referencia`, `status`, `numero`, `serie`, `chave_acesso`, `protocolo`, `url_danfe`, `url_xml`, `mensagem_erro`), `app.models.nota_fiscal.StatusNota` enum. `app.services.fiscal.base.FiscalProvider` (ABC with `emitir`, `consultar`, `cancelar`), `app.services.fiscal.base.ResultadoFiscal` dataclass. `app.services.fiscal.focus_nfe.FocusNFeProvider(token=None, ambiente=None, client=None)` implementing `FiscalProvider`, and `montar_payload(venda) -> dict`. Task 9 depends on `FiscalProvider` and `FocusNFeProvider` exactly as named here.

- [ ] **Step 1: Write failing tests for the Focus NFe provider**

`tests/test_focus_nfe.py`:

```python
from decimal import Decimal

import httpx
import pytest
import respx

from app.models.cliente import Cliente, TipoPessoa
from app.models.categoria import Categoria
from app.models.produto import Produto
from app.services.vendas_service import adicionar_item, criar_venda
from app.services.fiscal.focus_nfe import FocusNFeProvider


@pytest.fixture()
def venda_com_item(db_session):
    categoria = Categoria(nome="Lanches")
    db_session.add(categoria)
    db_session.commit()
    produto = Produto(
        codigo_interno="1",
        nome="LANCHES DIVERSAS",
        categoria_id=categoria.id,
        ncm="21069090",
        unidade="UN",
        preco_venda=Decimal("15.00"),
        estoque_atual=Decimal("10"),
    )
    cliente = Cliente(tipo_pessoa=TipoPessoa.PF, nome="AO CONSUMIDOR", consumidor_final=True)
    db_session.add_all([produto, cliente])
    db_session.commit()
    venda = criar_venda(db_session, cliente.id)
    adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    db_session.refresh(venda)
    return venda


@pytest.fixture()
def provider():
    client = httpx.Client(base_url="https://homologacao.focusnfe.com.br", auth=("test-token", ""))
    return FocusNFeProvider(token="test-token", ambiente="homologacao", client=client)


@respx.mock
def test_emitir_retorna_processando(provider, venda_com_item):
    respx.post("https://homologacao.focusnfe.com.br/v2/nfce").mock(
        return_value=httpx.Response(202, json={"status": "processando_autorizacao"})
    )

    resultado = provider.emitir(venda_com_item)

    assert resultado.status == "processando"
    assert resultado.referencia == f"venda-{venda_com_item.id}"


@respx.mock
def test_consultar_retorna_autorizada_com_dados(provider):
    respx.get("https://homologacao.focusnfe.com.br/v2/nfce/venda-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "autorizado",
                "numero": "123",
                "serie": "1",
                "chave_nfe": "1" * 44,
                "protocolo_autorizacao": "abc123",
                "caminho_danfe": "https://homologacao.focusnfe.com.br/danfe/venda-1",
            },
        )
    )

    resultado = provider.consultar("venda-1")

    assert resultado.status == "autorizada"
    assert resultado.chave_acesso == "1" * 44
    assert resultado.url_danfe == "https://homologacao.focusnfe.com.br/danfe/venda-1"


@respx.mock
def test_cancelar_retorna_cancelada(provider):
    respx.delete("https://homologacao.focusnfe.com.br/v2/nfce/venda-1").mock(
        return_value=httpx.Response(200, json={"status": "cancelado"})
    )

    resultado = provider.cancelar("venda-1", "Erro de digitação")

    assert resultado.status == "cancelada"


@respx.mock
def test_emitir_com_erro_retorna_rejeitada_e_mensagem(provider, venda_com_item):
    respx.post("https://homologacao.focusnfe.com.br/v2/nfce").mock(
        return_value=httpx.Response(
            422, json={"status": "erro_autorizacao", "mensagem_sefaz": "CFOP inválido"}
        )
    )

    resultado = provider.emitir(venda_com_item)

    assert resultado.status == "rejeitada"
    assert resultado.mensagem_erro == "CFOP inválido"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_focus_nfe.py -v`
Expected: FAIL — `app.services.fiscal` module not found.

- [ ] **Step 3: Create `app/models/nota_fiscal.py`**

```python
import enum

from sqlalchemy import Column, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class StatusNota(str, enum.Enum):
    PROCESSANDO = "processando"
    AUTORIZADA = "autorizada"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"

    id = Column(Integer, primary_key=True)
    venda_id = Column(Integer, ForeignKey("vendas.id"), unique=True, nullable=False)
    provedor = Column(String(30), nullable=False, default="focus_nfe")
    referencia = Column(String(50), nullable=False)
    status = Column(Enum(StatusNota), nullable=False, default=StatusNota.PROCESSANDO)
    numero = Column(String(20), nullable=True)
    serie = Column(String(10), nullable=True)
    chave_acesso = Column(String(44), nullable=True)
    protocolo = Column(String(30), nullable=True)
    url_danfe = Column(String(255), nullable=True)
    url_xml = Column(String(255), nullable=True)
    mensagem_erro = Column(Text, nullable=True)

    venda = relationship("Venda")
```

- [ ] **Step 4: Modify `app/models/__init__.py`**

```python
from app.models.categoria import Categoria
from app.models.cliente import Cliente, TipoPessoa
from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.parcela import Parcela, StatusParcela
from app.models.produto import Produto
from app.models.usuario import Usuario
from app.models.venda import StatusVenda, Venda, VendaItem

__all__ = [
    "Categoria",
    "Cliente",
    "TipoPessoa",
    "NotaFiscal",
    "StatusNota",
    "Parcela",
    "StatusParcela",
    "Produto",
    "Usuario",
    "StatusVenda",
    "Venda",
    "VendaItem",
]
```

- [ ] **Step 5: Create `app/services/fiscal/__init__.py`**

Empty file.

- [ ] **Step 6: Create `app/services/fiscal/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.venda import Venda


@dataclass
class ResultadoFiscal:
    referencia: str
    status: str
    numero: str | None = None
    serie: str | None = None
    chave_acesso: str | None = None
    protocolo: str | None = None
    url_danfe: str | None = None
    url_xml: str | None = None
    mensagem_erro: str | None = None


class FiscalProvider(ABC):
    @abstractmethod
    def emitir(self, venda: Venda) -> ResultadoFiscal:
        ...

    @abstractmethod
    def consultar(self, referencia: str) -> ResultadoFiscal:
        ...

    @abstractmethod
    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        ...
```

- [ ] **Step 7: Create `app/services/fiscal/focus_nfe.py`**

```python
import httpx

from app.config import settings
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal

BASE_URLS = {
    "homologacao": "https://homologacao.focusnfe.com.br",
    "producao": "https://api.focusnfe.com.br",
}

STATUS_MAP = {
    "processando_autorizacao": "processando",
    "autorizado": "autorizada",
    "erro_autorizacao": "rejeitada",
    "cancelado": "cancelada",
}


def montar_payload(venda: Venda) -> dict:
    cliente = venda.cliente
    payload = {
        "natureza_operacao": "Venda",
        "data_emissao": venda.data_venda.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "presenca_comprador": "1",
        "modalidade_frete": "9",
        "items": [
            {
                "numero_item": str(index),
                "codigo_produto": item.produto.codigo_interno,
                "descricao": item.produto.nome,
                "ncm": item.produto.ncm,
                "cfop": "5102",
                "unidade_comercial": item.produto.unidade,
                "quantidade_comercial": str(item.quantidade),
                "valor_unitario_comercial": str(item.preco_unitario),
                "valor_bruto": str(item.quantidade * item.preco_unitario),
                "unidade_tributavel": item.produto.unidade,
                "quantidade_tributavel": str(item.quantidade),
                "valor_unitario_tributavel": str(item.preco_unitario),
                "icms_origem": "0",
                "icms_situacao_tributaria": "102",
                "pis_situacao_tributaria": "49",
                "cofins_situacao_tributaria": "49",
            }
            for index, item in enumerate(venda.itens, start=1)
        ],
    }
    if cliente is not None and not cliente.consumidor_final and cliente.cpf_cnpj:
        documento = cliente.cpf_cnpj
        if len(documento) <= 11:
            payload["cpf"] = documento
        else:
            payload["cnpj"] = documento
        payload["nome_destinatario"] = cliente.nome
    return payload


class FocusNFeProvider(FiscalProvider):
    def __init__(self, token: str | None = None, ambiente: str | None = None, client: httpx.Client | None = None):
        self.token = token or settings.focus_nfe_token
        self.ambiente = ambiente or settings.focus_nfe_ambiente
        self.base_url = BASE_URLS[self.ambiente]
        self.client = client or httpx.Client(base_url=self.base_url, auth=(self.token, ""))

    def emitir(self, venda: Venda) -> ResultadoFiscal:
        referencia = f"venda-{venda.id}"
        payload = montar_payload(venda)
        response = self.client.post(f"/v2/nfce?ref={referencia}", json=payload)
        return self._parse(referencia, response.json())

    def consultar(self, referencia: str) -> ResultadoFiscal:
        response = self.client.get(f"/v2/nfce/{referencia}")
        return self._parse(referencia, response.json())

    def cancelar(self, referencia: str, motivo: str) -> ResultadoFiscal:
        response = self.client.delete(f"/v2/nfce/{referencia}", json={"justificativa": motivo})
        return self._parse(referencia, response.json())

    @staticmethod
    def _parse(referencia: str, data: dict) -> ResultadoFiscal:
        status = STATUS_MAP.get(data.get("status"), "processando")
        return ResultadoFiscal(
            referencia=referencia,
            status=status,
            numero=data.get("numero"),
            serie=data.get("serie"),
            chave_acesso=data.get("chave_nfe"),
            protocolo=data.get("protocolo_autorizacao"),
            url_danfe=data.get("caminho_danfe") or data.get("url_danfe"),
            url_xml=data.get("caminho_xml_nota_fiscal") or data.get("url_xml"),
            mensagem_erro=data.get("mensagem_sefaz"),
        )
```

**Important note for whoever executes this task:** the exact JSON field names above (`icms_situacao_tributaria`, `caminho_danfe`, `mensagem_sefaz`, etc.) are based on the general shape of the Focus NFe API from prior knowledge, not a live fetch of their current docs (no network access was available while writing this plan). Before connecting to the real Focus NFe sandbox in Task 11, diff this payload against `https://docs.focusnfe.com.br/api/nfce/` and adjust field names in `montar_payload` and `_parse` if they've changed — the tests in this task only verify that our own code maps request/response shapes correctly, not that Focus NFe's real API matches these exact names.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_focus_nfe.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/models/nota_fiscal.py app/services/fiscal app/models/__init__.py tests/test_focus_nfe.py
git commit -m "feat: add FiscalProvider abstraction with Focus NFe implementation"
```

---

### Task 9: Wire fiscal emission into the sale flow

**Files:**
- Create: `app/dependencies.py`
- Create: `app/services/notas_service.py`
- Create: `app/routers/notas_router.py`
- Create: `app/templates/vendas/nota.html`
- Modify: `app/main.py`
- Test: `tests/test_notas_router.py`

**Interfaces:**
- Consumes: `app.services.fiscal.base.FiscalProvider`, `app.services.fiscal.focus_nfe.FocusNFeProvider`, `app.models.NotaFiscal` (Task 8).
- Produces: `app.dependencies.get_fiscal_provider() -> FiscalProvider` (FastAPI dependency, overridden in tests with a fake provider). `app.services.notas_service.emitir_nota(db, venda_id, provider) -> NotaFiscal`, `.consultar_nota(db, venda_id, provider) -> NotaFiscal`, `.cancelar_nota(db, venda_id, motivo, provider) -> NotaFiscal`. Routes: `GET /vendas/{id}/nota`, `POST /vendas/{id}/nota/emitir`, `POST /vendas/{id}/nota/consultar`, `POST /vendas/{id}/nota/cancelar`.

- [ ] **Step 1: Write failing router tests using a fake provider**

`tests/test_notas_router.py`:

```python
from decimal import Decimal

import pytest

from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.main import app
from app.services.fiscal.base import FiscalProvider, ResultadoFiscal
from app.services import clientes_service, produtos_service, vendas_service


class FiscalProviderFalso(FiscalProvider):
    def __init__(self):
        self.emitidas = []
        self.canceladas = []

    def emitir(self, venda):
        self.emitidas.append(venda.id)
        return ResultadoFiscal(
            referencia=f"venda-{venda.id}",
            status="autorizada",
            numero="1",
            serie="1",
            chave_acesso="1" * 44,
            protocolo="abc123",
            url_danfe="https://exemplo.com/danfe/1",
        )

    def consultar(self, referencia):
        return ResultadoFiscal(referencia=referencia, status="autorizada", numero="1")

    def cancelar(self, referencia, motivo):
        self.canceladas.append((referencia, motivo))
        return ResultadoFiscal(referencia=referencia, status="cancelada")


@pytest.fixture()
def venda_paga(db_session):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal("10.00"), estoque_atual=Decimal("5"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    return venda


@pytest.fixture()
def authed_client_com_provider_falso(authed_client, db_session):
    provider_falso = FiscalProviderFalso()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_fiscal_provider] = lambda: provider_falso
    yield authed_client, provider_falso
    del app.dependency_overrides[get_fiscal_provider]


def test_emitir_nota_grava_dados_retornados_pelo_provedor(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso

    response = client.post(f"/vendas/{venda_paga.id}/nota/emitir", follow_redirects=False)

    assert response.status_code == 303
    assert provider_falso.emitidas == [venda_paga.id]

    pagina = client.get(f"/vendas/{venda_paga.id}/nota")
    assert "autorizada" in pagina.text
    assert "https://exemplo.com/danfe/1" in pagina.text


def test_cancelar_nota_chama_provedor_com_motivo(authed_client_com_provider_falso, venda_paga):
    client, provider_falso = authed_client_com_provider_falso
    client.post(f"/vendas/{venda_paga.id}/nota/emitir")

    response = client.post(
        f"/vendas/{venda_paga.id}/nota/cancelar",
        data={"motivo": "Erro de digitação"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert provider_falso.canceladas == [(f"venda-{venda_paga.id}", "Erro de digitação")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notas_router.py -v`
Expected: FAIL — `app.dependencies` module not found, no `/vendas/{id}/nota` routes registered.

- [ ] **Step 3: Create `app/dependencies.py`**

```python
from app.services.fiscal.base import FiscalProvider
from app.services.fiscal.focus_nfe import FocusNFeProvider


def get_fiscal_provider() -> FiscalProvider:
    return FocusNFeProvider()
```

- [ ] **Step 4: Create `app/services/notas_service.py`**

```python
from sqlalchemy.orm import Session

from app.models.nota_fiscal import NotaFiscal, StatusNota
from app.models.venda import Venda
from app.services.fiscal.base import FiscalProvider


def emitir_nota(db: Session, venda_id: int, provider: FiscalProvider) -> NotaFiscal:
    venda = db.get(Venda, venda_id)
    if venda is None:
        raise ValueError("Venda não encontrada")

    resultado = provider.emitir(venda)

    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        nota = NotaFiscal(venda_id=venda_id, referencia=resultado.referencia)
        db.add(nota)

    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def consultar_nota(db: Session, venda_id: int, provider: FiscalProvider) -> NotaFiscal:
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        raise ValueError("Nota fiscal não encontrada para esta venda")

    resultado = provider.consultar(nota.referencia)
    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def cancelar_nota(db: Session, venda_id: int, motivo: str, provider: FiscalProvider) -> NotaFiscal:
    nota = db.query(NotaFiscal).filter(NotaFiscal.venda_id == venda_id).first()
    if nota is None:
        raise ValueError("Nota fiscal não encontrada para esta venda")

    resultado = provider.cancelar(nota.referencia, motivo)
    _aplicar_resultado(nota, resultado)
    db.commit()
    db.refresh(nota)
    return nota


def _aplicar_resultado(nota: NotaFiscal, resultado) -> None:
    nota.referencia = resultado.referencia
    nota.status = StatusNota(resultado.status)
    nota.numero = resultado.numero
    nota.serie = resultado.serie
    nota.chave_acesso = resultado.chave_acesso
    nota.protocolo = resultado.protocolo
    nota.url_danfe = resultado.url_danfe
    nota.url_xml = resultado.url_xml
    nota.mensagem_erro = resultado.mensagem_erro
```

- [ ] **Step 5: Create `app/routers/notas_router.py`**

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.dependencies import get_fiscal_provider
from app.models.nota_fiscal import NotaFiscal
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
    return templates.TemplateResponse("vendas/nota.html", {"request": request, "venda": venda, "nota": nota})


@router.post("/{venda_id}/nota/emitir")
def emitir(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    notas_service.emitir_nota(db, venda_id, provider)
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)


@router.post("/{venda_id}/nota/consultar")
def consultar(
    venda_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    notas_service.consultar_nota(db, venda_id, provider)
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)


@router.post("/{venda_id}/nota/cancelar")
def cancelar(
    venda_id: int,
    motivo: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    provider: FiscalProvider = Depends(get_fiscal_provider),
):
    notas_service.cancelar_nota(db, venda_id, motivo, provider)
    return RedirectResponse(url=f"/vendas/{venda_id}/nota", status_code=303)
```

- [ ] **Step 6: Create `app/templates/vendas/nota.html`**

```html
{% extends "base.html" %}
{% block title %}Nota fiscal - Orçamento {{ venda.numero_orcamento }}{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-4">Nota fiscal — Orçamento nº {{ venda.numero_orcamento }}</h1>

{% if nota is none %}
<p class="mb-4">Nenhuma nota fiscal emitida para esta venda ainda.</p>
<form method="post" action="/vendas/{{ venda.id }}/nota/emitir">
    <button type="submit" class="bg-emerald-700 text-white px-4 py-2 rounded">Gerar Cupom Fiscal</button>
</form>
{% else %}
<p class="mb-2">Status: <strong>{{ nota.status.value }}</strong></p>
{% if nota.mensagem_erro %}
<p class="text-red-600 mb-2">{{ nota.mensagem_erro }}</p>
{% endif %}
{% if nota.chave_acesso %}
<p class="mb-2">Chave de acesso: {{ nota.chave_acesso }}</p>
{% endif %}

<div class="flex gap-2 mt-4">
    <form method="post" action="/vendas/{{ venda.id }}/nota/consultar">
        <button type="submit" class="bg-slate-700 text-white px-4 py-2 rounded">Atualizar status</button>
    </form>
    {% if nota.url_danfe %}
    <a href="{{ nota.url_danfe }}" target="_blank" class="bg-slate-800 text-white px-4 py-2 rounded">Imprimir cupom</a>
    {% endif %}
    {% if nota.status.value == "autorizada" %}
    <form method="post" action="/vendas/{{ venda.id }}/nota/cancelar" onsubmit="return confirm('Cancelar esta nota fiscal?');">
        <input type="hidden" name="motivo" value="Cancelamento solicitado pelo estabelecimento">
        <button type="submit" class="bg-red-700 text-white px-4 py-2 rounded">Cancelar nota</button>
    </form>
    {% endif %}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 7: Modify `app/main.py`** — register the fiscal notes router

```python
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
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 9: Commit**

```bash
git add app/dependencies.py app/services/notas_service.py app/routers/notas_router.py app/templates/vendas/nota.html app/main.py tests/test_notas_router.py
git commit -m "feat: wire fiscal emission, status refresh, and cancellation into the sale flow"
```

---

### Task 10: Dashboard — today's sales

**Files:**
- Create: `app/services/dashboard_service.py`
- Modify: `app/routers/dashboard_router.py`
- Modify: `app/templates/dashboard.html`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `app.models.Venda`, `app.models.venda.StatusVenda` (Task 6).
- Produces: `app.services.dashboard_service.vendas_do_dia(db, dia=None) -> list[Venda]`, `.total_vendido_no_dia(db, dia=None) -> Decimal`. `GET /` now shows today's paid sales and a link to start a new sale.

- [ ] **Step 1: Write failing test for the dashboard service**

`tests/test_dashboard.py`:

```python
from datetime import date, timedelta
from decimal import Decimal

from app.services import clientes_service, dashboard_service, parcelas_service, produtos_service, vendas_service


def _venda_paga(db_session, preco="10.00"):
    cliente = clientes_service.garantir_consumidor_final(db_session)
    produto = produtos_service.criar_produto(
        db_session, codigo_interno="1", nome="Lanche", categoria_nome="Diversos",
        ncm="21069090", unidade="UN", preco_venda=Decimal(preco), estoque_atual=Decimal("10"),
    )
    venda = vendas_service.criar_venda(db_session, cliente.id)
    vendas_service.adicionar_item(db_session, venda.id, produto.id, Decimal("1"))
    parcelas_service.confirmar_venda(db_session, venda.id, Decimal(preco))
    return venda


def test_vendas_do_dia_retorna_apenas_vendas_pagas_de_hoje(db_session):
    venda_hoje = _venda_paga(db_session, preco="10.00")
    venda_antiga = _venda_paga(db_session, preco="20.00")
    venda_antiga.data_venda = venda_antiga.data_venda - timedelta(days=2)
    db_session.commit()

    resultado = dashboard_service.vendas_do_dia(db_session)

    ids = [venda.id for venda in resultado]
    assert venda_hoje.id in ids
    assert venda_antiga.id not in ids


def test_total_vendido_no_dia_soma_vendas_pagas(db_session):
    _venda_paga(db_session, preco="10.00")
    _venda_paga(db_session, preco="15.00")

    total = dashboard_service.total_vendido_no_dia(db_session)

    assert total == Decimal("25.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL — `app.services.dashboard_service` not found.

- [ ] **Step 3: Create `app/services/dashboard_service.py`**

```python
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.venda import StatusVenda, Venda


def vendas_do_dia(db: Session, dia: date | None = None) -> list[Venda]:
    dia = dia or date.today()
    inicio = datetime.combine(dia, time.min)
    fim = datetime.combine(dia, time.max)
    return (
        db.query(Venda)
        .filter(Venda.data_venda >= inicio, Venda.data_venda <= fim)
        .filter(Venda.status == StatusVenda.PAGO)
        .order_by(Venda.data_venda.desc())
        .all()
    )


def total_vendido_no_dia(db: Session, dia: date | None = None) -> Decimal:
    vendas = vendas_do_dia(db, dia)
    return sum((venda.valor_total for venda in vendas), Decimal("0"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 5: Modify `app/routers/dashboard_router.py`**

```python
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
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "usuario": usuario, "vendas": vendas, "total": total}
    )
```

- [ ] **Step 6: Modify `app/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Painel - Nana Lanches{% endblock %}
{% block content %}
<h1 class="text-2xl font-bold mb-1">Bem-vindo, {{ usuario.username }}</h1>
<p class="text-slate-600 mb-6">Vendas de hoje: {{ vendas|length }} — Total: R$ {{ "%.2f"|format(total) }}</p>

<a href="/vendas/nova" class="inline-block mb-4 bg-emerald-700 text-white px-4 py-2 rounded">+ Nova Venda</a>

<table class="w-full bg-white rounded shadow overflow-hidden">
    <thead class="bg-slate-100 text-left">
        <tr>
            <th class="p-2">Orçamento</th>
            <th class="p-2">Cliente</th>
            <th class="p-2">Hora</th>
            <th class="p-2">Total</th>
        </tr>
    </thead>
    <tbody>
        {% for venda in vendas %}
        <tr class="border-t">
            <td class="p-2"><a class="underline" href="/vendas/{{ venda.id }}">{{ venda.numero_orcamento }}</a></td>
            <td class="p-2">{{ venda.cliente.nome }}</td>
            <td class="p-2">{{ venda.data_venda.strftime("%H:%M") }}</td>
            <td class="p-2">R$ {{ "%.2f"|format(venda.valor_total) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 7: Run all tests to verify everything still passes**

Run: `pytest -v`
Expected: PASS (all tests)

- [ ] **Step 8: Commit**

```bash
git add app/services/dashboard_service.py app/routers/dashboard_router.py app/templates/dashboard.html tests/test_dashboard.py
git commit -m "feat: show today's paid sales and total on the dashboard"
```

---

### Task 11: Seed script, Alembic migration, and deployment README

**Files:**
- Modify: `app/seed.py`
- Create: `migrations/env.py` (via `alembic init`, then edited)
- Create: `README.md`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `app.auth.hash_senha`, `app.models.Usuario`, `app.services.clientes_service.garantir_consumidor_final` (Tasks 3, 5).
- Produces: `app.seed.criar_usuario_admin(db, username, senha) -> Usuario` (idempotent), `app.seed.seed_inicial(db, admin_username, admin_senha) -> None`.

- [ ] **Step 1: Write failing tests for the seed script**

`tests/test_seed.py`:

```python
from app.models.cliente import Cliente
from app.seed import criar_usuario_admin, seed_inicial


def test_criar_usuario_admin_e_idempotente(db_session):
    usuario1 = criar_usuario_admin(db_session, "pai", "senha123")
    usuario2 = criar_usuario_admin(db_session, "pai", "outrasenha")

    assert usuario1.id == usuario2.id


def test_seed_inicial_cria_admin_e_consumidor_final(db_session):
    seed_inicial(db_session, "pai", "senha123")

    consumidor = db_session.query(Cliente).filter(Cliente.consumidor_final.is_(True)).first()
    assert consumidor is not None
    assert consumidor.nome == "AO CONSUMIDOR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_seed.py -v`
Expected: FAIL — `seed_inicial` not defined in `app.seed`.

- [ ] **Step 3: Modify `app/seed.py`**

```python
from sqlalchemy.orm import Session

from app.auth import hash_senha
from app.models.usuario import Usuario
from app.services.clientes_service import garantir_consumidor_final


def criar_usuario_admin(db: Session, username: str, senha: str) -> Usuario:
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return existente
    usuario = Usuario(username=username, senha_hash=hash_senha(senha), ativo=True)
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def seed_inicial(db: Session, admin_username: str, admin_senha: str) -> None:
    criar_usuario_admin(db, admin_username, admin_senha)
    garantir_consumidor_final(db)


if __name__ == "__main__":
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        username = input("Usuário admin: ")
        senha = input("Senha: ")
        seed_inicial(db, username, senha)
        print("Dados iniciais criados com sucesso.")
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_seed.py -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite one last time**

Run: `pytest -v`
Expected: PASS (all tests in the project)

- [ ] **Step 6: Initialize Alembic**

Run: `alembic init migrations`

This creates `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/`, and `alembic.ini` in the project root.

- [ ] **Step 7: Replace the generated `migrations/env.py`**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401 -- registers all models on Base.metadata
from app.config import settings
from app.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 8: Create the MySQL database and user, and fill in `.env`**

This step requires real access to the MySQL server at `SEU_SERVIDOR_MYSQL:3306` and cannot be done from this plan alone — it's an operational step for whoever has those credentials:

1. Copy `.env.example` to `.env`.
2. Connect to the MySQL server and run:
   ```sql
   CREATE DATABASE nana_lanches CHARACTER SET utf8mb4;
   CREATE USER 'nana_lanches_user'@'%' IDENTIFIED BY 'uma-senha-forte-aqui';
   GRANT ALL PRIVILEGES ON nana_lanches.* TO 'nana_lanches_user'@'%';
   FLUSH PRIVILEGES;
   ```
3. Fill `DB_PASSWORD` in `.env` with that same password, and set `SECRET_KEY` to a long random string.

- [ ] **Step 9: Generate and apply the initial migration**

Run: `alembic revision --autogenerate -m "schema inicial"`

Review the generated file under `migrations/versions/` — it should create tables `usuarios`, `categorias`, `produtos`, `clientes`, `vendas`, `venda_itens`, `parcelas`, `notas_fiscais`. Then apply it:

Run: `alembic upgrade head`

- [ ] **Step 10: Seed the admin user and default customer**

Run: `python -m app.seed` and follow the prompts to set the admin username/password for the father.

- [ ] **Step 11: Create `README.md`**

```markdown
# Nana Lanches — Sistema de Vendas e Nota Fiscal

## Requisitos
- Python 3.12+
- Acesso ao servidor MySQL (host `SEU_SERVIDOR_MYSQL`, porta `3306`)
- Conta na Focus NFe (ambiente de homologação para testes, produção para notas reais)

## Configuração inicial

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Copie `.env.example` para `.env` e preencha:
   - `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`: banco `nana_lanches` e usuário
     `nana_lanches_user` criados no servidor MySQL informado.
   - `SECRET_KEY`: qualquer texto aleatório longo (assina a sessão de login).
   - `FOCUS_NFE_TOKEN`: token da conta Focus NFe (comece pelo ambiente de
     homologação, que é gratuito).
   - `FOCUS_NFE_AMBIENTE`: `homologacao` para testes, `producao` para notas reais.
3. Aplique as migrações no banco:
   ```bash
   alembic upgrade head
   ```
4. Crie o usuário administrador e o cliente "Consumidor Final":
   ```bash
   python -m app.seed
   ```
5. Rode o servidor:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
6. Acesse `http://localhost:8000` (ou `http://<ip-do-computador>:8000` de outro
   dispositivo na mesma rede Wi-Fi, como um tablet no balcão).

## Antes de emitir notas reais

- Teste a emissão completa no ambiente de homologação da Focus NFe primeiro —
  isso não gera nota fiscal válida, só simula.
- Os nomes de campos usados na integração (`app/services/fiscal/focus_nfe.py`)
  foram montados a partir do conhecimento geral da API da Focus NFe, sem
  acesso à documentação ao vivo no momento em que este sistema foi escrito.
  Antes de ligar em produção, confira o payload de emissão contra a
  documentação atual em `https://docs.focusnfe.com.br/api/nfce/` e ajuste os
  nomes de campo em `montar_payload`/`_parse` caso tenham mudado.
- Confirme o NCM correto de cada categoria de produto com o contador do
  restaurante — os valores usados como sugestão no cadastro (ex.: água
  mineral `22011000`) vieram do sistema anterior e não substituem orientação
  contábil.

## Rodando os testes

```bash
pytest
```

Os testes usam um banco SQLite em memória — não é necessário acesso ao MySQL
real nem à Focus NFe para rodá-los.
```

- [ ] **Step 12: Commit**

```bash
git add app/seed.py migrations alembic.ini README.md tests/test_seed.py
git commit -m "feat: add idempotent seed script, Alembic migration setup, and deployment README"
```

---

## Self-Review Notes

- **Spec coverage:** login/session (Task 3), product catalog grouped by category (Task 4), PF/PJ customers with default Consumidor Final (Task 5), sale creation with item search (Task 6), payment + installments + stock deduction (Task 7), `FiscalProvider`/`FocusNFeProvider` abstraction (Task 8), emit/consult/cancel wired into the UI with provider-returned DANFE for printing (Task 9), daily sales dashboard (Task 10), MySQL migration + seed + setup docs (Task 11). All spec sections are covered.
- **Placeholder scan:** no TBD/TODO markers; the one caveat (Focus NFe field names need verification against live docs) is called out explicitly as an action item with a concrete fallback already implemented, not left blank.
- **Type consistency:** `FiscalProvider.emitir/consultar/cancelar` signatures in Task 8 match exactly what `notas_service` (Task 9) and `FocusNFeProvider` use. `Venda.status`/`StatusVenda` enum values (`orcamento`, `pago`, `cancelado`) are consistent across Tasks 6, 7, 9, 10. `Cliente.consumidor_final` flag introduced in Task 5 is used identically in Tasks 6, 8, and 11.

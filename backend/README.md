# GR Backend

Plataforma de inteligencia de dados para FIDCs. Backend FastAPI + PostgreSQL, multi-tenant, modular.

## Stack

- Python 3.11+
- FastAPI + SQLAlchemy async (asyncpg)
- Pydantic v2 + pydantic-settings
- Alembic (migrations)
- Ruff (lint + format) + pytest
- uv (package manager)
- PostgreSQL (gr_db no servidor Postgres da VM)
- Uvicorn + systemd (sem Docker)

## Setup local (Windows)

```bash
cd backend
uv venv --python 3.13
uv sync --extra dev
cp .env.example .env   # ajustar DATABASE_URL e JWT_SECRET_KEY
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

API sobe em http://localhost:8000. Docs automaticos em http://localhost:8000/docs.

## Testes

Pytest roda contra um banco **dedicado** (`gr_db_test`), nao contra `gr_db`. Existe um guard em [tests/conftest.py](./tests/conftest.py) que aborta se `DATABASE_URL` nao tiver `test` no nome — protege producao de poluicao por testes.

### Setup inicial (uma vez por ambiente)

1. Criar o banco com role `gr_app` como owner:

   ```python
   # via asyncpg (Windows, sem psql no PATH)
   uv run python -c "
   import asyncio, asyncpg
   asyncio.run(asyncpg.connect(
       host='192.168.100.27', user='gr_app', password='SENHA',
       database='postgres'
   ).close()) if False else None
   "
   # ou via psql se disponivel:
   #   psql -h 192.168.100.27 -U gr_app -d postgres -c \
   #     "CREATE DATABASE gr_db_test OWNER gr_app"
   ```

2. Aplicar migrations no banco de teste:

   ```bash
   DATABASE_URL=postgresql+asyncpg://gr_app:SENHA@192.168.100.27:5432/gr_db_test \
     uv run alembic upgrade head
   ```

3. Configurar `postgres_fdw` (CVM benchmark) + seed `source_catalog`. Precisa de **superuser** do cluster (peer auth via SSH na VM **ou** senha de algum role com `rolsuper=true`):

   ```bash
   uv run python scripts/setup_test_db_fdw.py
   ```

   O script pede o role superuser (default `postgres`) e a senha via `getpass`. E idempotente — pode reexecutar.

### Rodar pytest

```bash
DATABASE_URL=postgresql+asyncpg://gr_app:SENHA@192.168.100.27:5432/gr_db_test \
  uv run pytest
```

**Como funciona o isolamento**: a fixture autouse session-scoped em [tests/conftest.py](./tests/conftest.py) faz `TRUNCATE` de todas as tabelas do schema `public` no inicio de cada session, **exceto** `alembic_version` e `source_catalog` (preservadas como schema/seed).

## Deploy (VM Linux)

Ver [DEPLOY.md](./DEPLOY.md).

## Arquitetura

Ver `C:\app_gr\CLAUDE.md` (secoes 9-18) para governanca completa: multi-tenant, modularizacao, RBAC, adapters, proveniencia, deploy, checklist.

Sumario:

- `app/core/` — config, database, security, enums, middlewares (cross-cutting)
- `app/shared/` — shared kernel: identity, audit_log, catalog, auditable mixin
- `app/modules/` — 8 bounded contexts: bi, cadastros, operacoes, controladoria, risco, integracoes, laboratorio, admin
- `app/api/v1/` — roteamento HTTP + schemas Pydantic
- `app/warehouse/` — modelo canonico populado pelos adapters
- `alembic/` — migrations

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

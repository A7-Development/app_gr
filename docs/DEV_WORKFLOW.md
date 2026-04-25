# Dev Workflow e Deploy

Referência detalhada para §16 do CLAUDE.md.

## Desenvolvimento local (Windows)

```
C:\app_gr\backend\
├── .venv\                    # venv local (não commitar)
├── .env                      # config local (não commitar)
├── pyproject.toml            # ou requirements.txt
├── alembic.ini
├── alembic\versions\
└── app\...
```

- Python 3.11+ instalado
- Postgres local (ou remoto via SSH tunnel para VM) com database `gr_db_dev`
- `.env` aponta para Postgres local
- Rodar: `source .venv/Scripts/activate && uvicorn app.main:app --reload`

## Produção (VM Linux Ubuntu/Debian)

```
/opt/app_gr/backend/
├── .venv/
├── .env                      # config prod (chmod 600)
├── app/...
└── alembic/...
```

- Systemd service: `/etc/systemd/system/gr-api.service`
- Rodar: `systemctl start gr-api`
- Postgres na VM: database `gr_db` (separada do banco do app_controladoria)

## Deploy (manual inicial)

```bash
ssh vm
cd /opt/app_gr/backend
git pull
source .venv/bin/activate
pip install -r requirements.txt  # ou poetry install
alembic upgrade head
sudo systemctl restart gr-api
```

CI via GitHub Actions roda lint + pytest em cada push.

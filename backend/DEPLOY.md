# Deploy do GR Backend na VM

Ambiente de producao: **VM Linux Ubuntu/Debian**, sem Docker, com Postgres ja rodando.

## Pre-requisitos (apenas no primeiro deploy)

Na VM, como root ou sudo:

```bash
# 1. Python 3.11+
apt update
apt install -y python3.11 python3.11-venv python3-pip
# (Ou compilar 3.13 via pyenv, se preferir)

# 2. Usuario dedicado ao servico (nao-root)
useradd -r -m -d /opt/app_gr -s /bin/bash app_gr

# 3. Pastas de log
mkdir -p /var/log/gr-api
chown app_gr:app_gr /var/log/gr-api

# 4. Driver ODBC Microsoft (usado pelo adapter Bitfin a partir do Sprint 2)
# https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
# (seguir doc oficial para Debian/Ubuntu)

# 5. Clonar o repo
su - app_gr
git clone <url-do-repo> /opt/app_gr
cd /opt/app_gr/backend

# 6. Venv + deps (usando pip, pois uv pode nao estar instalado na VM)
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'

# 7. .env de producao (chmod 600)
cp .env.example .env
nano .env   # ajustar DATABASE_URL (gr_db), JWT_SECRET_KEY, etc
chmod 600 .env

# 8. Migrations + seed
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed

# 9. Systemd unit (como root)
exit   # voltar para root
cp /opt/app_gr/backend/deploy/gr-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable gr-api
systemctl start gr-api
systemctl status gr-api
```

## Deploy incremental (comando do dia-a-dia)

Apos alteracoes committadas no repo, na VM:

```bash
sudo -u app_gr bash -c '
    cd /opt/app_gr/backend
    git pull
    .venv/bin/pip install -e ".[dev]"
    .venv/bin/alembic upgrade head
'
sudo systemctl restart gr-api
sudo systemctl status gr-api
```

## Reverse proxy (recomendado)

A API sobe em `127.0.0.1:8000`. Coloque um nginx na frente com TLS:

```nginx
server {
    listen 443 ssl http2;
    server_name api.gr.a7credit.com.br;

    ssl_certificate     /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Troubleshooting

### Ver logs
```bash
journalctl -u gr-api -f
tail -f /var/log/gr-api/stderr.log
```

### Reiniciar
```bash
sudo systemctl restart gr-api
```

### Rollback de migration
```bash
sudo -u app_gr /opt/app_gr/backend/.venv/bin/alembic downgrade -1
```

### Verificar conexao ao Postgres
```bash
sudo -u app_gr /opt/app_gr/backend/.venv/bin/python -c "
import asyncio
from app.core.database import engine
async def check():
    async with engine.connect() as conn:
        r = await conn.execute('SELECT 1')
        print('DB OK:', r.scalar())
asyncio.run(check())
"
```

## Backups

- Postgres: usar `pg_dump gr_db` em rotina cron (independente do app_controladoria).
- `.env`: manter copia segura fora da VM (sem commitar).

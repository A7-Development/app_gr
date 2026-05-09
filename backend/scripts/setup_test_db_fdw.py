"""Setup do gr_db_test: postgres_fdw + seed source_catalog (espelha prod).

Faz duas coisas necessarias para os testes funcionarem:

1. **postgres_fdw**: configura o FDW que liga `gr_db_test` ao banco publico
   `cvm_benchmark` (mesmo cluster), espelhando o setup de prod (CLAUDE.md
   secao 13.1). Sem isso, testes de BI/benchmark (`cvm_remote.*`) falham.

2. **source_catalog**: copia as linhas de `source_catalog` de prod para
   `gr_db_test`. Tabela global (sem tenant_id) seedada via migration
   `b1d9a2f7c4e8` em prod, mas nao re-seedada automaticamente em outros
   bancos. Sem ela, testes que criam `tenant_source_config` quebram com
   ForeignKeyViolationError.

Operacao unica — depois de rodar uma vez por ambiente, nunca mais.
Reexecutar e idempotente (CREATE ... IF NOT EXISTS, ON CONFLICT DO NOTHING).

Pre-requisitos:
- gr_db_test ja criado (CREATE DATABASE gr_db_test OWNER gr_app)
- alembic upgrade head ja rodado em gr_db_test
- senha de um role superuser do cluster (pedida via getpass)

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/setup_test_db_fdw.py
"""

from __future__ import annotations

import asyncio
import getpass
import re
import sys
from pathlib import Path

import asyncpg


def _read_db_url() -> tuple[str, str, str, int]:
    """Le DATABASE_URL do .env e devolve (user, pwd, host, port)."""
    env = Path(__file__).resolve().parent.parent / ".env"
    text = env.read_text(encoding="utf-8")
    m = re.search(r"^DATABASE_URL=(.+)$", text, re.MULTILINE)
    if not m:
        raise RuntimeError(".env nao tem DATABASE_URL")
    url = m.group(1).strip().strip('"')
    m = re.match(
        r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:/]+):?(\d*)/(\w+)", url
    )
    if not m:
        raise RuntimeError(f"DATABASE_URL com formato inesperado: {url}")
    user, pwd, host, port_s, _ = m.groups()
    return user, pwd, host, int(port_s) if port_s else 5432


async def _read_etl_cvm_credentials(
    *, host: str, port: int, app_user: str, app_pwd: str
) -> tuple[str, str]:
    """Le user/senha do user mapping etl_cvm em prod (gr_db).

    Funciona porque `gr_app` (owner do mapping) consegue ver `umoptions`.
    """
    conn = await asyncpg.connect(
        host=host, port=port, user=app_user, password=app_pwd, database="gr_db"
    )
    try:
        row = await conn.fetchrow(
            """
            SELECT umoptions FROM pg_user_mappings
            WHERE usename = $1 AND srvname = 'cvm_benchmark_server'
            """,
            app_user,
        )
        if not row:
            raise RuntimeError(
                "user mapping etl_cvm nao existe em gr_db. "
                "Setup do FDW em prod parece estar incompleto."
            )
        opts = {k: v for k, v in (o.split("=", 1) for o in row["umoptions"])}
        return opts["user"], opts["password"]
    finally:
        await conn.close()


async def _setup_fdw(
    *,
    host: str,
    port: int,
    su_user: str,
    su_password: str,
    app_user: str,
    etl_user: str,
    etl_pass: str,
) -> None:
    """Configura tudo no gr_db_test conectado como superuser informado."""
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=su_user,
        password=su_password,
        database="gr_db_test",
    )
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgres_fdw")
        print("[ok] extension postgres_fdw")

        await conn.execute(
            """
            CREATE SERVER IF NOT EXISTS cvm_benchmark_server
            FOREIGN DATA WRAPPER postgres_fdw
            OPTIONS (host '127.0.0.1', port '5432',
                     dbname 'cvm_benchmark', fetch_size '10000')
            """
        )
        print("[ok] server cvm_benchmark_server")

        try:
            await conn.execute(
                f"""
                CREATE USER MAPPING FOR {app_user}
                SERVER cvm_benchmark_server
                OPTIONS (user '{etl_user}', password '{etl_pass}')
                """
            )
            print(f"[ok] user mapping {app_user} -> {etl_user}")
        except asyncpg.exceptions.DuplicateObjectError:
            print(f"[ok] user mapping {app_user} -> {etl_user} (ja existia)")

        await conn.execute("CREATE SCHEMA IF NOT EXISTS cvm_remote")
        await conn.execute(f"GRANT USAGE ON SCHEMA cvm_remote TO {app_user}")
        print("[ok] schema cvm_remote (com GRANT USAGE)")

        # IMPORT FOREIGN SCHEMA usa o user mapping do role logado, nao do
        # app_user. Como estamos rodando como superuser (cursor_ro/postgres),
        # precisamos garantir mapping pra ele tambem antes do IMPORT.
        try:
            await conn.execute(
                f"""
                CREATE USER MAPPING FOR {su_user}
                SERVER cvm_benchmark_server
                OPTIONS (user '{etl_user}', password '{etl_pass}')
                """
            )
            print(f"[ok] user mapping {su_user} -> {etl_user}")
        except asyncpg.exceptions.DuplicateObjectError:
            print(f"[ok] user mapping {su_user} -> {etl_user} (ja existia)")

        try:
            await conn.execute(
                """
                IMPORT FOREIGN SCHEMA cvm
                FROM SERVER cvm_benchmark_server INTO cvm_remote
                """
            )
            print("[ok] import foreign schema cvm_benchmark.cvm")
        except asyncpg.exceptions.DuplicateTableError:
            print("[ok] foreign tables ja existiam")

        await conn.execute(
            f"GRANT SELECT ON ALL TABLES IN SCHEMA cvm_remote TO {app_user}"
        )
        print(f"[ok] grant SELECT em cvm_remote.* para {app_user}")

        cnt = await conn.fetchval(
            """
            SELECT COUNT(*) FROM information_schema.foreign_tables
            WHERE foreign_table_schema = 'cvm_remote'
            """
        )
        print(f"\n=> {cnt} foreign tables em gr_db_test.cvm_remote")
    finally:
        await conn.close()


async def _seed_source_catalog(
    *, host: str, port: int, app_user: str, app_pwd: str
) -> None:
    """Copia source_catalog de gr_db -> gr_db_test (idempotente)."""
    prod = await asyncpg.connect(
        host=host, port=port, user=app_user, password=app_pwd, database="gr_db"
    )
    try:
        rows = await prod.fetch("SELECT * FROM source_catalog ORDER BY source_type")
    finally:
        await prod.close()

    if not rows:
        print("[ok] source_catalog em prod esta vazio — nada para seedar")
        return

    cols = list(rows[0].keys())
    test = await asyncpg.connect(
        host=host, port=port, user=app_user, password=app_pwd, database="gr_db_test"
    )
    try:
        placeholders = ",".join(f"${i+1}" for i in range(len(cols)))
        sql = (
            f"INSERT INTO source_catalog ({','.join(cols)}) "
            f"VALUES ({placeholders}) ON CONFLICT (source_type) DO NOTHING"
        )
        for r in rows:
            await test.execute(sql, *[r[c] for c in cols])
        cnt = await test.fetchval("SELECT COUNT(*) FROM source_catalog")
        print(f"[ok] source_catalog em gr_db_test: {cnt} linhas")
    finally:
        await test.close()


async def main() -> int:
    app_user, app_pwd, host, port = _read_db_url()
    print(f"[info] cluster: {host}:{port}")
    print(f"[info] app role (.env): {app_user}")

    etl_user, etl_pass = await _read_etl_cvm_credentials(
        host=host, port=port, app_user=app_user, app_pwd=app_pwd
    )
    print(f"[info] credencial etl_cvm lida de gr_db (user='{etl_user}')")

    su_user = input(
        "\nRole superuser para CREATE EXTENSION [postgres]: "
    ).strip() or "postgres"
    su_password = getpass.getpass(f"Senha do role '{su_user}' em {host}: ")
    if not su_password:
        print("[abort] senha vazia")
        return 1

    print()
    await _setup_fdw(
        host=host,
        port=port,
        su_user=su_user,
        su_password=su_password,
        app_user=app_user,
        etl_user=etl_user,
        etl_pass=etl_pass,
    )

    print()
    await _seed_source_catalog(
        host=host, port=port, app_user=app_user, app_pwd=app_pwd
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

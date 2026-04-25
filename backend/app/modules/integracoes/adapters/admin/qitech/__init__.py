"""QiTech adapter — legacy Singulare portal API (bearer token).

QiTech e a Singulare renomeada. O portal legado continua respondendo em
`api-portal.singulare.com.br` e usa autenticacao por bearer token obtido
via `POST /v2/painel/token/api`. O token e reaproveitado nas chamadas
subsequentes ate expirar.

Multi-tenant: credenciais, base_url e ambiente vem de `tenant_source_config`
— zero hardcode. O cache de token e chaveado por (tenant_id, environment)
e jamais cruza fronteiras.

Arquitetura:
    config.py     — QiTechConfig: base_url + payload de credenciais por tenant.
    auth.py       — fetch_api_token + TokenCache (TTL por tenant).
    connection.py — build_async_client: httpx.Auth que injeta bearer e
                    retry automatico em 401.
    endpoints.py  — catalogo (path + metodo) dos endpoints em uso.
    adapter.py    — entrypoints adapter_ping / adapter_sync usados pelo
                    sync_runner.
    bootstrap.py  — CLI para sync manual.
    version.py    — ADAPTER_VERSION registrada em cada decision_log entry.
"""

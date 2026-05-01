"""ETL sincrono para a familia QiTech `/v2/bank-account/*`.

Cobre os 2 endpoints de conta-corrente bancaria da Singulare:
- GET /v2/bank-account/balance/{agencia}/{conta}/{data}             -> saldo
- GET /v2/bank-account/statement/{agencia}/{conta}/{inicio}/{fim}   -> extrato

Diferente da familia /netreport/* (data unica + tipo de mercado), aqui temos:
- Path com agencia + conta (vem de QiTechConfig.bank_accounts da UA)
- Saldo: data unica
- Extrato: periodo (data_inicial + data_final)
- CNPJ titular vem implicitamente da UA dona da credencial (NAO viaja no path)

Cada sync grava:
- raw em wh_qitech_raw_bank_account_balance / wh_qitech_raw_bank_account_statement
- canonico em wh_saldo_bancario_diario / wh_extrato_bancario
- decision_log via caller (ETL orchestrator ou REST endpoint)

Modelo igual a custodia.py -- GET sincrono retorna JSON imediatamente.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from app.modules.integracoes.adapters.admin.qitech.endpoints import (
    E_BANK_ACCOUNT_BALANCE,
    E_BANK_ACCOUNT_STATEMENT,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError

logger = logging.getLogger(__name__)


async def fetch_balance(
    *,
    client: httpx.AsyncClient,
    agencia: str,
    conta: str,
    data: date,
) -> tuple[Any, int]:
    """GET /v2/bank-account/balance/{agencia}/{conta}/{data}.

    Args:
        client: httpx.AsyncClient autenticado (vindo de build_async_client).
        agencia: codigo da agencia (string, ex.: "1"), literal no path.
        conta: numero da conta sem digito (string, ex.: "4532551"), literal no path.
        data: data de posicao (saldo de fechamento daquele dia).

    Returns:
        (body_json_or_none, http_status). Body pode ser dict ou None se nao-JSON.

    Raises:
        QiTechHttpError em 4xx/5xx com status_code preenchido. 400 com shape
        canonico de "sem dados" e tratado no caller (mapper) -- aqui ele sobe
        com status 400 para o caller distinguir de erro real.
    """
    path = E_BANK_ACCOUNT_BALANCE.path.format(
        agencia=agencia, conta=conta, data=data.isoformat()
    )
    return await _request_with_retry(client, E_BANK_ACCOUNT_BALANCE.method, path)


async def fetch_statement(
    *,
    client: httpx.AsyncClient,
    agencia: str,
    conta: str,
    inicio: date,
    fim: date,
) -> tuple[Any, int]:
    """GET /v2/bank-account/statement/{agencia}/{conta}/{inicio}/{fim}.

    Args:
        client: httpx.AsyncClient autenticado.
        agencia: codigo da agencia.
        conta: numero da conta sem digito.
        inicio: data inicial inclusiva do periodo.
        fim: data final inclusiva do periodo.

    Returns:
        (body_json_or_none, http_status).

    Raises:
        QiTechHttpError em 4xx/5xx (com excecao de 400 "sem dados" -- caller decide).
    """
    if fim < inicio:
        raise ValueError(
            f"periodo invalido: fim ({fim}) anterior a inicio ({inicio})"
        )
    path = E_BANK_ACCOUNT_STATEMENT.path.format(
        agencia=agencia,
        conta=conta,
        inicio=inicio.isoformat(),
        fim=fim.isoformat(),
    )
    return await _request_with_retry(client, E_BANK_ACCOUNT_STATEMENT.method, path)


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    path: str,
) -> tuple[Any, int]:
    """Faz a request com retry leve em timeout transitorio.

    Singulare apresenta hiccup esporadico (validado contra /netreport/* em
    2026-04-27); mesmo padrao aplicado aqui. Erros HTTP reais (4xx/5xx) NAO
    entram no retry -- sobem na primeira tentativa.

    Diferente do `reports.fetch_market_report`, aqui devolvemos `(body, status)`
    em vez de levantar 400 -- o caller (mapper / ETL) decide se 400 e "sem
    dados" (legitimo) ou erro real, porque o shape do payload de "sem dados"
    da familia /bank-account/ ainda nao foi observado em campo.
    """
    last_error: httpx.HTTPError | None = None
    resp: httpx.Response | None = None
    for attempt in range(2):
        try:
            resp = await client.request(method, path)
            last_error = None
            break
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_error = e
            if attempt == 0:
                logger.warning(
                    "qitech.bank_account: timeout em %s (%s); retry em 1s",
                    path,
                    type(e).__name__,
                )
                await asyncio.sleep(1.0)
                continue
        except httpx.HTTPError as e:
            last_error = e
            break

    if last_error is not None or resp is None:
        e = last_error
        raise QiTechHttpError(
            f"falha de rede em {method} {path}: {type(e).__name__}({e!r})",
            status_code=None,
            detail=f"{type(e).__name__}: {e!r}",
        ) from e

    # Erros >=500 ou 401/403/404 sao erro real. 400 sobe pro caller analisar
    # (a Singulare costuma usar 400 para "sem dados no periodo" com shape
    # canonico).
    if resp.status_code >= 500 or resp.status_code in (401, 403, 404):
        raise QiTechHttpError(
            f"QiTech devolveu {resp.status_code} em {method} {path}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )

    try:
        body = resp.json()
    except ValueError:
        body = None
    return body, resp.status_code

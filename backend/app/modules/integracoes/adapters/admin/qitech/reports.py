"""Report endpoints QiTech — camada fina de fetch tipada.

Cada funcao aqui mapeia 1:1 para um endpoint de `GET /netreport/report/*`
do portal QiTech/Singulare. Responsabilidades:

    1. Montar a URL a partir do template em `endpoints.py`.
    2. Chamar o client autenticado (x-api-key injetado pelo `_ApiKeyAuth`).
    3. Converter erros HTTP em `QiTechHttpError` com status_code + detail.
    4. Devolver o JSON bruto da QiTech. **Nao parseia** para modelo canonico
       — o mapping acontece em uma camada acima (etl.py, quando existir),
       para que cada tipo de relatorio decida como interpretar seu payload.

Multi-tenant: essas funcoes NAO conhecem tenant_id. Recebem `httpx.AsyncClient`
pronto. Quem monta o client (connection.build_async_client) e que carrega
a credencial do tenant correto — isolamento fica garantido la em cima.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx

from app.modules.integracoes.adapters.admin.qitech.endpoints import E_REPORT_MARKET
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError

logger = logging.getLogger(__name__)

# Catalogo de valores conhecidos para `tipo-de-mercado` no path do endpoint
# GET /v2/netreport/report/market/{tipo-de-mercado}/{data}.
#
# Valores sao literais do vendor QiTech/Singulare — viajam tal e qual no path.
# Adicionar aqui quando a QiTech documentar um novo tipo (com label PT para
# rastreabilidade). A funcao `fetch_market_report` aceita `str` e nao valida
# contra esta tupla — isso permite que configuracoes per-tenant experimentem
# valores novos sem exigir deploy; mas preferencialmente consuma daqui.
TIPOS_DE_MERCADO_CONHECIDOS: tuple[tuple[str, str], ...] = (
    # Carteiras / ativos.
    ("outros-fundos", "Outros fundos"),
    ("rf", "Renda fixa"),
    ("rv", "Renda variavel"),
    ("rv-opcoes", "RV opcoes"),
    ("rv-opcoes-flexiveis", "RV opcoes flexiveis"),
    ("rv-emprestimo-acoes", "RV emprestimo acoes"),
    (
        "rv-emprestimo-acoes-inadimplentes",
        "RV emprestimo acoes inadimplentes",
    ),
    ("rf-fidc", "RF FIDC"),
    ("rf-compromissadas", "RF compromissadas"),
    # Derivativos e cambio.
    ("futuros", "Futuros"),
    ("opcoes-futuro", "Opcoes futuro"),
    ("swap", "Swap"),
    ("termo", "Termo"),
    ("termo-rv", "Termo RV"),
    ("cambio", "Cambio"),
    # Tesouraria / contabeis.
    ("tesouraria", "Tesouraria"),
    ("conta-corrente", "Conta corrente"),
    ("cpr", "CPR (Contas a Pagar e Receber)"),
    ("demonstrativo-caixa", "Demonstrativo caixa"),
    ("outros-ativos", "Outros ativos"),
    ("outros-emprestimos", "Outros emprestimos"),
    # Relatorios agregados.
    ("rentabilidade", "Rentabilidade"),
    ("mec", "MEC (mapa evolutivo de cotas)"),
)

# Tupla so-de-codigos para iteracao rapida (ex.: sync_runner itera sobre
# tipos_de_mercado configurados pelo tenant).
TIPOS_DE_MERCADO: tuple[str, ...] = tuple(code for code, _ in TIPOS_DE_MERCADO_CONHECIDOS)


async def fetch_market_report(
    *,
    client: httpx.AsyncClient,
    tipo_de_mercado: str,
    posicao: date,
) -> Any:
    """GET /netreport/report/market/{tipo-de-mercado}/{data}.

    Retorna todos os ativos com quebra por carteira, filtrados pelo
    perfil de acesso do client_id autenticado.

    Args:
        client: client ja autenticado (vindo de `build_async_client`).
        tipo_de_mercado: identificador do mercado na QiTech (ex.: "outros-fundos",
            "renda-fixa"). Vai literal no path (hifen preservado).
        posicao: data de posicao que delimita o relatorio (tipicamente D-1).

    Returns:
        Estrutura JSON retornada pela QiTech — tipicamente lista de ativos ou
        objeto com lista aninhada. O shape nao e assumido aqui; o caller
        decide como interpretar.

    Raises:
        QiTechHttpError: 4xx/5xx, falha de rede, ou resposta nao-JSON.
    """
    path = E_REPORT_MARKET.path.format(
        tipo_de_mercado=tipo_de_mercado,
        data=posicao.isoformat(),
    )
    # Retry leve em timeout transitorio (mesmo padrao do auth._request_token).
    # Singulare apresenta hiccup esporadico nesses endpoints (validado
    # 2026-04-27 em loop de repopulacao). Erros HTTP reais (4xx/5xx) NAO
    # entram aqui — sao tratados depois da resposta.
    last_error: httpx.HTTPError | None = None
    resp: httpx.Response | None = None
    for attempt in range(2):
        try:
            resp = await client.request(E_REPORT_MARKET.method, path)
            last_error = None
            break
        except (httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_error = e
            if attempt == 0:
                logger.warning(
                    "qitech.reports: timeout transitorio em %s (%s); retry em 1s",
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
            f"falha de rede em {E_REPORT_MARKET.method} {path}: "
            f"{type(e).__name__}({e!r})",
            status_code=None,
            detail=f"{type(e).__name__}: {e!r}",
        ) from e

    # Caso especial da QiTech: HTTP 400 com body canonico de "sem dados".
    # Validado em 2026-04-24 contra varios tipos onde o tenant nao tem
    # portfolio (rv, futuros, swap, ...):
    #     {"relatorios": {}, "_links": {}, "message": "Nao ha resultados ..."}
    # Mesmo shape do 200, so vazio. E dado legitimo — NAO e erro. O ETL
    # precisa ver isso pra registrar "zero posicoes em X em Y/dia" (dado
    # diferente de "falha de integracao"). Status code 500 continua como
    # erro real, assim como 401/403 e 404.
    if resp.status_code == 400:
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and "relatórios" in body:
            return body
        # 400 sem shape canonico -> erro real.

    if resp.status_code >= 400:
        raise QiTechHttpError(
            f"QiTech devolveu {resp.status_code} em "
            f"{E_REPORT_MARKET.method} {path}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )

    try:
        return resp.json()
    except ValueError as e:
        raise QiTechHttpError(
            f"resposta nao-JSON em {E_REPORT_MARKET.method} {path}: "
            f"{resp.text[:500]}",
            status_code=resp.status_code,
            detail=str(e),
        ) from e

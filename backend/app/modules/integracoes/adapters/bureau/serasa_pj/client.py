"""Client de alto nivel — query_pj_analitico(cnpj) retorna payload bruto.

Este e o ponto de entrada do adapter para o caller (BureauQueryNode no
workflow do credito, ou um service do dominio). O contrato e simples:

    1. Caller chama `query_pj_analitico(tenant_id, environment, config, cnpj)`
    2. Client autentica, monta query, dispara GET.
    3. Retorna `BureauQueryResult` com:
        - `payload`: dict bruto da Serasa (vai pro raw layer do warehouse)
        - `requested_report`: o que pedimos
        - `actual_report_returned`: o que veio (para detectar downgrade)
        - `status_code`: HTTP status
        - `cost_center`: o valor que mandamos em X-Cost-Center (se algum)
        - `latency_ms`: tempo de chamada
        - `adapter_version`: para gravar em proveniencia

O client NAO toca em DB do GR. Quem grava bronze + chama mapper + grava
silver e o caller — mantem o adapter puro e testavel.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx

from app.core.enums import Environment
from app.modules.integracoes.adapters.bureau.serasa_pj.config import (
    SerasaPjConfig,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.endpoints import (
    E_BUSINESS_INFORMATION_REPORT,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.errors import (
    SerasaPjConfigError,
    SerasaPjHttpError,
    SerasaPjReciprocityDowngradeError,
)
from app.modules.integracoes.adapters.bureau.serasa_pj.version import (
    ADAPTER_VERSION,
)


@dataclass(frozen=True)
class BureauQueryResult:
    """Resultado de uma consulta Serasa PJ.

    O `payload` cru vai para `wh_serasa_pj_raw_relatorio` (bronze) e o
    mapper deriva `wh_serasa_pj_consulta` + tabelas filhas (silver).

    `actual_report_returned` distingue o relatorio recebido do solicitado
    quando ha downgrade silencioso por reciprocidade (CLAUDE.md / memoria
    Serasa). Se diferentes, o caller deve registrar ambos no decision_log.
    """

    payload: dict[str, Any]
    requested_report: str
    actual_report_returned: str
    status_code: int
    cost_center: str | None
    latency_ms: float
    adapter_version: str = ADAPTER_VERSION


def _strip_non_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _truncate_cost_center(value: str | None) -> str | None:
    """Serasa limita X-Cost-Center a 12 chars. Trunca + valida ASCII basico."""
    if not value:
        return None
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in "-_")
    return cleaned[:12] or None


def _encode_report_parameters(segment_code: str) -> str:
    """Codifica `reportParameters` no formato esperado pela Serasa.

    A Serasa aceita parametros adicionais (segmento, perfil de score, etc)
    via query param `reportParameters`, que carrega um JSON base64-encoded
    no formato:

        {"reportParameters": [{"name": "segmentCode", "value": "028"}]}

    Validado contra prod 2026-05-01 (codigo interno A7).
    """
    obj = {
        "reportParameters": [
            {"name": "segmentCode", "value": segment_code},
        ],
    }
    raw = json.dumps(obj, separators=(",", ":"))
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


async def query_pj_analitico(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: SerasaPjConfig,
    cnpj: str,
    report_type: str | None = None,
    cost_center: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    raise_on_downgrade: bool = False,
) -> BureauQueryResult:
    """Consulta o Business Information Report (PJ analitico) por CNPJ.

    Args:
        tenant_id: dono da credencial — chave do cache de token.
        environment: sandbox/UAT ou production.
        config: SerasaPjConfig materializado de tenant_source_config.
        cnpj: 14 digitos. Formato e normalizado (so digitos) antes de enviar.
        report_type: override do tipo de relatorio. Default vem de
            `config.default_report_type` (`RELATORIO_AVANCADO_PJ_ANALITICO`).
        cost_center: rotulo livre pra rastreio interno (ex.: `dossie_id`
            truncado). Vai em `X-Cost-Center`, max 12 chars — trunca se
            maior. Opcional.
        transport: MockTransport para tests.
        raise_on_downgrade: se True, levanta `SerasaPjReciprocityDowngradeError`
            quando `actual_report_returned` != `requested_report`. Default
            False — caller decide o que fazer com o downgrade silencioso.

    Returns:
        `BureauQueryResult` com payload bruto + metadados.

    Raises:
        SerasaPjConfigError: CNPJ invalido ou config sem credenciais.
        SerasaPjHttpError: 4xx/5xx da Serasa, timeout, DNS.
        SerasaPjReciprocityDowngradeError: so se `raise_on_downgrade=True`
            e houve downgrade silencioso.
    """
    cnpj_clean = _strip_non_digits(cnpj)
    if len(cnpj_clean) != 14:
        raise SerasaPjConfigError(
            f"CNPJ invalido: '{cnpj}' (precisa ter 14 digitos, tem {len(cnpj_clean)})"
        )

    if not config.has_credentials():
        raise SerasaPjConfigError(
            "Serasa PJ config incompleta — falta client_id/client_secret/retailer_document_id"
        )

    requested_report = report_type or config.default_report_type
    cost_center_clean = _truncate_cost_center(cost_center)

    # Endpoint Business Information Report (validado contra prod 2026-05-01):
    # - GET (nao POST), sem body
    # - `reportName` em QUERY PARAM (string)
    # - `reportParameters` em QUERY PARAM (JSON base64-encoded, carrega
    #   o `segmentCode` autorizado pelo contrato — A7 Credit = `028`)
    # - CNPJ alvo no HEADER `X-Document-id` (case-sensitive em alguns
    #   gateways Serasa — usar exatamente como abaixo)
    # `scoreModelId` NAO vai na query — a Serasa infere pelo reportName
    # + segmentCode.
    query_params = {
        "reportName": requested_report,
        "reportParameters": _encode_report_parameters(
            config.default_segment_id
        ),
    }

    extra_headers: dict[str, str] = {"X-Document-id": cnpj_clean}
    if cost_center_clean:
        extra_headers["X-Cost-Center"] = cost_center_clean

    t0 = time.monotonic()
    async with build_async_client(
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        transport=transport,
    ) as client:
        try:
            resp = await client.request(
                E_BUSINESS_INFORMATION_REPORT.method,
                E_BUSINESS_INFORMATION_REPORT.path,
                params=query_params,
                headers=extra_headers,
            )
        except httpx.HTTPError as e:
            raise SerasaPjHttpError(
                f"falha de rede em {E_BUSINESS_INFORMATION_REPORT.path}: "
                f"{type(e).__name__}({e!r})",
                status_code=None,
                detail=f"{type(e).__name__}: {e!r}",
            ) from e

    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    if resp.status_code >= 400:
        # Coleta headers uteis pra debug de 4xx/5xx (especialmente 404 vazio
        # vindo do gateway). Inclui content-type, content-length, request-id
        # da AWS/CloudFront, server, via, www-authenticate.
        debug_headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower()
            in {
                "content-type",
                "content-length",
                "server",
                "via",
                "x-amzn-requestid",
                "x-amzn-errortype",
                "x-amzn-error-type",
                "x-amzn-trace-id",
                "x-cache",
                "www-authenticate",
                "x-served-by",
            }
        }
        body_preview = resp.text[:1000] if resp.text else "<empty body>"
        raise SerasaPjHttpError(
            f"Serasa devolveu {resp.status_code} em "
            f"{E_BUSINESS_INFORMATION_REPORT.path}",
            status_code=resp.status_code,
            detail=f"headers={debug_headers} body={body_preview}",
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise SerasaPjHttpError(
            f"resposta nao-JSON: {resp.text[:500]}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        ) from e

    if not isinstance(payload, dict):
        raise SerasaPjHttpError(
            f"payload de relatorio inesperado: {type(payload).__name__}",
            status_code=resp.status_code,
        )

    # Reciprocidade silenciosa: a Serasa pode devolver `reportName` diferente
    # do que pedimos quando a reciprocidade quebra. Detectamos comparando
    # body enviado vs `reportName` no payload retornado.
    actual_report = str(
        payload.get("reportName") or payload.get("ReportName") or requested_report
    )
    if actual_report != requested_report and raise_on_downgrade:
        raise SerasaPjReciprocityDowngradeError(
            f"Serasa devolveu '{actual_report}' em vez de '{requested_report}'",
            requested=requested_report,
            received=actual_report,
        )

    return BureauQueryResult(
        payload=payload,
        requested_report=requested_report,
        actual_report_returned=actual_report,
        status_code=resp.status_code,
        cost_center=cost_center_clean,
        latency_ms=latency_ms,
    )

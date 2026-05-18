"""ETL sincrono para a familia QiTech `/v2/fidc-custodia/report/*`.

Diferente da familia /netreport/* (data unica no path), aqui temos:
- 2 endpoints com PERIODO no path (data_inicial + data_final)
- 1 endpoint com data unica no path
- 1 endpoint snapshot (sem data) — TODO quando aparecer dado real

Diferente da familia /queue/scheduler/* (callback assincrono), aqui o
GET retorna JSON imediatamente — modelo igual ao /netreport/, so muda
o path e a forma de chamar.

Cada sync grava:
- raw em `wh_qitech_raw_relatorio` (tipo_de_mercado="fidc-custodia/...")
- canonico na tabela especifica
- decision_log via caller (sync_all do etl.py se entrar la, ou via REST endpoint)
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import QiTechHttpError
from app.modules.integracoes.adapters.admin.qitech.etl import (
    _bulk_upsert_canonical,
    _upsert_raw,
)
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_aquisicao_consolidada,
    map_detalhes_operacoes,
    map_liquidados_baixados,
    map_movimento_aberto,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.movimento_aberto import MovimentoAberto
from app.warehouse.operacao_remessa import OperacaoRemessa
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio


def _normalize_cnpj(value: str) -> str:
    """Remove pontuacao, retorna 14 digitos zero-pad."""
    digits = re.sub(r"\D", "", value or "")
    return digits.zfill(14) if digits else ""


# Status codes 4xx que a QiTech usa pra dizer "nao ha dado nesse dia" (envelope
# vazio canonico, mesmo padrao da familia /netreport/* tratada em
# `etl._infer_http_status`). Diferente de 401/403 (auth) ou 422 (request
# malformado): aqui o request foi valido, a fonte simplesmente nao publicou
# dado pra essa (UA, data, endpoint). Tratamos como "empty real" — grava raw
# com http_status preservado pro coverage classificar como NOT_PUBLISHED.
_EMPTY_ENVELOPE_STATUS = frozenset({400, 404})


async def _fetch_json(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    path: str,
    unidade_administrativa_id: UUID | None = None,
) -> tuple[Any, int]:
    """GET JSON. Retorna (body, status) inclusive para 4xx canonicos de
    'sem dado'. Levanta QiTechHttpError em auth/validacao/5xx ou body nao-JSON.

    Razao do tratamento diferenciado de 400/404: a QiTech responde 400/404 com
    body JSON pra dizer "nao ha dado nesse dia". Antes esse caso levantava
    exception e o raw nao era gravado — coverage marcava gap, reconciler
    re-enfileirava em loop. Agora repassamos o body pro caller persistir raw
    com http_status preservado (assess_completeness classifica como 'empty'
    e o coverage marca NOT_PUBLISHED, quebrando o loop). Status fora desse
    conjunto continua sendo erro real e levanta.
    """
    async with build_async_client(
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        unidade_administrativa_id=unidade_administrativa_id,
    ) as client:
        resp = await client.get(path)

    is_empty_envelope = resp.status_code in _EMPTY_ENVELOPE_STATUS
    if resp.status_code >= 400 and not is_empty_envelope:
        raise QiTechHttpError(
            f"HTTP {resp.status_code} em {path}",
            status_code=resp.status_code,
            detail=resp.text[:500],
        )

    try:
        body = resp.json()
    except ValueError as e:
        if is_empty_envelope:
            # 4xx canonico mas sem body JSON — ainda assim grava raw para
            # quebrar o loop (payload sintetico marca a tentativa).
            return ({"_non_json": resp.text[:500]}, resp.status_code)
        raise QiTechHttpError(
            f"resposta nao-JSON em {path}",
            status_code=resp.status_code,
            detail=str(e),
        ) from e

    return body, resp.status_code


async def _persist_raw(
    *,
    tenant_id: UUID,
    tipo_de_mercado: str,
    data_referencia: date,
    payload: Any,
    http_status: int,
    unidade_administrativa_id: UUID | None = None,
) -> None:
    """Grava raw em wh_qitech_raw_relatorio. Aceita lista ou dict no payload.

    Quando lista, embrulha em {"items": [...]} pra caber em JSONB.
    """
    if isinstance(payload, list):
        payload_json: dict[str, Any] = {"items": payload}
    elif isinstance(payload, dict):
        payload_json = payload
    else:
        payload_json = {"value": payload}

    async with AsyncSessionLocal() as db:
        await _upsert_raw(
            db,
            tenant_id=tenant_id,
            tipo_de_mercado=tipo_de_mercado,
            data_posicao=data_referencia,
            payload=payload_json,
            http_status=http_status,
            unidade_administrativa_id=unidade_administrativa_id,
        )
        await db.commit()


async def _persist_raw_split_by_window(
    *,
    tenant_id: UUID,
    tipo_de_mercado: str,
    data_inicial: date,
    data_final: date,
    payload: dict[str, Any],
    items_field: str,
    item_date_field: str,
    http_status: int,
    unidade_administrativa_id: UUID | None = None,
) -> int:
    """Grava 1 raw por dia em [data_inicial..data_final].

    Endpoint de janela (di, df) devolve items com `item_date_field` heterogeneo.
    Pra UI Cobertura saber em quais dias o endpoint foi chamado, splitamos o
    payload em N raws (um por dia em [di..df]). Dias sem items recebem raw
    vazio (`{items_field: []}`) — `assess_completeness` classifica como empty.

    A chave UQ `(tenant, tipo, data_posicao, ua)` garante upsert idempotente
    (re-rodar a mesma janela substitui cada dia). Silver continua mapeado a
    partir do payload completo (chamado em separado pelo caller) — split aqui
    afeta APENAS a camada raw.

    Retorna o numero de raws gravados (= dias na janela, inclusivos).
    """
    items = payload.get(items_field, []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []

    by_date: dict[date, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_date = item.get(item_date_field)
        if not raw_date:
            continue
        # Aceita "2026-05-06T00:00:00.000Z" ou "2026-05-06"
        s = str(raw_date)[:10]
        try:
            d = date.fromisoformat(s)
        except ValueError:
            continue
        by_date.setdefault(d, []).append(item)

    n = 0
    cur = data_inicial
    while cur <= data_final:
        items_dia = by_date.get(cur, [])
        payload_dia: dict[str, Any] = {items_field: items_dia}
        async with AsyncSessionLocal() as db:
            await _upsert_raw(
                db,
                tenant_id=tenant_id,
                tipo_de_mercado=tipo_de_mercado,
                data_posicao=cur,
                payload=payload_dia,
                http_status=http_status,
                unidade_administrativa_id=unidade_administrativa_id,
            )
            await db.commit()
        n += 1
        cur += timedelta(days=1)
    return n


# Hash custom pra raw quando payload e lista (override do default na _upsert_raw,
# que usa sha256_of_row do dict). Hoje passamos o dict ja embrulhado, entao
# o sha sai sobre o dict envolvedor — ok pra detecao de mudanca.
_ = sha256_of_row


# ---- Sync por endpoint --------------------------------------------------


async def _generic_sync(
    *,
    name: str,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    path: str,
    tipo_de_mercado: str,
    mapper: Any,
    model: Any,
    cnpj_fundo: str,
    data_referencia: date,
    mapper_extra_kwargs: dict[str, Any] | None = None,
    unidade_administrativa_id: UUID | None = None,
    # Split raw por dia (endpoints de janela). Quando setado, grava N raws (1
    # por dia em [data_inicial..data_final]) ao inves de 1 raw em data_referencia.
    # Silver continua mapeado a partir do payload completo — split afeta APENAS
    # a camada raw (cobertura UI marca cada dia da janela).
    split_window: tuple[date, date] | None = None,
    split_items_field: str | None = None,
    split_item_date_field: str = "dataDaPosicao",
) -> dict[str, Any]:
    """Pipeline generico: fetch -> raw -> mapper -> canonico canonical."""
    t0 = time.monotonic()
    step: dict[str, Any] = {
        "name": name,
        "cnpj_fundo": _normalize_cnpj(cnpj_fundo),
        "data_referencia": data_referencia.isoformat(),
        "ok": False,
        "raw_http_status": None,
        "raw_persisted": False,
        "canonical_rows_upserted": 0,
        "errors": [],
        "elapsed_seconds": 0.0,
    }

    # 1. Fetch
    try:
        payload, status = await _fetch_json(
            tenant_id=tenant_id,
            environment=environment,
            config=config,
            path=path,
            unidade_administrativa_id=unidade_administrativa_id,
        )
        step["raw_http_status"] = status
    except QiTechHttpError as e:
        step["errors"].append(f"fetch: HTTP {e.status_code}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step
    except httpx.HTTPError as e:
        step["errors"].append(f"fetch: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    # 2. Raw — 1 raw por dia da janela (split) ou 1 raw em data_referencia.
    try:
        if split_window is not None and split_items_field is not None:
            di, df = split_window
            n_raws = await _persist_raw_split_by_window(
                tenant_id=tenant_id,
                tipo_de_mercado=tipo_de_mercado,
                data_inicial=di,
                data_final=df,
                payload=payload if isinstance(payload, dict) else {},
                items_field=split_items_field,
                item_date_field=split_item_date_field,
                http_status=status,
                unidade_administrativa_id=unidade_administrativa_id,
            )
            step["raw_persisted"] = True
            step["raw_days_persisted"] = n_raws
        else:
            await _persist_raw(
                tenant_id=tenant_id,
                tipo_de_mercado=tipo_de_mercado,
                data_referencia=data_referencia,
                payload=payload,
                http_status=status,
                unidade_administrativa_id=unidade_administrativa_id,
            )
            step["raw_persisted"] = True
    except Exception as e:
        step["errors"].append(f"raw: {type(e).__name__}: {e}")

    # 3. Map
    try:
        canonical_rows = mapper(
            payload=payload,
            tenant_id=tenant_id,
            cnpj_fundo=cnpj_fundo,
            **(mapper_extra_kwargs or {}),
        )
    except Exception as e:
        step["errors"].append(f"map: {type(e).__name__}: {e}")
        step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
        return step

    # 4. Canonical
    if canonical_rows:
        try:
            async with AsyncSessionLocal() as db:
                count = await _bulk_upsert_canonical(
                    db,
                    model,
                    canonical_rows,
                    ["tenant_id", "source_id"],
                    unidade_administrativa_id=unidade_administrativa_id,
                )
                await db.commit()
            step["canonical_rows_upserted"] = count
        except Exception as e:
            step["errors"].append(f"canonical: {type(e).__name__}: {e}")
            step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
            return step

    step["ok"] = not step["errors"]
    step["elapsed_seconds"] = round(time.monotonic() - t0, 2)
    return step


async def sync_aquisicao_consolidada(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """GET aquisicao-consolidada {cnpj}/{di}/{df} -> wh_aquisicao_recebivel.

    Endpoint de janela: grava 1 raw por dia em [di..df] (split por
    `dataDaPosicao` do payload). Silver mapeado do payload completo.
    """
    cnpj = _normalize_cnpj(cnpj_fundo)
    path = (
        f"/v2/fidc-custodia/report/aquisicao-consolidada/"
        f"{cnpj}/{data_inicial.isoformat()}/{data_final.isoformat()}"
    )
    return await _generic_sync(
        name="aquisicao-consolidada",
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        path=path,
        tipo_de_mercado="fidc-custodia/aquisicao-consolidada",
        mapper=map_aquisicao_consolidada,
        model=AquisicaoRecebivel,
        cnpj_fundo=cnpj,
        data_referencia=data_final,
        unidade_administrativa_id=unidade_administrativa_id,
        split_window=(data_inicial, data_final),
        split_items_field="aquisicaoConsolidada",
        split_item_date_field="dataDaPosicao",
    )


async def sync_liquidados_baixados(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    cnpj_fundo: str,
    data_inicial: date,
    data_final: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """GET liquidados-baixados/v2 {cnpj}/{di}/{df} -> wh_liquidacao_recebivel.

    Endpoint de janela: grava 1 raw por dia em [di..df] (split por
    `dataDaPosicao` do payload).
    """
    cnpj = _normalize_cnpj(cnpj_fundo)
    path = (
        f"/v2/fidc-custodia/report/liquidados-baixados/v2/"
        f"{cnpj}/{data_inicial.isoformat()}/{data_final.isoformat()}"
    )
    return await _generic_sync(
        name="liquidados-baixados",
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        path=path,
        tipo_de_mercado="fidc-custodia/liquidados-baixados",
        mapper=map_liquidados_baixados,
        model=LiquidacaoRecebivel,
        cnpj_fundo=cnpj,
        data_referencia=data_final,
        unidade_administrativa_id=unidade_administrativa_id,
        split_window=(data_inicial, data_final),
        split_items_field="liquidadosBaixados",
        split_item_date_field="dataDaPosicao",
    )


async def sync_detalhes_operacoes(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    cnpj_fundo: str,
    data_importacao: date,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """GET fundo/{cnpj}/data/{data} -> wh_operacao_remessa.

    Retorna lista direta (nao wrapped) — raw embrulha em {"items": [...]}
    pra caber em JSONB sem perder dados.
    """
    cnpj = _normalize_cnpj(cnpj_fundo)
    path = (
        f"/v2/fidc-custodia/report/fundo/{cnpj}/data/{data_importacao.isoformat()}"
    )
    return await _generic_sync(
        name="detalhes-operacoes",
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        path=path,
        tipo_de_mercado="fidc-custodia/detalhes-operacoes",
        mapper=map_detalhes_operacoes,
        model=OperacaoRemessa,
        cnpj_fundo=cnpj,
        data_referencia=data_importacao,
        unidade_administrativa_id=unidade_administrativa_id,
    )


async def sync_movimento_aberto(
    *,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    cnpj_fundo: str,
    data_referencia: date | None = None,
    unidade_administrativa_id: UUID | None = None,
) -> dict[str, Any]:
    """GET movimento-aberto/{cnpj}/ -> wh_movimento_aberto.

    Snapshot atual de cessoes em aberto (pendentes de liquidacao). Sem
    data no path — cada chamada e uma foto do estado AGORA.

    `data_referencia` (default = hoje UTC) compoe source_id para que
    snapshots em datas diferentes nao colidam.

    Schema validado a partir de spec passada pelo user em 2026-04-25;
    sample real veio vazio. Quando aparecer dado, validar tipos.
    """
    cnpj = _normalize_cnpj(cnpj_fundo)
    path = f"/v2/fidc-custodia/report/movimento-aberto/{cnpj}/"
    if data_referencia is None:
        data_referencia = datetime.now(UTC).date()
    return await _generic_sync(
        name="movimento-aberto",
        tenant_id=tenant_id,
        environment=environment,
        config=config,
        path=path,
        tipo_de_mercado="fidc-custodia/movimento-aberto",
        mapper=map_movimento_aberto,
        model=MovimentoAberto,
        cnpj_fundo=cnpj,
        data_referencia=data_referencia,
        mapper_extra_kwargs={"data_referencia": data_referencia},
        unidade_administrativa_id=unidade_administrativa_id,
    )


# ---- Helper que carrega config + dispara (para uso pelo router REST) ----


async def get_qitech_config_for_tenant(
    *,
    tenant_id: UUID,
    environment: Environment,
    unidade_administrativa_id: UUID | None = None,
) -> QiTechConfig | None:
    """Carrega + decifra config QiTech do tenant + UA.

    Retorna None se nao houver config persistida (tenant/UA ainda nao
    configurou QiTech). Multi-UA: cada UA tem sua propria credencial.
    """
    from app.core.enums import SourceType
    from app.modules.integracoes.services.source_config import (
        decrypt_config,
        get_config,
    )

    async with AsyncSessionLocal() as db:
        cfg_row = await get_config(
            db,
            tenant_id,
            SourceType.ADMIN_QITECH,
            environment,
            unidade_administrativa_id=unidade_administrativa_id,
        )
        if cfg_row is None:
            return None
        plain = decrypt_config(cfg_row.config)

    return QiTechConfig.from_dict(plain)


async def resolve_cnpj_by_ua_id(
    *, tenant_id: UUID, unidade_administrativa_id: UUID
) -> str | None:
    """UA -> CNPJ (14 digitos zero-pad). Inverso do `resolve_ua_id_by_cnpj`.

    Usado pelos handlers do `adapter._HANDLERS` para descobrir o CNPJ do fundo
    quando o dispatcher genérico de endpoints chama `custodia.*` ou
    `market.fidc_estoque` — esses pedem cnpj_fundo no path/body QiTech mas o
    dispatcher so passa `unidade_administrativa_id`. Retorna None se UA nao
    existe ou nao tem CNPJ cadastrado.
    """
    from sqlalchemy import select

    from app.modules.cadastros.models.unidade_administrativa import (
        UnidadeAdministrativa,
    )

    async with AsyncSessionLocal() as db:
        stmt = (
            select(UnidadeAdministrativa.cnpj)
            .where(
                UnidadeAdministrativa.tenant_id == tenant_id,
                UnidadeAdministrativa.id == unidade_administrativa_id,
            )
            .limit(1)
        )
        cnpj_raw = (await db.execute(stmt)).scalar_one_or_none()

    if not cnpj_raw:
        return None
    return _normalize_cnpj(cnpj_raw) or None


async def resolve_ua_id_by_cnpj(
    *, tenant_id: UUID, cnpj_fundo: str
) -> UUID | None:
    """Resolve a UA do tenant correspondente a um CNPJ de fundo.

    Usado pelos endpoints REST /qitech/custodia/* que recebem cnpj_fundo
    no payload e precisam saber qual credencial QiTech usar (cada UA tem
    a sua). Match por CNPJ normalizado em
    `cadastros_unidade_administrativa.cnpj`.

    Retorna None se nenhuma UA do tenant tem este CNPJ — caller deve
    devolver 409 sugerindo cadastrar a UA primeiro.
    """
    from sqlalchemy import select

    from app.modules.cadastros.models.unidade_administrativa import (
        UnidadeAdministrativa,
    )

    cnpj_norm = _normalize_cnpj(cnpj_fundo)
    if not cnpj_norm:
        return None

    async with AsyncSessionLocal() as db:
        stmt = (
            select(UnidadeAdministrativa.id)
            .where(
                UnidadeAdministrativa.tenant_id == tenant_id,
                UnidadeAdministrativa.cnpj == cnpj_norm,
            )
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()


# Helper pra eliminar import ciclico no router REST (que tambem importa
# QiTechRawRelatorio em outros contextos).
_ = QiTechRawRelatorio
_ = ADAPTER_VERSION
_ = datetime
_ = UTC

"""Sync de catalogo BDC — diff entre /precos/ e provedor_dados_dataset.

Fluxo:
    1. Caller (etl.py::sync_catalog_for_provider) abre run em provedor_dados_sync_run.
    2. Chama client.query_pricing() — devolve payload bruto.
    3. _parse_pricing_payload() normaliza pra lista de ParsedDataset.
    4. _apply_catalog_diff() aplica:
        - dataset desconhecido (1a vez) → INSERT em provedor_dados_dataset +
          INITIAL em preco_historico
        - dataset conhecido com preco mudado → UPDATE em provedor_dados_dataset
          (apenas camada sync-managed) + DELTA em preco_historico
        - dataset conhecido sem mudanca → so atualiza last_synced_at
        - dataset que sumiu da resposta → marcado em provider_status
          (NAO deletamos — preserva trilha)
    5. Caller fecha run com contadores + status OK.

Camada A7 do dataset (display_name_pt_br, categoria_ui, description_pt_br,
enabled_for_sale, markup_pct) NUNCA e sobrescrita pelo sync — preservada
entre runs.

⚠️  ASSUMPTION SOBRE SHAPE DA RESPOSTA:
    A documentacao BDC nao detalha o shape exato do /precos/ com body
    vazio. O parser tenta tres shapes plausiveis (ver _parse_pricing_payload).
    Se nenhum bater, levanta BigDataCorpPayloadError com o payload truncado.
    Quando isso acontecer, ajustar o parser conforme o shape real (que ficou
    salvo em arquivo pelo script de sync — ver scripts/sync_bdc_catalog.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpPayloadError,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.shared.data_providers.enums import PriceChangeKind
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.price_history import (
    DataProviderDatasetPriceHistory,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Tipos parciais — saida do parser
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedTier:
    """Uma faixa de preco extraida do payload."""

    tier_index: int
    up_to_quantity: int | None
    price_brl: Decimal


@dataclass(frozen=True)
class ParsedDataset:
    """Um dataset extraido do payload (chave: api + code)."""

    api: str  # "People", "Companies", "Validations", etc.
    code: str  # "basic_data", "lawsuits_distribution_data", etc.
    tiers: list[ParsedTier] = field(default_factory=list)
    provider_status: str | None = None


@dataclass(frozen=True)
class CatalogSyncCounters:
    """Resultado agregado do diff — devolvido pra etl.py preencher sync_run."""

    added: int
    updated: int
    unchanged: int
    removed: int


# ─────────────────────────────────────────────────────────────────────────────
# Parser — tenta multiplos shapes plausiveis do BDC /precos/
# ─────────────────────────────────────────────────────────────────────────────


def _parse_pricing_payload(payload: dict[str, Any]) -> list[ParsedDataset]:
    """Normaliza payload do /precos/ pra lista plana de ParsedDataset.

    Shapes que tenta (em ordem):

    Shape A — Result aninhado por API:
        {
          "Status": [...],
          "Result": {
            "People": {
              "basic_data": {"PriceTable": [{"From":1,"To":10000,"Price":0.05}, ...]},
              "phones": {...}
            },
            "Companies": {...}
          }
        }

    Shape B — Lista plana:
        {
          "Status": [...],
          "Pricing": [
            {"API":"People","Dataset":"basic_data","PriceTable":[...]},
            ...
          ]
        }

    Shape C — Result direto sem aninhamento por API:
        {
          "Status": [...],
          "Result": {
            "basic_data": {"API":"People","PriceTable":[...]},
            "lawsuits_distribution_data": {...}
          }
        }

    Levanta BigDataCorpPayloadError se nenhum shape bater.
    """
    # Shape A
    result = payload.get("Result")
    if isinstance(result, dict):
        # Heuristica: se TODOS os filhos top-level forem dicts cujos VALORES
        # tambem sao dicts (api → datasets → spec), e shape A.
        is_shape_a = all(
            isinstance(v, dict)
            and v
            and all(isinstance(inner, dict) for inner in v.values())
            for v in result.values()
            if v
        )
        if is_shape_a and result:
            parsed: list[ParsedDataset] = []
            for api_name, datasets_dict in result.items():
                if not isinstance(datasets_dict, dict):
                    continue
                for dataset_code, spec in datasets_dict.items():
                    if not isinstance(spec, dict):
                        continue
                    parsed.append(
                        ParsedDataset(
                            api=str(api_name),
                            code=str(dataset_code),
                            tiers=_extract_tiers(spec),
                            provider_status=_extract_status(spec),
                        )
                    )
            if parsed:
                return parsed

        # Shape C — Result direto, dataset_code → spec com chave "API" interna
        is_shape_c = all(
            isinstance(v, dict) and ("API" in v or "PriceTable" in v)
            for v in result.values()
            if v
        )
        if is_shape_c and result:
            parsed = []
            for dataset_code, spec in result.items():
                if not isinstance(spec, dict):
                    continue
                api_name = str(spec.get("API") or "Unknown")
                parsed.append(
                    ParsedDataset(
                        api=api_name,
                        code=str(dataset_code),
                        tiers=_extract_tiers(spec),
                        provider_status=_extract_status(spec),
                    )
                )
            if parsed:
                return parsed

    # Shape B — chave "Pricing" como lista plana
    pricing_list = payload.get("Pricing") or payload.get("PriceTable")
    if isinstance(pricing_list, list) and pricing_list:
        parsed = []
        for item in pricing_list:
            if not isinstance(item, dict):
                continue
            api_name = str(
                item.get("API") or item.get("Api") or "Unknown"
            )
            dataset_code = item.get("Dataset") or item.get("Name")
            if not dataset_code:
                continue
            parsed.append(
                ParsedDataset(
                    api=api_name,
                    code=str(dataset_code),
                    tiers=_extract_tiers(item),
                    provider_status=_extract_status(item),
                )
            )
        if parsed:
            return parsed

    # Shape D — BDC "Pricing_All": Locales -> Entities -> Datasets ->
    # PricingRanges (chaves = quantidade minima da faixa). Prioriza pt-br.
    pricing_all = payload.get("Pricing_All")
    if isinstance(pricing_all, dict):
        locales = pricing_all.get("Locales")
        if isinstance(locales, dict) and locales:
            locale_node = locales.get("pt-br") or next(iter(locales.values()), None)
            entities = (
                locale_node.get("Entities")
                if isinstance(locale_node, dict)
                else None
            )
            if isinstance(entities, dict):
                parsed = []
                for entity_name, entity_node in entities.items():
                    datasets = (
                        entity_node.get("Datasets")
                        if isinstance(entity_node, dict)
                        else None
                    )
                    if not isinstance(datasets, dict):
                        continue
                    for dataset_code, spec in datasets.items():
                        if not isinstance(spec, dict):
                            continue
                        parsed.append(
                            ParsedDataset(
                                api=str(entity_name).title(),  # PEOPLE -> People
                                code=str(dataset_code),
                                tiers=_tiers_from_pricing_ranges(
                                    spec.get("PricingRanges")
                                ),
                                provider_status=_extract_status(spec),
                            )
                        )
                if parsed:
                    return parsed

    # Nao deu. Mensagem de erro inclui as TOP-LEVEL keys pra usuario poder
    # ajustar o parser sem precisar redumpar.
    top_keys = (
        list(payload.keys()) if isinstance(payload, dict) else "<not a dict>"
    )
    raise BigDataCorpPayloadError(
        f"Nenhum shape conhecido bate em /precos/. "
        f"top-level keys: {top_keys!r}. "
        "Ajuste _parse_pricing_payload() em pricing_sync.py."
    )


def _extract_tiers(spec: dict[str, Any]) -> list[ParsedTier]:
    """Extrai escada de precos de um dict de dataset.

    Procura por:
        - PriceTable: [{"From": int, "To": int, "Price": float}, ...]
        - Tiers: [{"UpTo": int, "Price": float}, ...]
        - Pricing: idem PriceTable

    Retorna lista vazia se nao encontrar (dataset sem preco — descoberto
    e registrado mesmo assim, mas sem historico).
    """
    candidates = (
        spec.get("PriceTable") or spec.get("Pricing") or spec.get("Tiers") or []
    )
    if not isinstance(candidates, list):
        return []

    tiers: list[ParsedTier] = []
    for idx, raw in enumerate(candidates):
        if not isinstance(raw, dict):
            continue
        # Tenta varios nomes de campo de preco/limite — vendor pode mudar.
        price_raw = (
            raw.get("Price")
            or raw.get("price")
            or raw.get("UnitPrice")
            or raw.get("Value")
        )
        up_to_raw = (
            raw.get("To")
            or raw.get("UpTo")
            or raw.get("UpToQuantity")
            or raw.get("MaxQuantity")
        )
        if price_raw is None:
            continue
        try:
            price_dec = Decimal(str(price_raw))
        except (ValueError, ArithmeticError):
            continue

        up_to_int: int | None
        try:
            up_to_int = int(up_to_raw) if up_to_raw is not None else None
        except (ValueError, TypeError):
            up_to_int = None

        tiers.append(
            ParsedTier(
                tier_index=idx,
                up_to_quantity=up_to_int,
                price_brl=price_dec,
            )
        )
    return tiers


def _tiers_from_pricing_ranges(ranges: Any) -> list[ParsedTier]:
    """Extrai tiers do shape BDC `PricingRanges`.

    Chaves = quantidade MINIMA (string) da faixa; valor = {Pricing, FixedValue}.
    Ordena por quantidade crescente: tier 0 = faixa de menor volume (maior preco
    unitario), coerente com `_first_tier_price`. `up_to_quantity` = inicio da
    proxima faixa (None na ultima). `FixedValue` (preco flat de faixa enterprise)
    nao e modelado — usa-se `Pricing` (preco por consulta).
    """
    if not isinstance(ranges, dict):
        return []
    thresholds: list[int] = []
    for k in ranges:
        try:
            thresholds.append(int(k))
        except (ValueError, TypeError):
            continue
    thresholds.sort()
    tiers: list[ParsedTier] = []
    for idx, t in enumerate(thresholds):
        spec = ranges.get(str(t))
        if not isinstance(spec, dict):
            continue
        try:
            price_dec = Decimal(str(spec.get("Pricing", 0)))
        except (ValueError, ArithmeticError):
            continue
        up_to = thresholds[idx + 1] if idx + 1 < len(thresholds) else None
        tiers.append(
            ParsedTier(tier_index=idx, up_to_quantity=up_to, price_brl=price_dec)
        )
    return tiers


def _extract_status(spec: dict[str, Any]) -> str | None:
    """Extrai status do dataset, se vendor reportar.

    Procura por chaves comuns: Status, status. Texto livre.
    """
    raw = spec.get("Status") or spec.get("status")
    if raw is None:
        return None
    return str(raw)[:32]


def _tiers_to_jsonb(tiers: list[ParsedTier]) -> list[dict] | None:
    """Serializa tiers pra JSONB (formato armazenado em pricing_tiers_json)."""
    if not tiers:
        return None
    return [
        {
            "tier_index": t.tier_index,
            "up_to_quantity": t.up_to_quantity,
            "price_brl": str(t.price_brl),
        }
        for t in tiers
    ]


def _first_tier_price(tiers: list[ParsedTier]) -> Decimal | None:
    """Preco da 1a faixa (mais cara) — vai pra `current_cost_brl`."""
    return tiers[0].price_brl if tiers else None


# ─────────────────────────────────────────────────────────────────────────────
# Diff & persist
# ─────────────────────────────────────────────────────────────────────────────


_PRICE_HISTORY_SOURCE = "bdc_pricing_api"


async def apply_catalog_diff(
    *,
    db: AsyncSession,
    provider_id: UUID,
    parsed: list[ParsedDataset],
    sync_run_id: UUID,
) -> CatalogSyncCounters:
    """Aplica o diff entre `parsed` e o estado atual do catalogo no DB.

    NAO commita — caller controla a transacao (geralmente uma transacao por
    sync run, com rollback em falha).

    Args:
        db: AsyncSession aberta.
        provider_id: row do provedor_dados (BDC).
        parsed: saida de _parse_pricing_payload().
        sync_run_id: row de provedor_dados_sync_run desta execucao —
            referenciada por price_history.

    Returns:
        CatalogSyncCounters agregando added/updated/unchanged/removed.
    """
    now = datetime.now(UTC)

    # 1. Carrega estado atual do catalogo desse provider em memoria
    # (volume tipico: ~100 datasets, OK pra in-memory).
    stmt = select(DataProviderDataset).where(
        DataProviderDataset.provider_id == provider_id
    )
    existing_rows = (await db.execute(stmt)).scalars().all()
    existing_by_key = {
        (row.provider_api, row.provider_dataset_code): row
        for row in existing_rows
    }

    parsed_keys: set[tuple[str, str]] = set()
    added = 0
    updated = 0
    unchanged = 0

    for ds in parsed:
        key = (ds.api, ds.code)
        parsed_keys.add(key)
        existing = existing_by_key.get(key)
        new_tiers_json = _tiers_to_jsonb(ds.tiers)
        new_first_price = _first_tier_price(ds.tiers)

        if existing is None:
            # Novo dataset — INSERT + INITIAL em historico (uma row por tier)
            new_row = DataProviderDataset(
                provider_id=provider_id,
                provider_dataset_code=ds.code,
                provider_api=ds.api,
                current_cost_brl=new_first_price,
                pricing_tiers_json=new_tiers_json,
                last_synced_at=now,
                last_diff_at=now,
                provider_status=ds.provider_status,
                # Camada A7 fica vazia — mantenedor preenche depois.
                enabled_for_sale=False,
            )
            db.add(new_row)
            await db.flush()  # garante new_row.id pra historico abaixo
            for tier in ds.tiers:
                db.add(
                    DataProviderDatasetPriceHistory(
                        dataset_id=new_row.id,
                        tier_index=tier.tier_index,
                        up_to_quantity=tier.up_to_quantity,
                        price_brl=tier.price_brl,
                        previous_price_brl=None,
                        kind=PriceChangeKind.INITIAL,
                        source=_PRICE_HISTORY_SOURCE,
                        observed_at=now,
                        sync_run_id=sync_run_id,
                    )
                )
            added += 1
            continue

        # Existente — detecta deltas por faixa
        old_tiers = existing.pricing_tiers_json or []
        deltas = _diff_tiers(old_tiers=old_tiers, new_tiers=ds.tiers)
        status_changed = (existing.provider_status or None) != (
            ds.provider_status or None
        )
        any_change = bool(deltas) or status_changed

        # Sempre atualiza last_synced_at (sinaliza "vi voce neste run")
        existing.last_synced_at = now
        if any_change:
            existing.last_diff_at = now
            existing.current_cost_brl = new_first_price
            existing.pricing_tiers_json = new_tiers_json
            existing.provider_status = ds.provider_status

            for delta in deltas:
                db.add(
                    DataProviderDatasetPriceHistory(
                        dataset_id=existing.id,
                        tier_index=delta.tier_index,
                        up_to_quantity=delta.up_to_quantity,
                        price_brl=delta.price_brl,
                        previous_price_brl=delta.previous_price_brl,
                        kind=PriceChangeKind.DELTA,
                        source=_PRICE_HISTORY_SOURCE,
                        observed_at=now,
                        sync_run_id=sync_run_id,
                    )
                )
            updated += 1
        else:
            unchanged += 1

    # 2. Datasets que SUMIRAM da resposta — marca em provider_status, nao deleta.
    removed = 0
    for key, existing in existing_by_key.items():
        if key in parsed_keys:
            continue
        # Marca como "missing" se ja nao estava — evita escrever sempre.
        marker = "missing_in_pricing_api"
        if existing.provider_status != marker:
            existing.provider_status = marker
            existing.last_diff_at = now
            removed += 1

    return CatalogSyncCounters(
        added=added,
        updated=updated,
        unchanged=unchanged,
        removed=removed,
    )


@dataclass(frozen=True)
class _TierDelta:
    """Mudanca detectada em uma faixa entre old e new (usado so internamente)."""

    tier_index: int
    up_to_quantity: int | None
    price_brl: Decimal
    previous_price_brl: Decimal | None


def _diff_tiers(
    *, old_tiers: list[Any], new_tiers: list[ParsedTier]
) -> list[_TierDelta]:
    """Compara escadas tier-a-tier; devolve as faixas com mudanca de preco.

    `old_tiers` e o JSONB armazenado (lista de dicts {tier_index, up_to_quantity,
    price_brl}). `new_tiers` e a lista parseada do payload corrente.

    Faixa nova (existe em new mas nao em old) -> delta com `previous_price_brl=None`.
    Faixa removida (existe em old mas nao em new) -> ignorada aqui (a row do
    dataset continua existindo, apenas com pricing_tiers_json mudado; o gap
    fica registrado no proprio JSONB).
    """
    old_by_idx: dict[int, Decimal] = {}
    for raw in old_tiers:
        if not isinstance(raw, dict):
            continue
        idx = raw.get("tier_index")
        price = raw.get("price_brl")
        if idx is None or price is None:
            continue
        try:
            old_by_idx[int(idx)] = Decimal(str(price))
        except (ValueError, ArithmeticError):
            continue

    deltas: list[_TierDelta] = []
    for tier in new_tiers:
        old_price = old_by_idx.get(tier.tier_index)
        if old_price is None or old_price != tier.price_brl:
            deltas.append(
                _TierDelta(
                    tier_index=tier.tier_index,
                    up_to_quantity=tier.up_to_quantity,
                    price_brl=tier.price_brl,
                    previous_price_brl=old_price,
                )
            )
    return deltas


# ─────────────────────────────────────────────────────────────────────────────
# Adapter version export
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "ADAPTER_VERSION",
    "CatalogSyncCounters",
    "ParsedDataset",
    "ParsedTier",
    "_parse_pricing_payload",
    "apply_catalog_diff",
]

"""Consultas JUCESP via Infosimples (ficha completa, lista e download de docs).

Camada de QUERY do adapter (espelha `bdc_cadastral_query`): resolve dataset
pelo public_code (white-label), carrega/decifra a credencial global, chama o
client, grava o BRONZE (`wh_infosimples_raw_consulta`) e devolve campos
mapeados (vendor-neutro). NÃO persiste silver — quem materializa no domínio
(credit_dossier_company.junta_data, documentos) é o módulo crédito, via
`public.py` (§11.3).

O path técnico de cada consulta vem de
`provedor_dados_dataset.provider_query_name` — divergência com a doc do
vendor se corrige com UPDATE no catálogo, sem deploy.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.infosimples import (
    ADAPTER_VERSION,
    InfosimplesConfig,
    build_async_client,
    consulta,
    download_binary,
)
from app.modules.integracoes.adapters.data.infosimples.errors import (
    InfosimplesAdapterError,
    InfosimplesPayloadError,
    InfosimplesQueryError,
)
from app.modules.integracoes.adapters.data.infosimples.mappers import (
    JuntaFichaFields,
    fields_to_jsonable,
    map_ficha,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.provider import DataProvider
from app.warehouse import InfosimplesRawConsulta

_PROVIDER_SLUG = "INFOSIMPLES"
_FAMILY_JUCESP = "jucesp"

PUBLIC_CODE_JUNTA_FICHA = "JUNTA-SP-FICHA"
PUBLIC_CODE_JUNTA_DOCS = "JUNTA-SP-DOCS"
PUBLIC_CODE_JUNTA_DOWNLOAD = "JUNTA-SP-DOC-DOWNLOAD"


@dataclass(slots=True)
class JuntaFichaResult:
    found: bool
    fields: JuntaFichaFields | None
    raw_id: UUID | None
    # Versão JSON-safe dos fields — pronta pra persistir no domínio (o
    # consumidor cross-módulo não importa o mapper do adapter).
    fields_json: dict[str, Any] | None = None
    adapter_version: str = ADAPTER_VERSION
    message: str | None = None
    # True quando a falha foi indisponibilidade transitória da fonte (ver
    # _TRANSIENT_SOURCE_CODES) — distinto de "não encontrado". O caller decide
    # apresentar como "tente de novo" em vez de "não existe / não é de SP".
    transient: bool = False


@dataclass(slots=True)
class JuntaListaDocsResult:
    found: bool
    documentos: list[dict[str, Any]] = field(default_factory=list)
    raw_id: UUID | None = None
    message: str | None = None
    transient: bool = False


@dataclass(slots=True)
class JuntaDownloadResult:
    content: bytes
    mime_type: str | None
    raw_id: UUID | None


def _digits(raw: Any) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _failure_message(resp: Any) -> str:
    """Mensagem legível pro analista: code_message + motivo real do vendor.

    O detalhe operacional vem em `errors[]` (ex.: "A conta está sem saldo.
    Adicione saldo para conseguir usar a API.") — sem ele, o analista só
    veria o 603 genérico.
    """
    msg = f"{resp.code} · {resp.code_message}"
    if resp.errors:
        first = str(resp.errors[0]).strip()
        if first and first not in msg:
            msg = f"{msg} — {first}"
    return msg


# Códigos aplicacionais da Infosimples que indicam o PORTAL DA FONTE
# (gov.br / JUCESP) instável, fora do ar ou lento — TRANSITÓRIOS e re-tentáveis,
# NÃO "empresa não encontrada". Tratá-los como found=false mente pro analista
# ("a empresa é registrada em SP?") e desvia pro upload manual sem necessidade.
# Familia 606-615 = portal de origem indisponivel / instavel / em manutencao /
# timeout / tentativas excedidas. Conhecidos: 606 (site fora do ar/instável),
# 607 (manutenção), 609 ("tentativas de consultar o site ou aplicativo de origem
# excedidas"), 612 (timeout), 615 ("o site ou aplicativo de origem parece estar
# indisponível"). Os intermediários (608/610/611/613/614) são da mesma família
# de indisponibilidade da fonte — incluídos por segurança. DC-2026-0044.
# NÃO inclui 600 (sem resultados = "não encontrado" real, tratado à parte como
# code 200 + data vazio) nem 601/602/603 (parâmetros/captcha/saldo — mensagem
# própria, não "tente de novo").
_TRANSIENT_SOURCE_CODES = frozenset(range(606, 616))


def _is_transient(resp: Any) -> bool:
    return int(getattr(resp, "code", 0) or 0) in _TRANSIENT_SOURCE_CODES


def _transient_message(resp: Any) -> str:
    """Mensagem honesta de indisponibilidade transitória (≠ 'não existe')."""
    return (
        "A JUCESP (portal gov.br) está instável ou lenta agora e a consulta não "
        f"completou ({_failure_message(resp)}). Isso NÃO significa que a empresa "
        "não existe — tente novamente em instantes."
    )


async def _load_provider_and_config(
    db: AsyncSession,
) -> tuple[DataProvider, InfosimplesConfig]:
    provider = (
        await db.execute(
            select(DataProvider).where(DataProvider.slug == _PROVIDER_SLUG)
        )
    ).scalar_one_or_none()
    if provider is None or not provider.enabled:
        raise InfosimplesAdapterError(
            "Provedor Infosimples não cadastrado/habilitado."
        )
    credential = (
        (
            await db.execute(
                select(DataProviderCredential)
                .where(
                    DataProviderCredential.provider_id == provider.id,
                    DataProviderCredential.active.is_(True),
                )
                .order_by(DataProviderCredential.updated_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if credential is None:
        raise InfosimplesAdapterError(
            "Nenhuma credencial Infosimples ativa. Cadastre em "
            "/admin/dados/provedores."
        )
    plain = decrypt_envelope(credential.encrypted_payload)
    return provider, InfosimplesConfig.from_dict(
        plain,
        base_url=provider.base_url,
        timeout_ms=provider.default_timeout_ms,
    )


async def _resolve_dataset(
    db: AsyncSession, *, provider_id: UUID, public_code: str
) -> DataProviderDataset:
    dataset = (
        await db.execute(
            select(DataProviderDataset).where(
                DataProviderDataset.provider_id == provider_id,
                DataProviderDataset.public_code == public_code,
            )
        )
    ).scalar_one_or_none()
    if dataset is None or not dataset.provider_query_name:
        raise InfosimplesAdapterError(
            f"Dataset {public_code!r} não cadastrado no catálogo do Infosimples."
        )
    return dataset


async def _store_bronze(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    public_code: str,
    consulta_path: str,
    api_code: int | None,
    found: bool,
    status_code: int,
    payload: dict[str, Any],
    latency_ms: float | None,
    triggered_by: str | None,
) -> UUID:
    sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    row = InfosimplesRawConsulta(
        tenant_id=tenant_id,
        documento=documento[:20],
        public_code=public_code,
        consulta_path=consulta_path[:128],
        api_code=api_code,
        found=found,
        status_code=status_code,
        payload=payload,
        payload_sha256=sha,
        latency_ms=latency_ms,
        triggered_by=triggered_by,
        fetched_by_version=ADAPTER_VERSION,
    )
    db.add(row)
    await db.flush()
    return row.id


async def fetch_junta_ficha(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str | None = None,
    nire: str | None = None,
    public_code: str = PUBLIC_CODE_JUNTA_FICHA,
    triggered_by: str | None = None,
) -> JuntaFichaResult:
    """Ficha cadastral (completa) da JUCESP por CNPJ ou NIRE.

    Grava bronze SEMPRE (sucesso ou falha de consulta com response). O caller
    é responsável pelo commit.
    """
    doc = _digits(cnpj) or _digits(nire)
    if not doc:
        raise ValueError("Informe cnpj ou nire.")

    provider, config = await _load_provider_and_config(db)
    dataset = await _resolve_dataset(
        db, provider_id=provider.id, public_code=public_code
    )
    login = config.family_login(_FAMILY_JUCESP)

    params: dict[str, Any] = {**login}
    if _digits(cnpj):
        params["cnpj"] = _digits(cnpj)
    elif nire:
        params["nire"] = _digits(nire)

    async with build_async_client(
        base_url=config.base_url, timeout_s=config.timeout_s
    ) as client:
        resp = await consulta(
            client,
            path=dataset.provider_query_name,
            api_key=config.api_key,
            params=params,
            timeout_s=config.timeout_s,
        )

    raw_id = await _store_bronze(
        db,
        tenant_id=tenant_id,
        documento=doc,
        public_code=public_code,
        consulta_path=dataset.provider_query_name,
        api_code=resp.code,
        found=resp.ok and resp.first is not None,
        status_code=resp.http_status,
        payload=resp.raw,
        latency_ms=resp.latency_ms,
        triggered_by=triggered_by,
    )

    if not resp.ok:
        transient = _is_transient(resp)
        return JuntaFichaResult(
            found=False,
            fields=None,
            raw_id=raw_id,
            message=_transient_message(resp) if transient else _failure_message(resp),
            transient=transient,
        )
    first = resp.first
    if first is None:
        return JuntaFichaResult(
            found=False, fields=None, raw_id=raw_id, message="Sem resultados."
        )
    fields = map_ficha(first)
    return JuntaFichaResult(
        found=True,
        fields=fields,
        raw_id=raw_id,
        fields_json=fields_to_jsonable(fields),
    )


def _extract_documentos(first: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista de documentos digitalizados a partir do response (tolerante)."""
    for key in ("resultados", "documentos", "lista"):
        raw = first.get(key)
        if isinstance(raw, list):
            return [i for i in raw if isinstance(i, dict)]
    # Alguns layouts devolvem o próprio data[] como linhas de documento.
    return [first] if first.get("registro") or first.get("protocolo") else []


async def fetch_junta_lista_documentos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    nire: str,
    public_code: str = PUBLIC_CODE_JUNTA_DOCS,
    triggered_by: str | None = None,
) -> JuntaListaDocsResult:
    """Documentos digitalizados arquivados na JUCESP para o NIRE."""
    provider, config = await _load_provider_and_config(db)
    dataset = await _resolve_dataset(
        db, provider_id=provider.id, public_code=public_code
    )
    login = config.family_login(_FAMILY_JUCESP)

    async with build_async_client(
        base_url=config.base_url, timeout_s=config.timeout_s
    ) as client:
        resp = await consulta(
            client,
            path=dataset.provider_query_name,
            api_key=config.api_key,
            params={**login, "nire": _digits(nire)},
            timeout_s=config.timeout_s,
        )

    raw_id = await _store_bronze(
        db,
        tenant_id=tenant_id,
        documento=_digits(nire),
        public_code=public_code,
        consulta_path=dataset.provider_query_name,
        api_code=resp.code,
        found=resp.ok and bool(resp.data),
        status_code=resp.http_status,
        payload=resp.raw,
        latency_ms=resp.latency_ms,
        triggered_by=triggered_by,
    )

    if not resp.ok:
        transient = _is_transient(resp)
        return JuntaListaDocsResult(
            found=False,
            raw_id=raw_id,
            message=_transient_message(resp) if transient else _failure_message(resp),
            transient=transient,
        )
    documentos: list[dict[str, Any]] = []
    for item in resp.data:
        if isinstance(item, dict):
            documentos.extend(_extract_documentos(item))
    return JuntaListaDocsResult(
        found=bool(documentos), documentos=documentos, raw_id=raw_id
    )


async def fetch_junta_documento(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    nire: str,
    registro: str,
    public_code: str = PUBLIC_CODE_JUNTA_DOWNLOAD,
    triggered_by: str | None = None,
) -> JuntaDownloadResult:
    """Baixa a cópia digitalizada de um documento arquivado (NIRE + registro).

    O binário em si NÃO vai pro bronze (só o response JSON da consulta);
    quem persiste o arquivo é o módulo crédito (vira credit_dossier_document).
    """
    provider, config = await _load_provider_and_config(db)
    dataset = await _resolve_dataset(
        db, provider_id=provider.id, public_code=public_code
    )
    login = config.family_login(_FAMILY_JUCESP)

    async with build_async_client(
        base_url=config.base_url, timeout_s=config.timeout_s
    ) as client:
        resp = await consulta(
            client,
            path=dataset.provider_query_name,
            api_key=config.api_key,
            params={**login, "nire": _digits(nire), "registro": registro},
            timeout_s=config.timeout_s,
        )

        raw_id = await _store_bronze(
            db,
            tenant_id=tenant_id,
            documento=_digits(nire),
            public_code=public_code,
            consulta_path=dataset.provider_query_name,
            api_code=resp.code,
            found=resp.ok,
            status_code=resp.http_status,
            payload=resp.raw,
            latency_ms=resp.latency_ms,
            triggered_by=triggered_by,
        )

        if not resp.ok:
            raise InfosimplesQueryError(resp.code, _failure_message(resp))

        # O PDF chega como URL (data[].url/arquivo/link ou site_receipts).
        url: str | None = None
        first = resp.first or {}
        for key in ("url", "arquivo", "link", "download", "documento_url"):
            candidate = first.get(key)
            if isinstance(candidate, str) and candidate.startswith("http"):
                url = candidate
                break
        if url is None and resp.site_receipts:
            url = resp.site_receipts[0]
        if url is None:
            raise InfosimplesPayloadError(
                "Download JUCESP sem URL de arquivo no response — "
                "verifique o layout no bronze."
            )
        content, mime = await download_binary(client, url)

    return JuntaDownloadResult(content=content, mime_type=mime, raw_id=raw_id)

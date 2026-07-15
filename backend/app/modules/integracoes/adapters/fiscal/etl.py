"""ETL fiscal -- drena a landing zone (fiscal_nfe / fiscal_cte) para o warehouse.

Fluxo por registro pendente de `file_landing` (1 registro = 1 zip ou XML solto):

    blob do StorageBackend -> explode container (magic bytes PK = zip) ->
    por entrada .xml: roteia pela raiz
        nfeProc       -> raw JSONB integral + silver curado + duplicatas
        cteProc       -> raw JSONB integral + silver curado + elos NF-e
        procEventoNFe -> DESCARTADO (decisao 2026-07-07: eventos virao de
                         outra origem; o XML permanece no zip do bronze)
        outros/.pdf   -> ignorado (preservado no bronze)
    -> marca consumed_at -> decision_log do batch

Commit por registro de landing (zip): resumivel e sem transacao gigante no
backfill inicial (~29k documentos).
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.modules.integracoes.adapters.fiscal.parsers import (
    CteParsed,
    NfeParsed,
    parse_cte,
    parse_nfe,
)
from app.modules.integracoes.adapters.fiscal.version import ADAPTER_VERSION
from app.modules.integracoes.adapters.fiscal.xml_json import xml_to_dict
from app.modules.integracoes.models.file_landing import FileLanding
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.storage import ObjectNotFoundError, get_storage_backend
from app.warehouse.fiscal_cte import Cte, CteNfe, CteRawDocumento
from app.warehouse.fiscal_nfe import Nfe, NfeDuplicata, NfeItem, NfeRawDocumento

logger = logging.getLogger(__name__)

LABELS = ("fiscal_nfe", "fiscal_cte")
_ZIP_MAGIC = b"PK\x03\x04"


@dataclass
class FiscalSyncResult:
    landings_processados: int = 0
    nfe_novas: int = 0
    nfe_duplicadas: int = 0
    cte_novos: int = 0
    cte_duplicados: int = 0
    eventos_descartados: int = 0
    entradas_ignoradas: int = 0  # PDFs e outros nao-XML
    xml_invalidos: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _explode(blob: bytes, nome: str) -> list[tuple[str, bytes]]:
    """(nome, bytes) por documento; zip vira N entradas .xml."""
    if not blob.startswith(_ZIP_MAGIC):
        return [(nome, blob)]
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.file_size == 0:
                continue
            out.append((f"{nome}/{info.filename}", zf.read(info)))
    return out


async def sync_fiscal(db: AsyncSession, *, tenant_id: UUID) -> FiscalSyncResult:
    """Consome todos os pendentes fiscais do tenant. Commit por landing row."""
    result = FiscalSyncResult()
    storage = get_storage_backend()
    pending = (
        (
            await db.execute(
                select(FileLanding)
                .where(
                    FileLanding.tenant_id == tenant_id,
                    FileLanding.source_label.in_(LABELS),
                    FileLanding.consumed_at.is_(None),
                )
                .order_by(FileLanding.received_at)
            )
        )
        .scalars()
        .all()
    )
    for row in pending:
        try:
            blob = await storage.get(row.storage_key)
        except ObjectNotFoundError:
            logger.error(
                "file_landing %s sem blob (key=%s) — permanece pendente",
                row.id,
                row.storage_key,
            )
            continue
        try:
            entradas = _explode(blob, row.nome_arquivo)
        except zipfile.BadZipFile:
            logger.error("file_landing %s: zip corrompido — permanece pendente", row.id)
            continue

        for nome, data in entradas:
            if not nome.lower().endswith(".xml"):
                result.entradas_ignoradas += 1
                continue
            try:
                root, doc = xml_to_dict(data)
            except Exception:
                result.xml_invalidos += 1
                logger.warning("XML invalido em %s (%s)", row.storage_key, nome)
                continue
            if root == "procEventoNFe":
                result.eventos_descartados += 1
                continue
            if root == "nfeProc":
                await _ingest_nfe(db, row, nome, data, doc, result)
            elif root == "cteProc":
                await _ingest_cte(db, row, nome, data, doc, result)
            else:
                result.entradas_ignoradas += 1

        await db.execute(
            update(FileLanding)
            .where(FileLanding.id == row.id)
            .values(consumed_at=datetime.now(UTC))
        )
        result.landings_processados += 1
        await db.commit()

    _log_batch(db, tenant_id, result)
    await db.commit()
    return result


async def _ingest_nfe(
    db: AsyncSession,
    landing: FileLanding,
    nome: str,
    data: bytes,
    doc: dict,
    result: FiscalSyncResult,
) -> None:
    parsed = parse_nfe(doc)
    if parsed is None:
        result.xml_invalidos += 1
        return
    raw_id, created = await _upsert_raw(
        db, NfeRawDocumento, landing=landing, nome=nome, data=data, doc=doc, parsed=parsed
    )
    if not created:
        result.nfe_duplicadas += 1
        return
    nfe = Nfe(
        tenant_id=landing.tenant_id,
        raw_documento_id=raw_id,
        chave_acesso=parsed.chave_acesso,
        numero=parsed.numero,
        serie=parsed.serie,
        modelo=parsed.modelo,
        natureza_operacao=parsed.natureza_operacao,
        data_emissao=parsed.data_emissao,
        tipo_operacao=parsed.tipo_operacao,
        finalidade=parsed.finalidade,
        emitente_documento=parsed.emitente_documento,
        emitente_nome=parsed.emitente_nome,
        emitente_uf=parsed.emitente_uf,
        emitente_municipio=parsed.emitente_municipio,
        destinatario_documento=parsed.destinatario_documento,
        destinatario_tipo_pessoa=parsed.destinatario_tipo_pessoa,
        destinatario_nome=parsed.destinatario_nome,
        destinatario_uf=parsed.destinatario_uf,
        destinatario_municipio=parsed.destinatario_municipio,
        valor_produtos=parsed.valor_produtos,
        valor_frete=parsed.valor_frete,
        valor_desconto=parsed.valor_desconto,
        valor_total=parsed.valor_total,
        valor_tributos=parsed.valor_tributos,
        modalidade_frete=parsed.modalidade_frete,
        meio_pagamento=parsed.meio_pagamento,
        numero_fatura=parsed.numero_fatura,
        valor_fatura_liquido=parsed.valor_fatura_liquido,
        transportadora_documento=parsed.transportadora_documento,
        transportadora_nome=parsed.transportadora_nome,
        veiculo_placa=parsed.veiculo_placa,
        veiculo_uf=parsed.veiculo_uf,
        cstat=parsed.cstat,
        autorizada=parsed.autorizada,
        protocolo=parsed.protocolo,
        data_autorizacao=parsed.data_autorizacao,
        source_type=SourceType.DOCUMENT_NFE,
        source_id=parsed.chave_acesso,
        source_updated_at=parsed.data_autorizacao,
        hash_origem=hashlib.sha256(data).hexdigest(),
        ingested_by_version=ADAPTER_VERSION,
    )
    db.add(nfe)
    await db.flush()
    for dup in parsed.duplicatas:
        db.add(
            NfeDuplicata(
                tenant_id=landing.tenant_id,
                nfe_id=nfe.id,
                numero=dup.numero,
                vencimento=dup.vencimento,
                valor=dup.valor,
            )
        )
    for item in parsed.itens:
        db.add(
            NfeItem(
                tenant_id=landing.tenant_id,
                nfe_id=nfe.id,
                n_item=item.n_item,
                codigo=item.codigo,
                descricao=item.descricao,
                ncm=item.ncm,
                cfop=item.cfop,
                ean=item.ean,
                quantidade=item.quantidade,
                unidade=item.unidade,
                valor_unitario=item.valor_unitario,
                valor_total=item.valor_total,
            )
        )
    result.nfe_novas += 1


async def _ingest_cte(
    db: AsyncSession,
    landing: FileLanding,
    nome: str,
    data: bytes,
    doc: dict,
    result: FiscalSyncResult,
) -> None:
    parsed = parse_cte(doc)
    if parsed is None:
        result.xml_invalidos += 1
        return
    raw_id, created = await _upsert_raw(
        db, CteRawDocumento, landing=landing, nome=nome, data=data, doc=doc, parsed=parsed
    )
    if not created:
        result.cte_duplicados += 1
        return
    cte = Cte(
        tenant_id=landing.tenant_id,
        raw_documento_id=raw_id,
        chave_acesso=parsed.chave_acesso,
        numero=parsed.numero,
        serie=parsed.serie,
        cfop=parsed.cfop,
        natureza_operacao=parsed.natureza_operacao,
        data_emissao=parsed.data_emissao,
        tipo_cte=parsed.tipo_cte,
        municipio_inicio=parsed.municipio_inicio,
        uf_inicio=parsed.uf_inicio,
        municipio_fim=parsed.municipio_fim,
        uf_fim=parsed.uf_fim,
        emitente_documento=parsed.emitente_documento,
        emitente_nome=parsed.emitente_nome,
        remetente_documento=parsed.remetente_documento,
        remetente_nome=parsed.remetente_nome,
        destinatario_documento=parsed.destinatario_documento,
        destinatario_nome=parsed.destinatario_nome,
        expedidor_documento=parsed.expedidor_documento,
        recebedor_documento=parsed.recebedor_documento,
        tomador_codigo=parsed.tomador_codigo,
        valor_prestacao=parsed.valor_prestacao,
        valor_receber=parsed.valor_receber,
        valor_carga=parsed.valor_carga,
        produto_predominante=parsed.produto_predominante,
        cstat=parsed.cstat,
        autorizada=parsed.autorizada,
        protocolo=parsed.protocolo,
        data_autorizacao=parsed.data_autorizacao,
        source_type=SourceType.DOCUMENT_CTE,
        source_id=parsed.chave_acesso,
        source_updated_at=parsed.data_autorizacao,
        hash_origem=hashlib.sha256(data).hexdigest(),
        ingested_by_version=ADAPTER_VERSION,
    )
    db.add(cte)
    await db.flush()
    for chave in parsed.chaves_nfe:
        db.add(CteNfe(tenant_id=landing.tenant_id, cte_id=cte.id, chave_nfe=chave))
    result.cte_novos += 1


async def _upsert_raw(
    db: AsyncSession,
    model: type[NfeRawDocumento] | type[CteRawDocumento],
    *,
    landing: FileLanding,
    nome: str,
    data: bytes,
    doc: dict,
    parsed: NfeParsed | CteParsed,
) -> tuple[UUID, bool]:
    """Insere o raw JSONB; conflito de chave = documento ja ingerido (id, False)."""
    stmt = (
        pg_insert(model)
        .values(
            tenant_id=landing.tenant_id,
            chave_acesso=parsed.chave_acesso,
            schema_versao=parsed.schema_versao,
            documento=doc,
            file_landing_id=landing.id,
            nome_arquivo_xml=nome[:512],
            payload_sha256=hashlib.sha256(data).hexdigest(),
            fetched_by_version=ADAPTER_VERSION,
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "chave_acesso"]
        )
        .returning(model.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    if new_id is not None:
        return new_id, True
    existing = (
        await db.execute(
            select(model.id).where(
                model.tenant_id == landing.tenant_id,
                model.chave_acesso == parsed.chave_acesso,
            )
        )
    ).scalar_one()
    return existing, False


def _log_batch(db: AsyncSession, tenant_id: UUID, result: FiscalSyncResult) -> None:
    if result.landings_processados == 0:
        return
    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.SYNC,
            rule_or_model="fiscal_landing",
            rule_or_model_version=ADAPTER_VERSION,
            endpoint_name="fiscal_nfe+fiscal_cte",
            triggered_by="scheduler:fiscal_landing",
            inputs_ref={"landings": result.landings_processados},
            output=result.as_dict(),
            explanation=(
                f"Drain fiscal: {result.nfe_novas} NF-e novas, {result.cte_novos} CT-e "
                f"novos, {result.eventos_descartados} eventos descartados, "
                f"{result.xml_invalidos} XML invalidos."
            ),
        )
    )

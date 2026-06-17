"""Mappers KYC (BDC) -> silver canonico `wh_pj_kyc` + `wh_pj_kyc_ocorrencia`.

Recebe a UNIAO dos sujeitos (`map_kyc` da empresa + `map_owners_kyc` dos
socios) e faz UM delete-insert por (tenant, cnpj, source_type) nas duas
tabelas — assim a empresa e os socios sao reconciliados juntos numa consulta
(processar kyc e owners_kyc em chamadas separadas se apagariam). Nao commita.

Frescor (§14): header (flags) = dataset computado -> source_updated_at NULL;
cada ocorrencia carrega seu LastUpdateDate -> source_updated_at por registro.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType, TrustLevel
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.kyc import (
    KycSubjectFields,
)
from app.warehouse.pj_kyc import PjKyc, PjKycOcorrencia


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


async def replace_pj_kyc(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    cnpj: str,
    subjects: list[KycSubjectFields],
    raw_id: UUID | None,
    hash_origem: str | None,
    ingested_by_version: str,
    unidade_administrativa_id: UUID | None = None,
    source_type: SourceType = SourceType.BUREAU_BDC,
) -> tuple[int, int]:
    """Substitui headers + ocorrencias KYC de (tenant, cnpj, source_type).

    Retorna (n_sujeitos, n_ocorrencias) inseridos.
    """
    cnpj_digits = _digits(cnpj)
    where = lambda m: (  # noqa: E731
        (m.tenant_id == tenant_id)
        & (m.cnpj == cnpj_digits)
        & (m.source_type == source_type)
    )
    await db.execute(delete(PjKycOcorrencia).where(where(PjKycOcorrencia)))
    await db.execute(delete(PjKyc).where(where(PjKyc)))

    n_occ = 0
    headers: list[PjKyc] = []
    occs: list[PjKycOcorrencia] = []
    for subj in subjects:
        subj_doc = subj.subject_documento or "?"
        headers.append(
            PjKyc(
                tenant_id=tenant_id,
                unidade_administrativa_id=unidade_administrativa_id,
                raw_id=raw_id,
                cnpj=cnpj_digits,
                subject_documento=subj_doc,
                subject_tipo=subj.subject_tipo,
                subject_nome=subj.subject_nome,
                is_currently_pep=subj.is_currently_pep,
                is_currently_sanctioned=subj.is_currently_sanctioned,
                was_previously_sanctioned=subj.was_previously_sanctioned,
                count_sanctions=subj.count_sanctions,
                count_peps=subj.count_peps,
                last_30_days_sanctions=subj.last_30_days_sanctions,
                last_90_days_sanctions=subj.last_90_days_sanctions,
                last_180_days_sanctions=subj.last_180_days_sanctions,
                last_365_days_sanctions=subj.last_365_days_sanctions,
                last_year_pep=subj.last_year_pep,
                last_3y_pep=subj.last_3y_pep,
                last_5y_pep=subj.last_5y_pep,
                last_5plus_pep=subj.last_5plus_pep,
                source_type=source_type,
                source_id=f"{cnpj_digits}:{subj_doc}"[:255],
                source_updated_at=None,  # header computado -> idade = consulta
                ingested_by_version=ingested_by_version,
                hash_origem=hash_origem,
                trust_level=TrustLevel.HIGH,
            )
        )
        for i, oc in enumerate(subj.ocorrencias):
            n_occ += 1
            occs.append(
                PjKycOcorrencia(
                    tenant_id=tenant_id,
                    unidade_administrativa_id=unidade_administrativa_id,
                    raw_id=raw_id,
                    cnpj=cnpj_digits,
                    subject_documento=subj_doc,
                    subject_tipo=subj.subject_tipo,
                    subject_nome=subj.subject_nome,
                    categoria=oc.categoria,
                    fonte=oc.fonte,
                    tipo=oc.tipo,
                    match_rate=oc.match_rate,
                    name_uniqueness_score=oc.name_uniqueness_score,
                    nome_original=oc.nome_original,
                    nome_sancao=oc.nome_sancao,
                    is_current=oc.is_current,
                    data_inicio=oc.data_inicio,
                    data_fim=oc.data_fim,
                    detalhe=oc.detalhe,
                    source_type=source_type,
                    source_id=f"{cnpj_digits}:{subj_doc}:{oc.categoria}:{i}"[:255],
                    source_updated_at=oc.source_updated_at,
                    ingested_by_version=ingested_by_version,
                    hash_origem=hash_origem,
                    trust_level=TrustLevel.HIGH,
                )
            )

    db.add_all(headers)
    db.add_all(occs)
    return len(headers), n_occ

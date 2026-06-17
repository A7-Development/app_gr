"""Visões PARA O AGENTE do dossie societario + KYC (silver-first).

Builders que alimentam as read-tools `get_quadro_societario` e `get_kyc_pj`.
Resolvem a empresa-alvo (TARGET) do dossie -> CNPJ e leem o silver canonico
no warehouse (`wh_pj_vinculo`, `wh_pj_grupo_indicador`, `wh_pj_kyc`,
`wh_pj_kyc_ocorrencia`) — populado deterministicamente pelo node BDC. O agente
nunca toca silver direto (§13.2.1); consome esta view ja modelada.

Frescor (§14): cada view expoe a idade da informacao (source_updated_at quando
ha; senao a data da consulta). KYC aplica THRESHOLD de match_rate — o BDC casa
por NOME, entao match fraco e provavel homonimo, NAO sancao confirmada. Nada e
escondido: ocorrencias de baixa confianca sao contadas + rotuladas, nao
descartadas (zero ocultacao §14.6).

Contrato: hoje hand-shaped (sem contrato QSA/GRUPO/KYC seedado ainda). Quando o
contrato existir, migrar para projecao dirigida pelo contrato (como a cadastral).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole
from app.modules.credito.models.company import CreditDossierCompany
from app.warehouse.pj_grupo_indicador import PjGrupoIndicador
from app.warehouse.pj_kyc import PjKyc, PjKycOcorrencia
from app.warehouse.pj_vinculo import PjVinculo

# match_rate >= ALTA => confianca alta; abaixo = provavel homonimo (BDC casa
# por nome). Threshold conservador; o agente recebe o sinal, nao um corte cego.
_MATCH_RATE_ALTA = Decimal("80")

# Papeis de QSA/controle (vs funcionario/representante) — o que importa pra
# "quem controla a empresa".
_PAPEIS_CONTROLE = {"QSA", "Ownership"}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _target_cnpj(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> str | None:
    """CNPJ (14 digitos) da empresa-alvo do dossie, ou None."""
    target = (
        await db.execute(
            select(CreditDossierCompany.cnpj).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if not target:
        return None
    digits = "".join(ch for ch in target if ch.isdigit())
    return digits if len(digits) == 14 else None


async def build_quadro_societario_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Visão societaria para o agente: controle atual, churn e risco do grupo.

    Returns None quando não há empresa-alvo no dossie.
    """
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return None

    vinculos = (
        await db.execute(
            select(PjVinculo)
            .where(PjVinculo.tenant_id == tenant_id, PjVinculo.cnpj == cnpj)
            .order_by(PjVinculo.ativo.desc(), PjVinculo.data_inicio.desc())
        )
    ).scalars().all()

    if not vinculos:
        return {
            "encontrado": False,
            "cnpj": cnpj,
            "mensagem": (
                "Sem dados societarios coletados para esta empresa. "
                "Rode a consulta BDC antes."
            ),
        }

    controle_atual: list[dict] = []
    saidas_recentes: list[dict] = []
    frescor: datetime | None = None
    for v in vinculos:
        if v.source_updated_at and (frescor is None or v.source_updated_at > frescor):
            frescor = v.source_updated_at
        is_controle = (v.relationship_type or "") in _PAPEIS_CONTROLE
        if v.ativo and is_controle:
            controle_atual.append(
                {
                    "nome": v.nome,
                    "documento": v.documento_relacionado,
                    "tipo": v.tipo_pessoa,
                    "papel": v.relationship_name,
                    "desde": v.data_inicio.isoformat() if v.data_inicio else None,
                }
            )
        elif not v.ativo and is_controle and v.data_fim is not None:
            saidas_recentes.append(
                {
                    "nome": v.nome,
                    "papel": v.relationship_name,
                    "ate": v.data_fim.isoformat(),
                }
            )

    saidas_recentes.sort(key=lambda s: s["ate"] or "", reverse=True)

    grupo_row = (
        await db.execute(
            select(PjGrupoIndicador).where(
                PjGrupoIndicador.tenant_id == tenant_id,
                PjGrupoIndicador.cnpj == cnpj,
            )
        )
    ).scalar_one_or_none()
    grupo = None
    if grupo_row is not None:
        grupo = {
            "empresas": grupo_row.total_companies,
            "ativas": grupo_row.total_active,
            "socios_pessoas": grupo_row.total_people,
            "sancionados": grupo_row.total_sanctioned,
            "peps": grupo_row.total_peps,
            "processos": grupo_row.total_lawsuits,
        }

    return {
        "encontrado": True,
        "cnpj": cnpj,
        "controle_atual": controle_atual,
        "saidas_recentes": saidas_recentes,  # churn de controle (sinal)
        "vinculos_total": len(vinculos),
        "grupo_economico": grupo,
        "idade_da_informacao": _iso(frescor),  # data da fonte (LastUpdateDate)
        "nota": (
            "controle_atual = socios/quotistas ativos; saidas_recentes = "
            "mudanca recente de controle (avaliar estabilidade). Numeros do "
            "grupo sao agregados do 1o nivel."
        ),
    }


async def build_kyc_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Visão KYC para o agente: flags por sujeito + ocorrencias com confianca.

    Aplica threshold de match_rate (BDC casa por nome). Ocorrencias de baixa
    confianca NAO sao escondidas — vao contadas + rotuladas como provavel
    homonimo. Returns None quando não há empresa-alvo no dossie.
    """
    cnpj = await _target_cnpj(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if cnpj is None:
        return None

    headers = (
        await db.execute(
            select(PjKyc).where(PjKyc.tenant_id == tenant_id, PjKyc.cnpj == cnpj)
        )
    ).scalars().all()
    if not headers:
        return {
            "encontrado": False,
            "cnpj": cnpj,
            "mensagem": (
                "Sem KYC coletado para esta empresa. Rode a consulta BDC antes."
            ),
        }

    sujeitos = [
        {
            "documento": h.subject_documento,
            "tipo": h.subject_tipo,
            "nome": h.subject_nome,
            "pep": h.is_currently_pep,
            "sancionado": h.is_currently_sanctioned,
            "qtd_sancoes": h.count_sanctions,
            "qtd_pep": h.count_peps,
        }
        for h in headers
    ]

    ocorrencias = (
        await db.execute(
            select(PjKycOcorrencia)
            .where(
                PjKycOcorrencia.tenant_id == tenant_id,
                PjKycOcorrencia.cnpj == cnpj,
            )
            .order_by(PjKycOcorrencia.match_rate.desc().nullslast())
        )
    ).scalars().all()

    alta: list[dict] = []
    baixa_count = 0
    baixa_range: list[Decimal] = []
    for o in ocorrencias:
        mr = o.match_rate if o.match_rate is not None else Decimal("0")
        if mr >= _MATCH_RATE_ALTA:
            alta.append(
                {
                    "sujeito": o.subject_nome or o.subject_documento,
                    "documento": o.subject_documento,
                    "categoria": o.categoria,
                    "fonte": o.fonte,
                    "tipo": o.tipo,
                    "match_rate": float(mr),
                    "nome_na_sancao": o.nome_sancao,
                    "vigente": o.is_current,
                    "atualizado_em": _iso(o.source_updated_at),
                }
            )
        else:
            baixa_count += 1
            baixa_range.append(mr)

    baixa_resumo = None
    if baixa_count:
        lo = float(min(baixa_range))
        hi = float(max(baixa_range))
        faixa = f"{lo:.0f}%" if lo == hi else f"{lo:.0f}-{hi:.0f}%"
        baixa_resumo = (
            f"{baixa_count} ocorrencia(s) de BAIXA confianca (match {faixa}) "
            "— provavel homonimo por similaridade de nome. NAO tratar como "
            "sancao confirmada sem evidencia adicional."
        )

    return {
        "encontrado": True,
        "cnpj": cnpj,
        "sujeitos": sujeitos,
        "ocorrencias_confirmadas": alta,  # match_rate alto
        "ocorrencias_baixa_confianca_qtd": baixa_count,
        "ocorrencias_baixa_confianca_resumo": baixa_resumo,
        "nota_metodo": (
            "O bureau casa sancoes/PEP por NOME e devolve match_rate (0-100). "
            f"match_rate >= {int(_MATCH_RATE_ALTA)} = confianca alta; abaixo = "
            "provavel homonimo. Cada ocorrencia traz a data da fonte "
            "(atualizado_em) — pese o quao recente e o achado."
        ),
    }

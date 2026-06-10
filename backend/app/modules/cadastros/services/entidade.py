"""Cadastros — service da Ficha da Entidade (resumo/peek).

Le APENAS silver (wh_entidade*, wh_grupo_economico*, wh_serasa_pj_consulta),
escopado por tenant em toda query (CLAUDE.md §10, §13.2.1).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntidadePapel
from app.shared.documento import normalizar_documento
from app.warehouse.entidade import (
    WhEntidade,
    WhEntidadePapel,
    WhGrupoEconomico,
    WhGrupoEconomicoMembro,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta

_BUREAU_FONTE_LABEL = "Serasa Relato PJ"


async def get_resumo(
    db: AsyncSession, tenant_id: UUID, documento_raw: str
) -> dict | None:
    """Monta o resumo da entidade para o peek. None se nao existir."""
    doc = normalizar_documento(documento_raw)
    if doc is None:
        return None

    entidade = (
        await db.execute(
            select(WhEntidade).where(
                WhEntidade.tenant_id == tenant_id,
                WhEntidade.documento == doc.documento,
            )
        )
    ).scalar_one_or_none()
    if entidade is None:
        return None

    # --- Papeis ---
    papeis_rows = (
        await db.execute(
            select(WhEntidadePapel).where(
                WhEntidadePapel.tenant_id == tenant_id,
                WhEntidadePapel.entidade_id == entidade.id,
            )
        )
    ).scalars().all()
    papeis = [
        {
            "papel": p.papel.value,
            "source_id": p.source_id,
            "status_fonte": p.status_fonte,
        }
        for p in papeis_rows
    ]
    cedente_id: int | None = None
    for p in papeis_rows:
        if p.papel == EntidadePapel.CEDENTE and p.source_id.isdigit():
            cedente_id = int(p.source_id)
            break

    # --- Estabelecimentos da mesma raiz (PJ) ---
    estabelecimentos: list[dict] = []
    if entidade.documento_raiz:
        est_rows = (
            await db.execute(
                select(WhEntidade)
                .where(
                    WhEntidade.tenant_id == tenant_id,
                    WhEntidade.documento_raiz == entidade.documento_raiz,
                )
                .order_by(WhEntidade.is_matriz.desc(), WhEntidade.filial_numero)
            )
        ).scalars().all()
        estabelecimentos = [
            {
                "documento": e.documento,
                "nome": e.nome,
                "filial_numero": e.filial_numero,
                "is_matriz": e.is_matriz,
                "localidade": e.localidade,
                "estado": e.estado,
            }
            for e in est_rows
        ]

    # --- Grupo economico + membros (com papeis de cada membro) ---
    grupo: dict | None = None
    if entidade.grupo_economico_source_id is not None:
        grupo_row = (
            await db.execute(
                select(WhGrupoEconomico).where(
                    WhGrupoEconomico.tenant_id == tenant_id,
                    WhGrupoEconomico.source_id
                    == str(entidade.grupo_economico_source_id),
                )
            )
        ).scalar_one_or_none()
        if grupo_row is not None:
            membro_rows = (
                await db.execute(
                    select(WhGrupoEconomicoMembro, WhEntidade)
                    .outerjoin(
                        WhEntidade,
                        WhEntidade.id == WhGrupoEconomicoMembro.entidade_id,
                    )
                    .where(
                        WhGrupoEconomicoMembro.tenant_id == tenant_id,
                        WhGrupoEconomicoMembro.grupo_economico_id == grupo_row.id,
                    )
                )
            ).all()
            membro_ids = [
                ent.id for _m, ent in membro_rows if ent is not None
            ]
            papeis_por_entidade: dict[UUID, list[str]] = {}
            if membro_ids:
                for ent_id, papel in (
                    await db.execute(
                        select(
                            WhEntidadePapel.entidade_id, WhEntidadePapel.papel
                        ).where(
                            WhEntidadePapel.tenant_id == tenant_id,
                            WhEntidadePapel.entidade_id.in_(membro_ids),
                        )
                    )
                ).all():
                    papeis_por_entidade.setdefault(ent_id, []).append(papel.value)
            grupo = {
                "nome": grupo_row.nome,
                "segmento": grupo_row.segmento,
                "membros": [
                    {
                        "documento": ent.documento if ent else None,
                        "nome": ent.nome if ent else None,
                        "vinculo": m.vinculo,
                        "papeis": papeis_por_entidade.get(ent.id, [])
                        if ent
                        else [],
                    }
                    for m, ent in membro_rows
                ],
            }

    # --- Bureau: ultima consulta Serasa do documento ---
    bureau: dict | None = None
    consulta = (
        await db.execute(
            select(SerasaPjConsulta)
            .where(
                SerasaPjConsulta.tenant_id == tenant_id,
                SerasaPjConsulta.cnpj == entidade.documento,
            )
            .order_by(SerasaPjConsulta.consulted_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if consulta is not None:
        bureau = {
            "fonte": _BUREAU_FONTE_LABEL,
            "consultado_em": consulta.consulted_at,
            "score": consulta.score_h4pj,
            "score_classe": consulta.score_classe,
            "protestos_qtd": consulta.count_protesto,
            "pefin_qtd": consulta.count_pefin,
            "refin_qtd": consulta.count_refin,
            "cheques_qtd": consulta.count_cheque,
            "acoes_judiciais_qtd": consulta.count_acoes_judiciais,
            "falencias_qtd": consulta.count_falencias,
            "valor_total_restricoes": float(consulta.valor_total_restricoes)
            if consulta.valor_total_restricoes is not None
            else None,
        }

    return {
        "documento": entidade.documento,
        "tipo_pessoa": entidade.tipo_pessoa.value,
        "nome": entidade.nome,
        "documento_raiz": entidade.documento_raiz,
        "filial_numero": entidade.filial_numero,
        "is_matriz": entidade.is_matriz,
        "cnae_chave": entidade.cnae_chave,
        "cnae_denominacao": entidade.cnae_denominacao,
        "porte": entidade.porte,
        "data_constituicao": entidade.data_constituicao,
        "em_recuperacao_judicial": entidade.em_recuperacao_judicial,
        "data_recuperacao_judicial": entidade.data_recuperacao_judicial,
        "localidade": entidade.localidade,
        "estado": entidade.estado,
        "papeis": papeis,
        "cedente_id": cedente_id,
        "estabelecimentos": estabelecimentos,
        "grupo": grupo,
        "bureau": bureau,
        "source_type": entidade.source_type.value,
        "ingested_at": entidade.ingested_at,
    }

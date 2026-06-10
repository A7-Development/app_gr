"""Cadastros — service da Ficha da Entidade (resumo/peek).

Le APENAS silver (wh_entidade*, wh_grupo_economico*, wh_serasa_pj_consulta),
escopado por tenant em toda query (CLAUDE.md §10, §13.2.1).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EntidadePapel
from app.shared.documento import normalizar_documento
from app.warehouse.entidade import (
    WhEntidade,
    WhEntidadePapel,
    WhGrupoEconomico,
    WhGrupoEconomicoMembro,
)
from app.warehouse.posicao_papel import (
    WhPosicaoCedente,
    WhPosicaoCedenteProduto,
    WhPosicaoSacado,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta

_BUREAU_FONTE_LABEL = "Serasa Relato PJ"


def _f(value: object) -> float:
    """Decimal/None -> float (0.0 para None — agregados monetarios)."""
    return float(value) if value is not None else 0.0


def _fn(value: object) -> float | None:
    return float(value) if value is not None else None


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
    grupo_entidade_ids: list[UUID] = []
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
            grupo_entidade_ids = membro_ids
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

    # --- Posicoes por papel (F1): carteira ativa + limites + performance ---
    pos_ced = (
        await db.execute(
            select(WhPosicaoCedente).where(
                WhPosicaoCedente.tenant_id == tenant_id,
                WhPosicaoCedente.entidade_id == entidade.id,
            )
        )
    ).scalars().first()
    pos_sac = (
        await db.execute(
            select(WhPosicaoSacado).where(
                WhPosicaoSacado.tenant_id == tenant_id,
                WhPosicaoSacado.entidade_id == entidade.id,
            )
        )
    ).scalars().first()

    carteira_ativa: list[dict] = []
    if pos_ced is not None or pos_sac is not None:
        ced_v = _f(pos_ced.risco_total_valor) if pos_ced else 0.0
        sac_v = _f(pos_sac.risco_total_valor) if pos_sac else 0.0
        carteira_ativa.append(
            {
                "escopo": "cnpj",
                "cedente_valor": ced_v,
                "sacado_valor": sac_v,
                "total": ced_v + sac_v,
                "cedente_vencido": _f(pos_ced.risco_vencido_valor) if pos_ced else 0.0,
                "sacado_vencido": _f(pos_sac.risco_vencido_valor) if pos_sac else 0.0,
            }
        )

    # Escopo GRUPO: soma sobre todas as entidades do grupo (inclui a propria).
    ids_grupo = {*grupo_entidade_ids, entidade.id} if grupo_entidade_ids else set()
    if ids_grupo and len(ids_grupo) > 1:
        ced_g = (
            await db.execute(
                select(
                    func.coalesce(func.sum(WhPosicaoCedente.risco_total_valor), 0),
                    func.coalesce(func.sum(WhPosicaoCedente.risco_vencido_valor), 0),
                ).where(
                    WhPosicaoCedente.tenant_id == tenant_id,
                    WhPosicaoCedente.entidade_id.in_(ids_grupo),
                )
            )
        ).one()
        sac_g = (
            await db.execute(
                select(
                    func.coalesce(func.sum(WhPosicaoSacado.risco_total_valor), 0),
                    func.coalesce(func.sum(WhPosicaoSacado.risco_vencido_valor), 0),
                ).where(
                    WhPosicaoSacado.tenant_id == tenant_id,
                    WhPosicaoSacado.entidade_id.in_(ids_grupo),
                )
            )
        ).one()
        if _f(ced_g[0]) + _f(sac_g[0]) > 0 or carteira_ativa:
            carteira_ativa.append(
                {
                    "escopo": "grupo",
                    "cedente_valor": _f(ced_g[0]),
                    "sacado_valor": _f(sac_g[0]),
                    "total": _f(ced_g[0]) + _f(sac_g[0]),
                    "cedente_vencido": _f(ced_g[1]),
                    "sacado_vencido": _f(sac_g[1]),
                }
            )

    limites_rows = (
        await db.execute(
            select(WhPosicaoCedenteProduto)
            .where(
                WhPosicaoCedenteProduto.tenant_id == tenant_id,
                WhPosicaoCedenteProduto.entidade_id == entidade.id,
            )
            .order_by(WhPosicaoCedenteProduto.limite_operacional.desc())
        )
    ).scalars().all()
    limites = [
        {
            "produto_sigla": lr.produto_sigla,
            "limite": _f(lr.limite_operacional),
            "em_uso": _f(lr.risco_total_valor),
            "vencido": _f(lr.risco_vencido_valor),
        }
        for lr in limites_rows
        if _f(lr.limite_operacional) > 0 or _f(lr.risco_total_valor) > 0
    ]

    # Performance: lente cedente quando ha; senao a lente sacado.
    performance: dict | None = None
    pos_perf = pos_ced if pos_ced is not None else pos_sac
    if pos_perf is not None and pos_perf.vencimentario_liquidez is not None:
        performance = {
            "papel": "cedente" if pos_perf is pos_ced else "sacado",
            "indice_liquidez": _fn(pos_perf.indice_liquidez),
            "vencimentario": _fn(pos_perf.vencimentario_liquidez),
            "liquidados": _fn(pos_perf.liquidez_total_liquidados),
            "recomprados": _fn(pos_perf.liquidez_total_recomprados),
            "vencidos_penalizados": _fn(pos_perf.liquidez_total_vencidos_penalizados),
            "vencidos_nao_penalizados": _fn(
                pos_perf.liquidez_total_vencidos_nao_penalizados
            ),
            "janela_dias": pos_perf.liquidez_qtde_dias,
            "data_apuracao": pos_perf.liquidez_data_apuracao,
            "prazo_medio_carteira": _fn(pos_ced.prazo_medio_carteira)
            if pos_ced is not None
            else None,
            "indice_pontualidade": _fn(pos_sac.indice_pontualidade)
            if pos_perf is pos_sac and pos_sac is not None
            else None,
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
        "carteira_ativa": carteira_ativa,
        "limites": limites,
        "performance": performance,
        "bureau": bureau,
        "source_type": entidade.source_type.value,
        "ingested_at": entidade.ingested_at,
    }

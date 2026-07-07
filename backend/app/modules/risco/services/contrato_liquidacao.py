"""Liquidation contract per product: active version + observed profile.

Reads ONLY silver tables (wh_dim_produto, wh_titulo, wh_operacao,
wh_boleto_vigente — CLAUDE.md 13.2.1). Product of a title comes from
`split_part(wh_operacao.modalidade, '-', 1)` ('FAT-DM' -> 'FAT'), the same
convention used by the BI services.

"Bancarizado" = the title's `numero` matches a `wh_boleto_vigente.numero_documento`
row of the same tenant (fold identity per documento — memoria
project_conciliacao_boletos_estado_vigente). "Baixa manual em bancarizado" =
title liquidated (situacao=1) that HAS a boleto but no boleto in state
'liquidado' — i.e. the money did not arrive through the bank rail.
NOTE: this is the S3v2-style inference; F3 (wh_liquidacao with the declared
Bitfin outcome) will replace it with declared data.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risco.models.contrato_liquidacao import (
    ExpectativaBaixaManual,
    ExpectativaBoleto,
    ProdutoContratoLiquidacao,
)
from app.modules.risco.schemas.contrato_liquidacao import (
    ContratoLiquidacaoRow,
    ContratoLiquidacaoUpdate,
    ContratoLiquidacaoVersao,
    PerfilObservado,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.dim import DimProduto

logger = logging.getLogger(__name__)

SERVICE_VERSION = "contrato_liquidacao_v1"

# Divergence thresholds (percentage points over the observed window).
# Deliberately coarse: the badge is a CURATION prompt (observado vs declarado),
# not a fraud score — the signal engine (F4) does the scoring per title.
_BOLETO_NAO_ESPERADO_MAX_PCT = 10.0  # >10% bancarizado where none is expected
_BOLETO_OBRIGATORIO_MIN_PCT = 90.0  # <90% bancarizado where it is mandatory

DIVERGENCIA_VOLUME_EM_ABERTO = "volume_em_produto_aberto"
DIVERGENCIA_BOLETO_ALEM = "boleto_alem_do_esperado"
DIVERGENCIA_BOLETO_ABAIXO = "boleto_abaixo_do_esperado"
DIVERGENCIA_BAIXA_MANUAL_ANOMALA = "baixa_manual_em_produto_anomalo"

_PERFIL_SQL = text(
    """
    WITH t AS (
        SELECT
            split_part(op.modalidade, '-', 1) AS produto,
            ti.situacao,
            ti.valor,
            EXISTS (
                SELECT 1 FROM wh_boleto_vigente bv
                WHERE bv.tenant_id = ti.tenant_id
                  AND bv.numero_documento = ti.numero
            ) AS bancarizado,
            EXISTS (
                SELECT 1 FROM wh_boleto_vigente bv
                WHERE bv.tenant_id = ti.tenant_id
                  AND bv.numero_documento = ti.numero
                  AND bv.estado = 'liquidado'
            ) AS boleto_liquidado
        FROM wh_titulo ti
        JOIN wh_operacao op
          ON op.tenant_id = ti.tenant_id
         AND op.operacao_id = ti.operacao_id
        WHERE ti.tenant_id = :tenant_id
          AND ti.data_de_cadastro >= :cutoff
    )
    SELECT
        produto,
        count(*)                                            AS qtd_titulos,
        coalesce(sum(valor), 0)                             AS valor_total,
        count(*) FILTER (WHERE bancarizado)                 AS qtd_bancarizados,
        count(*) FILTER (
            WHERE bancarizado AND situacao = 1 AND NOT boleto_liquidado
        )                                                   AS qtd_baixa_manual
    FROM t
    GROUP BY produto
    """
)


async def _perfil_por_produto(
    db: AsyncSession, tenant_id: UUID, janela_dias: int
) -> dict[str, PerfilObservado]:
    cutoff = datetime.now(UTC) - timedelta(days=janela_dias)
    rows = (
        await db.execute(_PERFIL_SQL, {"tenant_id": tenant_id, "cutoff": cutoff})
    ).all()
    perfis: dict[str, PerfilObservado] = {}
    for produto, qtd, valor_total, qtd_banc, qtd_manual in rows:
        perfis[produto] = PerfilObservado(
            janela_dias=janela_dias,
            qtd_titulos=qtd,
            valor_total=float(valor_total),
            qtd_bancarizados=qtd_banc,
            qtd_baixa_manual_bancarizados=qtd_manual,
            pct_bancarizado=round(100.0 * qtd_banc / qtd, 1) if qtd else None,
            pct_baixa_manual_bancarizados=(
                round(100.0 * qtd_manual / qtd_banc, 1) if qtd_banc else None
            ),
        )
    return perfis


def _perfil_vazio(janela_dias: int) -> PerfilObservado:
    return PerfilObservado(
        janela_dias=janela_dias,
        qtd_titulos=0,
        valor_total=0.0,
        qtd_bancarizados=0,
        qtd_baixa_manual_bancarizados=0,
        pct_bancarizado=None,
        pct_baixa_manual_bancarizados=None,
    )


def _divergencias(
    contrato: ProdutoContratoLiquidacao | None, obs: PerfilObservado
) -> list[str]:
    """Curation flags where observed behaviour contradicts the declaration."""
    out: list[str] = []
    if contrato is None:
        # Volume flowing through a product with no contract = curation item
        # (decisao 2026-07-07: "volume novo em produto aberto").
        if obs.qtd_titulos > 0:
            out.append(DIVERGENCIA_VOLUME_EM_ABERTO)
        return out

    pct = obs.pct_bancarizado
    if pct is not None:
        if (
            contrato.boleto == ExpectativaBoleto.NAO_ESPERADO
            and pct > _BOLETO_NAO_ESPERADO_MAX_PCT
        ):
            out.append(DIVERGENCIA_BOLETO_ALEM)
        if (
            contrato.boleto == ExpectativaBoleto.OBRIGATORIO
            and pct < _BOLETO_OBRIGATORIO_MIN_PCT
        ):
            out.append(DIVERGENCIA_BOLETO_ABAIXO)

    if (
        contrato.baixa_manual == ExpectativaBaixaManual.ANOMALA
        and obs.qtd_baixa_manual_bancarizados > 0
    ):
        out.append(DIVERGENCIA_BAIXA_MANUAL_ANOMALA)
    return out


async def _contratos_ativos(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, ProdutoContratoLiquidacao]:
    """Latest version per produto_sigla (append-only -> max version wins)."""
    rows = (
        (
            await db.execute(
                select(ProdutoContratoLiquidacao)
                .where(ProdutoContratoLiquidacao.tenant_id == tenant_id)
                .order_by(
                    ProdutoContratoLiquidacao.produto_sigla,
                    ProdutoContratoLiquidacao.version,
                )
            )
        )
        .scalars()
        .all()
    )
    ativos: dict[str, ProdutoContratoLiquidacao] = {}
    for row in rows:  # ordered by version asc -> last one wins
        ativos[row.produto_sigla] = row
    return ativos


def _to_row(
    sigla: str,
    nome: str,
    contrato: ProdutoContratoLiquidacao | None,
    obs: PerfilObservado,
) -> ContratoLiquidacaoRow:
    return ContratoLiquidacaoRow(
        produto_sigla=sigla,
        produto_nome=nome,
        version=contrato.version if contrato else None,
        fluxo_esperado=contrato.fluxo_esperado if contrato else None,
        boleto=contrato.boleto if contrato else None,
        baixa_manual=contrato.baixa_manual if contrato else None,
        justificativa=contrato.justificativa if contrato else None,
        atualizado_em=contrato.created_at if contrato else None,
        em_aberto=contrato is None,
        observado=obs,
        divergencias=_divergencias(contrato, obs),
    )


async def list_contratos(
    db: AsyncSession, tenant_id: UUID, *, janela_dias: int = 180
) -> list[ContratoLiquidacaoRow]:
    """All products of the tenant (from wh_dim_produto) + contract + profile.

    The listing is driven by the product dimension so a NEW product coming
    from the ERP shows up automatically as "em aberto" — that arrival is
    itself a curation event.
    """
    produtos = (
        await db.execute(
            select(DimProduto.sigla, DimProduto.nome)
            .where(DimProduto.tenant_id == tenant_id)
            .order_by(DimProduto.nome)
        )
    ).all()
    ativos = await _contratos_ativos(db, tenant_id)
    perfis = await _perfil_por_produto(db, tenant_id, janela_dias)
    return [
        _to_row(sigla, nome, ativos.get(sigla), perfis.get(sigla, _perfil_vazio(janela_dias)))
        for sigla, nome in produtos
    ]


async def get_contrato(
    db: AsyncSession, tenant_id: UUID, produto_sigla: str, *, janela_dias: int = 180
) -> ContratoLiquidacaoRow | None:
    """Single product row; None when the sigla is not in wh_dim_produto."""
    nome = (
        await db.execute(
            select(DimProduto.nome).where(
                DimProduto.tenant_id == tenant_id,
                DimProduto.sigla == produto_sigla,
            )
        )
    ).scalar_one_or_none()
    if nome is None:
        return None
    ativos = await _contratos_ativos(db, tenant_id)
    perfis = await _perfil_por_produto(db, tenant_id, janela_dias)
    return _to_row(
        produto_sigla,
        nome,
        ativos.get(produto_sigla),
        perfis.get(produto_sigla, _perfil_vazio(janela_dias)),
    )


async def definir_contrato(
    db: AsyncSession,
    tenant_id: UUID,
    produto_sigla: str,
    body: ContratoLiquidacaoUpdate,
    *,
    user_id: UUID | None,
) -> ProdutoContratoLiquidacao | None:
    """Insert a NEW version of the contract (append-only, premise_set style).

    Returns None when the sigla does not exist in wh_dim_produto (router
    turns it into 404). Caller commits.
    """
    exists = (
        await db.execute(
            select(DimProduto.id).where(
                DimProduto.tenant_id == tenant_id,
                DimProduto.sigla == produto_sigla,
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        return None

    atual = (
        await db.execute(
            select(ProdutoContratoLiquidacao)
            .where(
                ProdutoContratoLiquidacao.tenant_id == tenant_id,
                ProdutoContratoLiquidacao.produto_sigla == produto_sigla,
            )
            .order_by(ProdutoContratoLiquidacao.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    novo = ProdutoContratoLiquidacao(
        tenant_id=tenant_id,
        produto_sigla=produto_sigla,
        version=(atual.version + 1) if atual else 1,
        fluxo_esperado=body.fluxo_esperado,
        boleto=body.boleto,
        baixa_manual=body.baixa_manual,
        justificativa=body.justificativa,
        created_by=user_id,
    )
    db.add(novo)

    db.add(
        DecisionLog(
            tenant_id=tenant_id,
            decision_type=DecisionType.CONFIGURATION_CHANGE,
            rule_or_model="produto_contrato_liquidacao",
            rule_or_model_version=SERVICE_VERSION,
            endpoint_name="risco.contratos_liquidacao.definir",
            triggered_by=f"user:{user_id}" if user_id else "system",
            inputs_ref={
                "produto_sigla": produto_sigla,
                "version_anterior": atual.version if atual else None,
            },
            output={
                "version": novo.version,
                "fluxo_esperado": body.fluxo_esperado.value,
                "boleto": body.boleto.value,
                "baixa_manual": body.baixa_manual.value,
            },
            explanation=(
                f"Contrato de liquidacao do produto {produto_sigla} "
                f"definido (v{novo.version})."
            ),
        )
    )
    await db.flush()
    return novo


async def list_versoes(
    db: AsyncSession, tenant_id: UUID, produto_sigla: str
) -> list[ContratoLiquidacaoVersao]:
    rows = (
        (
            await db.execute(
                select(ProdutoContratoLiquidacao)
                .where(
                    ProdutoContratoLiquidacao.tenant_id == tenant_id,
                    ProdutoContratoLiquidacao.produto_sigla == produto_sigla,
                )
                .order_by(ProdutoContratoLiquidacao.version.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        ContratoLiquidacaoVersao(
            version=r.version,
            fluxo_esperado=r.fluxo_esperado,
            boleto=r.boleto,
            baixa_manual=r.baixa_manual,
            justificativa=r.justificativa,
            created_at=r.created_at,
            created_by=r.created_by,
        )
        for r in rows
    ]

"""Feature builder of the liquidation detection model (modelo `liquidacao_boleto`).

Builds READY features per wh_liquidacao event (canais `bancaria` +
`baixa_manual`) — the model multiplies and sums, it never derives arithmetic
(hard handoff rule). Every feature is declared data or an intra-cedente
relative measure; lastro/fiscal information is deliberately NOT a feature
(circular with proxy labels — decisao 2026-07-08).

Feature families (memoria project_deteccao_anomalias_liquidacao):
    praca (S1)        declared bank bits + exact match against the cedente's
                      registered accounts (wh_conta_bancaria) + municipality
                      triangulation via RefBacen (never the Bitfin AgenciaId
                      FK — known NULL trap).
    canal (F2)        RefBacenResolver one-hot (cooperativa is its own class,
                      never sintonia fina — decisao Ricardo F2).
    fingerprint (S4)  1 - share of the paying bank in the SACADO's own
                      history; only scores when the sacado has >= 3 paid
                      events AND a stable habit (dominant share >= 0.8).
    compartilhada(S2) distinct sacados of the same cedente paying at the
                      same physical branch (12m window), minus exclusions.
    mecanica (S3v3)   declared evidence of the manual write-off.
    timing (S5)       paid exactly on due date; same-day batch size.
    contrato          product contract states + "observed violates declared".
    relativas         ticket z-score vs the cedente's own baseline.

Hard rule (deterministic, independent of any trained model): sacado from
another city paying at a branch where the CEDENTE banks. Fires regardless
of score; never trained, never regresses.
"""

from __future__ import annotations

import logging
import math
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.public import (
    CANAL_BANCO_PRACA,
    CANAL_COOPERATIVA,
    CANAL_IP,
    CANAL_NAO_RESOLVIDO,
    RefBacenResolver,
)
from app.warehouse.ref_bacen import (
    SEGMENTO_BANCO,
    SEGMENTO_BANCO_COOPERATIVO,
    SEGMENTO_COOPERATIVA,
    SEGMENTO_FINANCEIRA,
    SEGMENTO_IP,
    SEGMENTO_SCD,
)

logger = logging.getLogger(__name__)

# Exclusoes parametricas do S2 (agencias-gateway de infraestrutura: pagam N
# sacados de N cedentes por desenho, nao por fraude). Calibrado no F0:
# Santander 033/2271 = gateway (11 cedentes / 79 sacados). Promover a tabela
# versionada quando a lista crescer (hoje: 1 entrada, constante documentada).
_EXCLUSOES_AGENCIA_GATEWAY: frozenset[tuple[str, str]] = frozenset({("033", "02271")})

_FINGERPRINT_MIN_EVENTOS = 3
_FINGERPRINT_MIN_ESTABILIDADE = 0.8

# Ordem canonica das features — treino e score compartilham este contrato.
# TRILHO B REMOVIDO (2026-07-08): os bits de praca do ERP (bit_pago_agencia_
# cliente / bit_pago_praca_cliente / bit_fora_praca_sacado / pago_banco_
# digital) sairam — a praca agora vem SO da resolucao propria (escada Bacen
# -> cadastro ERP), com `praca_fonte` distinguindo a origem.
FEATURE_NAMES: tuple[str, ...] = (
    "match_agencia_conta_cedente",
    "cidade_pgto_eq_cedente",
    "cidade_pgto_neq_sacado",
    "praca_fonte_bacen",
    "praca_fonte_cadastro_erp",
    "praca_nao_resolvida",
    "canal_cooperativa",
    "canal_ip",
    "canal_sem_praca",
    "canal_nao_resolvido",
    "quebra_fingerprint",
    "agencia_compartilhada",
    "agencia_compartilhada_cedentes",
    "canal_baixa_manual",
    "baixa_confirmada",
    "sem_ocorrencia",
    "baixa_manual_produto_anomala",
    "boleto_nao_esperado_mas_teve",
    "contrato_aberto",
    "pago_exato_vencimento",
    "lote_dia",
    "ticket_z",
    "valor_log",
)


@dataclass
class FeatureRow:
    """One scored unit: features + hard-rule verdict + display context."""

    liquidacao_id: UUID
    titulo_id: int
    cedente_documento: str | None
    cedente_nome: str | None
    produto_sigla: str | None
    sacado_documento: str | None
    data_evento: datetime
    valor: float | None
    canal: str
    evidencia: str | None
    features: dict[str, float] = field(default_factory=dict)
    regra_dura: bool = False
    regra_dura_motivo: str | None = None


def _norm_cidade(nome: str | None) -> str | None:
    """Uppercase + strip accents; None-safe (string compare guarded by UF)."""
    if not nome or not nome.strip():
        return None
    s = unicodedata.normalize("NFKD", nome.strip().upper())
    return "".join(c for c in s if not unicodedata.combining(c))


def _doc(documento: str | None) -> str | None:
    """Normalize a document across sources: digits only, last 14 when longer.

    wh_operacao.cedente_documento comes 15-digit zero-padded from the ERP
    while wh_entidade.documento is the canonical 14 — without this the city
    lookups silently miss (validated on real data 2026-07-08).
    """
    if not documento:
        return None
    d = "".join(c for c in documento if c.isdigit())
    if not d:
        return None
    return d[-14:] if len(d) > 14 else d


def _raiz(documento: str | None) -> str | None:
    """CNPJ root (8 digits) = all establishments of the same company."""
    d = _doc(documento)
    if d and len(d) == 14:
        return d[:8]
    return d


# --- main event query -------------------------------------------------------
# Um evento por linha + titulo + operacao + contrato ativo (maior version) +
# melhor evento CNAB do boleto correspondente (praca REAL: banco/agencia do
# arquivo de retorno — F1). LATERAL escolhe o evento de pagamento.
_SQL_EVENTOS = text("""
WITH contrato_ativo AS (
    SELECT DISTINCT ON (tenant_id, produto_sigla)
        tenant_id, produto_sigla, fluxo_esperado, boleto, baixa_manual
    FROM produto_contrato_liquidacao
    ORDER BY tenant_id, produto_sigla, version DESC
)
SELECT
    l.id                AS liquidacao_id,
    l.titulo_id,
    l.canal,
    l.evidencia,
    l.data_evento,
    l.valor_pago,
    l.valor_titulo,
    l.pago_fora_praca_sacado,
    l.pago_na_praca_cliente,
    l.pago_na_agencia_cliente,
    l.pago_em_banco_digital,
    t.numero            AS titulo_numero,
    t.data_de_vencimento,
    t.data_de_vencimento_efetiva,
    o.cedente_documento,
    o.cedente_nome,
    split_part(o.modalidade, '-', 1) AS produto_sigla,
    ca.boleto           AS contrato_boleto,
    ca.baixa_manual     AS contrato_baixa_manual,
    ev.banco_pagador,
    ev.agencia_pagadora,
    sac.documento       AS sacado_documento
FROM wh_liquidacao l
JOIN wh_titulo t
    ON t.titulo_id = l.titulo_id AND t.tenant_id = l.tenant_id
LEFT JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
LEFT JOIN contrato_ativo ca
    ON ca.tenant_id = l.tenant_id
   AND ca.produto_sigla = split_part(o.modalidade, '-', 1)
-- Praca do proprio evento desta liquidacao (identidade estavel titulo_id,
-- NAO nosso_numero — que colide entre cedentes). Desempate por valor do
-- evento mais proximo do valor liquidado (§ fix 2026-07-09).
LEFT JOIN LATERAL (
    SELECT be.banco_pagador, be.agencia_pagadora
    FROM wh_boleto_evento be
    WHERE be.tenant_id = l.tenant_id
      AND be.titulo_id = l.titulo_id
      AND be.banco_pagador IS NOT NULL
    ORDER BY abs(coalesce(be.valor_pago, 0) - coalesce(l.valor_pago, 0)) ASC,
             be.data_ocorrencia DESC
    LIMIT 1
) ev ON true
-- Sacado do TITULO (autoritativo): sacado_id e ID de PAPEL (Bitfin SacadoId)
-- — a ponte e wh_entidade_papel.source_id, NUNCA wh_entidade.source_id
-- (que e EntidadeId; espacos de ID diferentes — bug 2026-07-09: titulo 39535
-- resolvia Ey Espumas em vez de Mega Pack).
LEFT JOIN wh_entidade_papel pap
    ON pap.tenant_id = l.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
WHERE l.tenant_id = :tenant_id
  AND l.canal IN ('bancaria', 'baixa_manual')
""")

# Fingerprint do sacado: historico de pagamentos com praca por sacado.
# Identidade via titulo_id (nao nosso_numero, que colide); sacado do TITULO.
_SQL_FINGERPRINT = text("""
SELECT sac.documento AS sacado_documento, be.banco_pagador, count(*) AS n
FROM wh_boleto_evento be
JOIN wh_titulo t ON t.tenant_id = be.tenant_id AND t.titulo_id = be.titulo_id
JOIN wh_entidade_papel pap
    ON pap.tenant_id = be.tenant_id AND pap.papel = 'sacado'
   AND pap.source_id = t.sacado_id::text
JOIN wh_entidade sac ON sac.id = pap.entidade_id
WHERE be.tenant_id = :tenant_id
  AND be.banco_pagador IS NOT NULL
  AND be.valor_pago > 0
GROUP BY sac.documento, be.banco_pagador
""")

# S2: por (banco, agencia fisica, 12m) — sacados distintos POR CEDENTE e o
# total de CEDENTES distintos na agencia (dimensao de rede: operador comum).
_SQL_AGENCIA_COMPARTILHADA = text("""
WITH base AS (
    -- Identidade via titulo_id (nao nosso_numero, que colide); sacado e
    -- cedente do TITULO autoritativo.
    SELECT DISTINCT o.cedente_documento, sac.documento AS sacado_documento,
           be.banco_pagador, be.agencia_pagadora
    FROM wh_boleto_evento be
    JOIN wh_titulo t
        ON t.tenant_id = be.tenant_id AND t.titulo_id = be.titulo_id
    JOIN wh_operacao o
        ON o.operacao_id = t.operacao_id AND o.tenant_id = t.tenant_id
    LEFT JOIN wh_entidade_papel pap
        ON pap.tenant_id = be.tenant_id AND pap.papel = 'sacado'
       AND pap.source_id = t.sacado_id::text
    LEFT JOIN wh_entidade sac ON sac.id = pap.entidade_id
    WHERE be.tenant_id = :tenant_id
      AND be.banco_pagador IS NOT NULL
      AND be.agencia_pagadora IS NOT NULL
      AND be.valor_pago > 0
      AND be.data_ocorrencia >= now() - interval '365 days'
),
por_agencia AS (
    SELECT banco_pagador, agencia_pagadora,
           count(DISTINCT cedente_documento) AS n_cedentes
    FROM base GROUP BY banco_pagador, agencia_pagadora
)
SELECT b.cedente_documento, b.banco_pagador, b.agencia_pagadora,
       count(DISTINCT b.sacado_documento) AS n_sacados,
       max(pa.n_cedentes) AS n_cedentes
FROM base b
JOIN por_agencia pa
    ON pa.banco_pagador = b.banco_pagador
   AND pa.agencia_pagadora = b.agencia_pagadora
GROUP BY b.cedente_documento, b.banco_pagador, b.agencia_pagadora
""")

# Contas cadastradas: (banco, agencia, cidade) por raiz de documento.
_SQL_CONTAS = text("""
SELECT entidade_documento, banco_codigo, agencia_codigo,
       agencia_localidade, agencia_estado
FROM wh_conta_bancaria
WHERE tenant_id = :tenant_id AND entidade_documento IS NOT NULL
""")

# Cidades cadastrais por documento (cedentes + sacados + grupo por raiz).
_SQL_CIDADES = text("""
SELECT documento, localidade, estado
FROM wh_entidade
WHERE tenant_id = :tenant_id AND documento IS NOT NULL
  AND localidade IS NOT NULL
""")

# Baseline de ticket por cedente (media/desvio do valor de titulo).
_SQL_TICKET = text("""
SELECT o.cedente_documento,
       avg(t.valor)                AS media,
       coalesce(stddev(t.valor),0) AS desvio
FROM wh_titulo t
JOIN wh_operacao o
    ON o.operacao_id = t.operacao_id AND o.tenant_id = t.tenant_id
WHERE t.tenant_id = :tenant_id AND t.valor > 0
GROUP BY o.cedente_documento
""")

# Lote: liquidacoes do mesmo cedente no mesmo dia.
_SQL_LOTE = text("""
SELECT o.cedente_documento, l.data_evento::date AS dia, count(*) AS n
FROM wh_liquidacao l
JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
WHERE l.tenant_id = :tenant_id
  AND l.canal IN ('bancaria', 'baixa_manual')
GROUP BY o.cedente_documento, l.data_evento::date
""")


def _zfill_banco(b: str | None) -> str | None:
    b = (b or "").strip()
    return b.zfill(3) if b.isdigit() and int(b) > 0 else None


def _zfill_agencia(a: str | None) -> str | None:
    a = (a or "").strip()
    return a.zfill(5) if a.isdigit() and int(a) > 0 else None


async def montar_features(db: AsyncSession, tenant_id: UUID) -> list[FeatureRow]:
    """Build the full feature set for every scorable liquidation event."""
    resolver = await RefBacenResolver.carregar(db)

    eventos = (await db.execute(_SQL_EVENTOS, {"tenant_id": tenant_id})).mappings().all()

    # --- auxiliary lookups (one pass each, all in memory) -------------------
    fingerprint: dict[str, dict[str, int]] = {}
    for r in (await db.execute(_SQL_FINGERPRINT, {"tenant_id": tenant_id})).mappings():
        fingerprint.setdefault(r["sacado_documento"], {})[
            _zfill_banco(r["banco_pagador"]) or "?"
        ] = int(r["n"])

    # (cedente, banco, agencia) -> nº sacados do cedente naquela agencia
    compartilhada: dict[tuple[str, str, str], int] = {}
    # (banco, agencia) -> nº de cedentes distintos na agencia (rede)
    compart_cedentes: dict[tuple[str, str], int] = {}
    for r in (await db.execute(_SQL_AGENCIA_COMPARTILHADA, {"tenant_id": tenant_id})).mappings():
        b = _zfill_banco(r["banco_pagador"])
        a = _zfill_agencia(r["agencia_pagadora"])
        ced = _doc(r["cedente_documento"])
        if b and a and ced:
            compartilhada[(ced, b, a)] = int(r["n_sacados"])
            compart_cedentes[(b, a)] = int(r["n_cedentes"])

    contas_por_raiz: dict[str, set[tuple[str, str]]] = {}
    cidades_conta_por_raiz: dict[str, set[tuple[str | None, str | None]]] = {}
    for r in (await db.execute(_SQL_CONTAS, {"tenant_id": tenant_id})).mappings():
        raiz = _raiz(r["entidade_documento"])
        b = _zfill_banco(r["banco_codigo"])
        a = _zfill_agencia(r["agencia_codigo"])
        if raiz and b and a:
            contas_por_raiz.setdefault(raiz, set()).add((b, a))
        if raiz and r["agencia_localidade"]:
            cidades_conta_por_raiz.setdefault(raiz, set()).add(
                (_norm_cidade(r["agencia_localidade"]), (r["agencia_estado"] or "").strip() or None)
            )

    cidade_por_doc: dict[str, tuple[str | None, str | None]] = {}
    cidades_por_raiz: dict[str, set[tuple[str | None, str | None]]] = {}
    for r in (await db.execute(_SQL_CIDADES, {"tenant_id": tenant_id})).mappings():
        cid = (_norm_cidade(r["localidade"]), (r["estado"] or "").strip() or None)
        doc = _doc(r["documento"])
        if doc:
            cidade_por_doc[doc] = cid
        raiz = _raiz(r["documento"])
        if raiz:
            cidades_por_raiz.setdefault(raiz, set()).add(cid)

    ticket: dict[str, tuple[float, float]] = {
        _doc(r["cedente_documento"]): (float(r["media"]), float(r["desvio"]))
        for r in (await db.execute(_SQL_TICKET, {"tenant_id": tenant_id})).mappings()
        if _doc(r["cedente_documento"])
    }

    lote: dict[tuple[str, Any], int] = {
        (_doc(r["cedente_documento"]), r["dia"]): int(r["n"])
        for r in (await db.execute(_SQL_LOTE, {"tenant_id": tenant_id})).mappings()
        if _doc(r["cedente_documento"])
    }

    # Bancos digitais (segmento oficial banco SEM rede fisica) — chave Compe.
    # Descritor de canal por segmento p/ o painel deterministico; NAO e feature
    # do modelo (chave extra no vetor, ignorada por FEATURE_NAMES).
    digital: set[str] = {
        row[0]
        for row in (
            await db.execute(
                text(
                    "SELECT codigo_compe FROM ref_bacen_instituicao "
                    "WHERE is_banco_digital IS TRUE"
                )
            )
        ).all()
    }

    # --- per-event assembly -------------------------------------------------
    rows: list[FeatureRow] = []
    for ev in eventos:
        canal_evento: str = ev["canal"]
        evidencia: str | None = ev["evidencia"]
        cedente_doc = _doc(ev["cedente_documento"])
        raiz_ced = _raiz(cedente_doc)
        banco = _zfill_banco(ev["banco_pagador"])
        agencia = _zfill_agencia(ev["agencia_pagadora"])
        sacado_doc = _doc(ev["sacado_documento"])

        praca = resolver.resolver(banco, agencia)
        cidade_pgto = (_norm_cidade(praca.municipio), praca.uf) if praca.praca_resolvida else None
        cidade_sacado = cidade_por_doc.get(sacado_doc) if sacado_doc else None
        cidades_cedente = cidades_por_raiz.get(raiz_ced, set()) if raiz_ced else set()
        cidades_cedente = cidades_cedente | (
            cidades_conta_por_raiz.get(raiz_ced, set()) if raiz_ced else set()
        )

        contas_ced = contas_por_raiz.get(raiz_ced, set()) if raiz_ced else set()
        match_conta = bool(banco and agencia and (banco, agencia) in contas_ced)

        # Fingerprint do sacado (so pontua com historico e habito estavel).
        quebra = 0.0
        if sacado_doc and banco:
            hist = fingerprint.get(sacado_doc, {})
            total = sum(hist.values())
            if total >= _FINGERPRINT_MIN_EVENTOS:
                dominante = max(hist.values()) / total
                if dominante >= _FINGERPRINT_MIN_ESTABILIDADE:
                    quebra = 1.0 - (hist.get(banco, 0) / total)

        # S2 (excluindo gateways declarados): sacados do cedente na agencia +
        # cedentes distintos na agencia (rede — operador comum).
        n_compart = 0
        n_compart_ced = 0
        is_gateway = bool(banco and agencia and (banco, agencia) in _EXCLUSOES_AGENCIA_GATEWAY)
        if cedente_doc and banco and agencia and not is_gateway:
            n_compart = compartilhada.get((cedente_doc, banco, agencia), 0)
            n_compart_ced = compart_cedentes.get((banco, agencia), 0)

        contrato_boleto = ev["contrato_boleto"]  # OBRIGATORIO|PERMITIDO|NAO_ESPERADO|None
        contrato_baixa = ev["contrato_baixa_manual"]  # NORMAL|ANOMALA|None

        vencimento = ev["data_de_vencimento_efetiva"] or ev["data_de_vencimento"]
        pago_exato = bool(
            vencimento is not None
            and ev["data_evento"] is not None
            and ev["data_evento"].date() == vencimento.date()
        )

        valor = float(ev["valor_pago"] or ev["valor_titulo"] or 0.0)
        media, desvio = ticket.get(cedente_doc, (0.0, 0.0)) if cedente_doc else (0.0, 0.0)
        ticket_z = 0.0
        if desvio > 0 and valor > 0:
            ticket_z = max(-5.0, min(5.0, (valor - media) / desvio))

        n_lote = (
            lote.get((cedente_doc, ev["data_evento"].date()), 1)
            if cedente_doc and ev["data_evento"] is not None
            else 1
        )

        teve_trilho_bancario = canal_evento == "bancaria" or evidencia == "baixa_confirmada"

        f: dict[str, float] = {
            "match_agencia_conta_cedente": 1.0 if match_conta else 0.0,
            "cidade_pgto_eq_cedente": (
                1.0 if cidade_pgto and cidade_pgto in cidades_cedente else 0.0
            ),
            "cidade_pgto_neq_sacado": (
                1.0 if cidade_pgto and cidade_sacado and cidade_pgto != cidade_sacado else 0.0
            ),
            # praca_fonte (escada): de onde veio a resolucao da praca.
            "praca_fonte_bacen": 1.0 if praca.praca_fonte == "bacen" else 0.0,
            "praca_fonte_cadastro_erp": 1.0 if praca.praca_fonte == "cadastro_erp" else 0.0,
            "praca_nao_resolvida": (
                1.0 if banco is not None and not praca.praca_resolvida else 0.0
            ),
            "canal_cooperativa": 1.0 if praca.canal == CANAL_COOPERATIVA else 0.0,
            "canal_ip": 1.0 if praca.canal == CANAL_IP else 0.0,
            "canal_sem_praca": (
                1.0
                if banco is not None
                and praca.canal
                not in (CANAL_BANCO_PRACA, CANAL_COOPERATIVA, CANAL_IP, CANAL_NAO_RESOLVIDO)
                else 0.0
            ),
            "canal_nao_resolvido": (
                1.0 if banco is not None and praca.canal == CANAL_NAO_RESOLVIDO else 0.0
            ),
            "quebra_fingerprint": round(quebra, 4),
            "agencia_compartilhada": round(math.log1p(max(0, n_compart - 1)), 4),
            "agencia_compartilhada_cedentes": round(math.log1p(max(0, n_compart_ced - 1)), 4),
            "canal_baixa_manual": 1.0 if canal_evento == "baixa_manual" else 0.0,
            "baixa_confirmada": 1.0 if evidencia == "baixa_confirmada" else 0.0,
            "sem_ocorrencia": 1.0 if evidencia == "sem_ocorrencia" else 0.0,
            "baixa_manual_produto_anomala": (
                1.0 if canal_evento == "baixa_manual" and contrato_baixa == "ANOMALA" else 0.0
            ),
            "boleto_nao_esperado_mas_teve": (
                1.0 if contrato_boleto == "NAO_ESPERADO" and teve_trilho_bancario else 0.0
            ),
            "contrato_aberto": 1.0 if contrato_boleto is None else 0.0,
            "pago_exato_vencimento": 1.0 if pago_exato else 0.0,
            "lote_dia": round(math.log1p(max(0, n_lote - 1)), 4),
            "ticket_z": round(ticket_z, 4),
            "valor_log": round(math.log1p(valor), 4),
        }

        # --- descritores de segmento da instituicao pagadora ----------------
        # Chaves EXTRA (fora de FEATURE_NAMES): alimentam o painel
        # deterministico de padroes de liquidacao (canal por segmento oficial
        # Bacen), ignoradas pelo modelo (score le so FEATURE_NAMES).
        seg = praca.segmento
        f["seg_banco_digital"] = (
            1.0 if seg == SEGMENTO_BANCO and (praca.banco_compe in digital) else 0.0
        )
        f["seg_cooperativa"] = (
            1.0 if seg in (SEGMENTO_COOPERATIVA, SEGMENTO_BANCO_COOPERATIVO) else 0.0
        )
        f["seg_ip"] = 1.0 if seg == SEGMENTO_IP else 0.0
        f["seg_scd"] = 1.0 if seg == SEGMENTO_SCD else 0.0
        f["seg_financeira"] = 1.0 if seg == SEGMENTO_FINANCEIRA else 0.0

        # --- regra dura (deterministica, fora do modelo) --------------------
        # Praca resolvida SO por fonte propria (escada Bacen->ERP); trilho B
        # (bit do ERP) nao entra mais na regra.
        regra = False
        motivo = None
        if (
            praca.praca_resolvida
            and cidade_sacado
            and cidade_pgto
            and cidade_pgto != cidade_sacado
            and match_conta
        ):
            regra = True
            motivo = (
                "sacado de outra cidade pagou na agencia do cedente "
                f"(banco {banco} ag {agencia}, {praca.municipio}/{praca.uf})"
            )
        # Regra nova (pos-escada): agencia FISICA compartilhada por >=10
        # sacados de cidades divergentes da cidade da agencia, nao-gateway —
        # concentracao regional nao explica; e operador comum.
        elif (
            praca.praca_resolvida
            and not is_gateway
            and n_compart >= 10
            and cidade_sacado
            and cidade_pgto
            and cidade_pgto != cidade_sacado
        ):
            regra = True
            motivo = (
                f"agencia compartilhada por {n_compart} sacados de outras "
                f"cidades (banco {banco} ag {agencia}, {praca.municipio}/{praca.uf})"
            )

        rows.append(
            FeatureRow(
                liquidacao_id=ev["liquidacao_id"],
                titulo_id=ev["titulo_id"],
                cedente_documento=cedente_doc,
                cedente_nome=ev["cedente_nome"],
                produto_sigla=ev["produto_sigla"],
                sacado_documento=sacado_doc,
                data_evento=ev["data_evento"],
                valor=valor or None,
                canal=canal_evento,
                evidencia=evidencia,
                features=f,
                regra_dura=regra,
                regra_dura_motivo=motivo,
            )
        )

    logger.info(
        "deteccao_features: %d eventos, %d com regra dura",
        len(rows),
        sum(1 for r in rows if r.regra_dura),
    )
    return rows

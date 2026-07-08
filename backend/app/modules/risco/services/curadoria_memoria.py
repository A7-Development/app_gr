"""Memoria de calculo de UMA liquidacao — evidencia completa para o curador.

"Como o sistema chegou no sinal": para cada conclusao exibida na tela, este
service reune os DADOS que a sustentam — praca do pagamento resolvida
(Bacen), contas cadastradas do cedente (e qual deu match), cidades
comparadas, fingerprint bancario do sacado (historico por banco), contrato
ativo do produto, timing (vencimento vs pagamento, lote do dia). O curador
decide com os insumos, nao com um badge (feedback Ricardo 2026-07-08).

Output = secoes genericas {titulo, itens[{label, valor, destaque}]} — o
frontend renderiza sem conhecer a semantica; sinais novos ganham secao sem
mudar a tela.

Queries sao PONTUAIS ao evento (escopadas por titulo/sacado/cedente) — nao
reusa o feature builder global, que varre a carteira inteira.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.public import RefBacenResolver
from app.modules.risco.services.deteccao_features import (
    _doc,
    _norm_cidade,
    _raiz,
    _zfill_agencia,
    _zfill_banco,
)

_SQL_EVENTO = text("""
SELECT
    l.id AS liquidacao_id, l.titulo_id, l.canal, l.evidencia, l.data_evento,
    l.data_credito, l.valor_pago, l.valor_titulo, l.situacao_titulo,
    l.local_pagamento, l.pago_fora_praca_sacado, l.pago_na_praca_cliente,
    l.pago_na_agencia_cliente, l.pago_na_agencia_sacado,
    l.pago_em_banco_digital, l.registrado, l.meio_codigo,
    t.numero AS titulo_numero, t.status AS titulo_status,
    t.data_de_emissao, t.data_de_vencimento, t.data_de_vencimento_efetiva,
    t.valor AS valor_face,
    o.cedente_nome, o.cedente_documento, o.modalidade,
    split_part(o.modalidade, '-', 1) AS produto_sigla,
    dp.nome AS produto_nome,
    bv.sacado_nome, bv.sacado_documento,
    ev.banco_pagador, ev.agencia_pagadora,
    ds.score, ds.fatores, ds.regra_dura, ds.regra_dura_motivo
FROM wh_liquidacao l
JOIN wh_titulo t ON t.titulo_id = l.titulo_id AND t.tenant_id = l.tenant_id
LEFT JOIN wh_operacao o
    ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
LEFT JOIN wh_dim_produto dp
    ON dp.tenant_id = l.tenant_id AND dp.sigla = split_part(o.modalidade, '-', 1)
LEFT JOIN LATERAL (
    SELECT b.sacado_nome, b.sacado_documento, b.banco_origem, b.nosso_numero
    FROM wh_boleto_vigente b
    WHERE b.tenant_id = l.tenant_id AND b.numero_documento = t.numero
    LIMIT 1
) bv ON true
LEFT JOIN LATERAL (
    SELECT be.banco_pagador, be.agencia_pagadora
    FROM wh_boleto_evento be
    WHERE be.tenant_id = l.tenant_id
      AND be.banco_origem = bv.banco_origem
      AND be.nosso_numero = bv.nosso_numero
      AND be.banco_pagador IS NOT NULL
    ORDER BY be.data_ocorrencia DESC
    LIMIT 1
) ev ON true
LEFT JOIN deteccao_score ds
    ON ds.tenant_id = l.tenant_id AND ds.liquidacao_id = l.id
WHERE l.tenant_id = :tenant_id AND l.id = :liquidacao_id
""")

_SQL_CIDADE = text("""
SELECT documento, localidade, estado FROM wh_entidade
WHERE tenant_id = :tenant_id AND documento = ANY(:docs)
""")

_SQL_CONTAS_CEDENTE = text("""
SELECT banco_codigo, banco_nome, agencia_codigo, agencia_localidade,
       agencia_estado, ativa
FROM wh_conta_bancaria
WHERE tenant_id = :tenant_id
  AND entidade_documento LIKE :raiz || '%'
ORDER BY banco_codigo, agencia_codigo
""")

_SQL_FINGERPRINT_SACADO = text("""
SELECT be.banco_pagador, count(*) AS n
FROM wh_boleto_evento be
JOIN wh_boleto_vigente bv
    ON bv.tenant_id = be.tenant_id
   AND bv.banco_origem = be.banco_origem
   AND bv.nosso_numero = be.nosso_numero
WHERE be.tenant_id = :tenant_id
  AND bv.sacado_documento = :sacado_documento
  AND be.banco_pagador IS NOT NULL
  AND be.valor_pago > 0
GROUP BY be.banco_pagador
ORDER BY n DESC
""")

_SQL_USO_AGENCIA = text("""
SELECT count(DISTINCT bv.sacado_documento) AS n_sacados,
       count(DISTINCT o.cedente_documento) AS n_cedentes,
       count(*) AS n_pagamentos
FROM wh_boleto_evento be
JOIN wh_boleto_vigente bv
    ON bv.tenant_id = be.tenant_id
   AND bv.banco_origem = be.banco_origem
   AND bv.nosso_numero = be.nosso_numero
JOIN wh_titulo t ON t.tenant_id = be.tenant_id AND t.numero = bv.numero_documento
JOIN wh_operacao o
    ON o.operacao_id = t.operacao_id AND o.tenant_id = t.tenant_id
WHERE be.tenant_id = :tenant_id
  AND lpad(be.banco_pagador, 3, '0') = :banco
  AND lpad(be.agencia_pagadora, 5, '0') = lpad(:agencia_raw, 5, '0')
  AND be.valor_pago > 0
  AND be.data_ocorrencia >= now() - interval '365 days'
""")

_SQL_CONTRATO = text("""
SELECT fluxo_esperado, boleto, baixa_manual, version
FROM produto_contrato_liquidacao
WHERE tenant_id = :tenant_id AND produto_sigla = :sigla
ORDER BY version DESC LIMIT 1
""")

_SQL_LOTE_DIA = text("""
SELECT count(*) AS n
FROM wh_liquidacao l
JOIN wh_operacao o ON o.operacao_id = l.operacao_id AND o.tenant_id = l.tenant_id
WHERE l.tenant_id = :tenant_id
  AND o.cedente_documento = :cedente_documento
  AND l.data_evento::date = :dia
  AND l.canal IN ('bancaria', 'baixa_manual')
""")

_CANAL_LABEL = {
    "banco_praca": "banco com praça física",
    "cooperativa": "cooperativa de crédito (sem praça pública)",
    "ip": "instituição de pagamento (conta eletrônica)",
    "outras_if": "outra instituição financeira",
    "nao_resolvido": "não resolvido na referência Bacen",
}


def _label_canal(praca: Any) -> str:
    """Human label of the channel — banco_sem_praca is NOT one thing.

    The resolver bucket `banco_sem_praca` mixes (a) genuine electronic
    settlement at the agencia-matriz 0001 and (b) a real branch the current
    Bacen snapshot does not list (internal numbering or EXTINCT agency —
    known F2 gotcha, e.g. Bradesco 1417/RJ). Calling (b) "sem praça física"
    misled the curator (feedback Ricardo 2026-07-08) — the truth is "praça
    não identificada", possibly a physical branch.
    """
    if praca.canal != "banco_sem_praca":
        return _CANAL_LABEL.get(praca.canal, praca.canal)
    if "matriz" in (praca.detalhe or ""):
        return "liquidação eletrônica (agência-matriz 0001 — cidade não é praça)"
    return (
        "banco — praça não identificada (agência fora da referência Bacen; "
        "pode ser física extinta ou renumerada)"
    )

_SITUACAO_LABEL = {
    0: "Em aberto",
    1: "Liquidação Normal",
    2: "Liquidação em Cartório",
    3: "Baixado",
    5: "Recomprado",
    7: "Recuperação de Crédito",
    9: "Perda",
}


def _item(label: str, valor: Any, *, destaque: bool = False) -> dict[str, Any]:
    return {"label": label, "valor": valor, "destaque": destaque}


def _fmt_brl(v: Any) -> str:
    if v is None:
        return "—"
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def montar_memoria(
    db: AsyncSession, tenant_id: UUID, liquidacao_id: UUID
) -> dict[str, Any] | None:
    """Full calculation trail of one liquidation (None = not this tenant's)."""
    ev = (
        (await db.execute(_SQL_EVENTO, {"tenant_id": tenant_id, "liquidacao_id": liquidacao_id}))
        .mappings()
        .first()
    )
    if ev is None:
        return None

    resolver = await RefBacenResolver.carregar(db)
    banco = _zfill_banco(ev["banco_pagador"])
    agencia = _zfill_agencia(ev["agencia_pagadora"])
    praca = resolver.resolver(banco, agencia)

    cedente_doc = _doc(ev["cedente_documento"])
    sacado_doc = _doc(ev["sacado_documento"])
    raiz = _raiz(cedente_doc)

    docs = [d for d in (cedente_doc, sacado_doc) if d]
    cidades = {
        r["documento"]: (r["localidade"], r["estado"])
        for r in (
            await db.execute(_SQL_CIDADE, {"tenant_id": tenant_id, "docs": docs})
        ).mappings()
    }
    cidade_cedente = cidades.get(cedente_doc)
    cidade_sacado = cidades.get(sacado_doc)

    contas = (
        (
            await db.execute(
                _SQL_CONTAS_CEDENTE, {"tenant_id": tenant_id, "raiz": raiz or ""}
            )
        )
        .mappings()
        .all()
    )
    conta_match = next(
        (
            c
            for c in contas
            if banco
            and agencia
            and _zfill_banco(c["banco_codigo"]) == banco
            and _zfill_agencia(c["agencia_codigo"]) == agencia
        ),
        None,
    )

    fingerprint = (
        (
            await db.execute(
                _SQL_FINGERPRINT_SACADO,
                {"tenant_id": tenant_id, "sacado_documento": ev["sacado_documento"]},
            )
        )
        .mappings()
        .all()
        if ev["sacado_documento"]
        else []
    )
    fp_total = sum(int(r["n"]) for r in fingerprint)

    contrato = (
        (
            await db.execute(
                _SQL_CONTRATO, {"tenant_id": tenant_id, "sigla": ev["produto_sigla"]}
            )
        )
        .mappings()
        .first()
        if ev["produto_sigla"]
        else None
    )

    lote = (
        await db.execute(
            _SQL_LOTE_DIA,
            {
                "tenant_id": tenant_id,
                "cedente_documento": ev["cedente_documento"],
                "dia": ev["data_evento"].date() if ev["data_evento"] else None,
            },
        )
    ).scalar_one_or_none() if ev["cedente_documento"] and ev["data_evento"] else None

    # ── secoes da memoria ───────────────────────────────────────────────────
    secoes: list[dict[str, Any]] = []

    vencimento = ev["data_de_vencimento_efetiva"] or ev["data_de_vencimento"]
    dias_vs_venc = (
        (ev["data_evento"].date() - vencimento.date()).days
        if ev["data_evento"] and vencimento
        else None
    )
    secoes.append(
        {
            "titulo": "O título",
            "itens": [
                _item("Documento", ev["titulo_numero"] or str(ev["titulo_id"])),
                _item("Valor de face", _fmt_brl(ev["valor_face"])),
                _item(
                    "Emissão",
                    ev["data_de_emissao"].strftime("%d/%m/%Y") if ev["data_de_emissao"] else "—",
                ),
                _item(
                    "Vencimento",
                    vencimento.strftime("%d/%m/%Y") if vencimento else "—",
                ),
                _item(
                    "Situação atual",
                    _SITUACAO_LABEL.get(ev["situacao_titulo"], str(ev["situacao_titulo"])),
                    destaque=ev["situacao_titulo"] in (3, 9),
                ),
            ],
        }
    )

    itens_liq = [
        _item(
            "Mecânica",
            "bancária (retorno do banco)" if ev["canal"] == "bancaria" else "baixa manual",
        ),
        _item("Valor pago", _fmt_brl(ev["valor_pago"])),
        _item(
            "Data do evento",
            ev["data_evento"].strftime("%d/%m/%Y") if ev["data_evento"] else "—",
        ),
        _item(
            "Dias vs vencimento",
            "no vencimento exato"
            if dias_vs_venc == 0
            else (f"{dias_vs_venc:+d} dias" if dias_vs_venc is not None else "—"),
            destaque=dias_vs_venc == 0,
        ),
    ]
    if ev["evidencia"]:
        rotulo = {
            "baixa_confirmada": "boleto baixado por INSTRUÇÃO no banco e título liquidado por fora",
            "sem_registro": "título nunca entrou no trilho bancário (depósito direto plausível)",
            "sem_ocorrencia": "boleto registrado mas sem ocorrência de liquidação (cobertura ou baixa silenciosa)",
        }.get(ev["evidencia"], ev["evidencia"])
        itens_liq.append(_item("Evidência da baixa", rotulo, destaque=ev["evidencia"] == "baixa_confirmada"))
    if lote and lote > 1:
        itens_liq.append(
            _item(
                "Lote do dia",
                f"{lote} liquidações do mesmo cedente neste dia",
                destaque=lote >= 10,
            )
        )
    secoes.append({"titulo": "A liquidação", "itens": itens_liq})

    if banco:
        fonte_label = {
            "bacen": "referência Bacen",
            "cadastro_erp": "cadastro do ERP (agência fora da referência Bacen)",
        }.get(praca.praca_fonte, "não resolvida")
        itens_praca = [
            _item("Banco pagador", f"{banco} — {praca.instituicao or 'não identificado'}"),
            _item("Agência", agencia or "—"),
            _item("Canal", _label_canal(praca)),
            _item(
                "Praça do pagamento",
                f"{praca.municipio}/{praca.uf} (fonte: {fonte_label})"
                if praca.praca_resolvida
                else f"não resolvida ({praca.detalhe})",
                destaque=praca.praca_fonte == "cadastro_erp",
            ),
        ]
        # Trilho B (bits de praca do ERP) REMOVIDO da memoria (2026-07-08):
        # a praca agora vem SO da resolucao propria (escada Bacen->cadastro ERP).
        secoes.append({"titulo": "Onde foi pago", "itens": itens_praca})

        # Uso desta agencia (S2): quantos sacados e cedentes distintos usam
        # este mesmo (banco, agencia) — a coincidencia que interessa.
        if agencia:
            uso = (
                await db.execute(
                    _SQL_USO_AGENCIA,
                    {
                        "tenant_id": tenant_id,
                        "banco": banco,
                        "agencia_raw": ev["agencia_pagadora"],
                    },
                )
            ).mappings().first()
            if uso and int(uso["n_sacados"] or 0) > 1:
                secoes.append(
                    {
                        "titulo": "Uso desta agência (12 meses)",
                        "itens": [
                            _item(
                                "Sacados distintos aqui",
                                str(uso["n_sacados"]),
                                destaque=int(uso["n_sacados"]) >= 5,
                            ),
                            _item(
                                "Cedentes distintos aqui",
                                str(uso["n_cedentes"]),
                                destaque=int(uso["n_cedentes"]) >= 3,
                            ),
                            _item("Pagamentos", str(uso["n_pagamentos"])),
                        ],
                    }
                )

    itens_partes = [
        _item(
            "Cedente",
            f"{ev['cedente_nome'] or '—'}"
            + (f" — {cidade_cedente[0]}/{cidade_cedente[1]}" if cidade_cedente else ""),
        ),
        _item(
            "Sacado",
            f"{ev['sacado_nome'] or '—'}"
            + (f" — {cidade_sacado[0]}/{cidade_sacado[1]}" if cidade_sacado else ""),
        ),
    ]
    if praca.praca_resolvida and cidade_sacado:
        mesma = _norm_cidade(praca.municipio) == _norm_cidade(cidade_sacado[0])
        itens_partes.append(
            _item(
                "Cidade do pagamento vs sacado",
                "mesma cidade" if mesma else f"DIVERGE — pagamento em {praca.municipio}/{praca.uf}, sacado em {cidade_sacado[0]}/{cidade_sacado[1]}",
                destaque=not mesma,
            )
        )
    secoes.append({"titulo": "As partes", "itens": itens_partes})

    if contas:
        itens_contas = [
            _item(
                f"{_zfill_banco(c['banco_codigo']) or '—'} ag {c['agencia_codigo'] or '—'}",
                f"{c['banco_nome'] or ''}"
                + (f" — {c['agencia_localidade']}/{c['agencia_estado']}" if c["agencia_localidade"] else "")
                + (" · MATCH com o pagamento" if conta_match is c else ""),
                destaque=conta_match is c,
            )
            for c in contas
        ]
        secoes.append(
            {
                "titulo": f"Contas cadastradas do cedente ({len(contas)})",
                "itens": itens_contas,
            }
        )

    if fingerprint:
        dominante = fingerprint[0]
        share = int(dominante["n"]) / fp_total if fp_total else 0
        itens_fp = [
            _item(
                "Histórico do sacado",
                f"{fp_total} pagamentos com praça identificada",
            ),
            _item(
                "Banco habitual",
                f"{_zfill_banco(dominante['banco_pagador'])} ({share:.0%} dos pagamentos)",
            ),
        ]
        if banco:
            usa_banco = next(
                (int(r["n"]) for r in fingerprint if _zfill_banco(r["banco_pagador"]) == banco),
                0,
            )
            quebrou = fp_total >= 3 and share >= 0.8 and usa_banco == 0
            itens_fp.append(
                _item(
                    "Este pagamento",
                    f"banco {banco}"
                    + (
                        " — QUEBRA o padrão do sacado"
                        if quebrou
                        else f" ({usa_banco} pagamentos anteriores neste banco)"
                    ),
                    destaque=quebrou,
                )
            )
        secoes.append({"titulo": "Padrão bancário do sacado", "itens": itens_fp})

    if contrato:
        secoes.append(
            {
                "titulo": f"Contrato do produto ({ev['produto_nome'] or ev['produto_sigla']}, v{contrato['version']})",
                "itens": [
                    _item("Fluxo esperado", str(contrato["fluxo_esperado"]).replace("_", " ").lower()),
                    _item("Boleto", str(contrato["boleto"]).replace("_", " ").lower()),
                    _item(
                        "Baixa manual",
                        str(contrato["baixa_manual"]).lower(),
                        destaque=str(contrato["baixa_manual"]) == "ANOMALA"
                        and ev["canal"] == "baixa_manual",
                    ),
                ],
            }
        )
    elif ev["produto_sigla"]:
        secoes.append(
            {
                "titulo": f"Contrato do produto ({ev['produto_nome'] or ev['produto_sigla']})",
                "itens": [_item("Contrato", "em aberto — produto sem declaração")],
            }
        )

    if ev["titulo_status"] == 3:
        secoes.append(
            {
                "titulo": "Verificação de lastro",
                "itens": [
                    _item(
                        "Status na esteira de confirmação",
                        "LASTRO INCONSISTENTE — nota cancelada na SEFAZ ou sacado recusou a nota",
                        destaque=True,
                    )
                ],
            }
        )

    return {
        "liquidacao_id": str(ev["liquidacao_id"]),
        "titulo_numero": ev["titulo_numero"],
        "cedente_nome": ev["cedente_nome"],
        "regra_dura": bool(ev["regra_dura"]),
        "regra_dura_motivo": ev["regra_dura_motivo"],
        "score": float(ev["score"]) if ev["score"] is not None else None,
        "fatores": ev["fatores"],
        "secoes": secoes,
    }

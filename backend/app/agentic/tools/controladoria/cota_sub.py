"""Tools agenticas pra analise da variacao da Cota Sub Jr.

10 tools registradas. A 10a (get_conferencia_cessao, 2026-05-30) confere as
AQUISICOES de recebiveis do dia contra os DEBITOS de caixa aos cedentes no
extrato bancario (reconciliacao DC<->caixa: erro de lancamento / furo de sync
do extrato / fluxo extra ao cedente). As demais: 5 wrappers de drills/balanco +
get_decomposicao_classes (ΔPL por classe: capital vs valorizacao) + 3 de
investigacao de papel.

**Convencao de scope:**

- `ua_id` (UUID do FIDC) e `data_d0` (ISO date) vivem em `scope.extras`
  — preenchidos pelo invocador da analise, NAO escolhidos pelo LLM.
  Razao: o controller seleciona o fundo + dia na UI; agente nao decide.
- `seu_numero`, `cedente_doc`, `sacado_doc` sao decisao do LLM —
  passados via `args`. O agente investiga papeis especificos ao
  decompor a variacao.

**Output:** todas retornam JSON string compacto (Decimal/date serializados
via `default=str`). Schema do JSON e descrito na docstring da tool — o
LLM le e usa.

Registradas com `module=CONTROLADORIA, min_permission=READ,
cacheable=True` (read-only de snapshot historico, idempotente
dentro da janela de uma analise).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agentic._scope import ScopedContext
from app.agentic.tools._base import register_tool
from app.core.enums import Module, Permission

# ─── Helpers ──────────────────────────────────────────────────────────────


def _to_json(obj: Any) -> str:
    """Serializa estrutura com Decimal/date/datetime/UUID → JSON string."""

    def default(o: Any) -> Any:
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, ensure_ascii=False, default=default)


def _parse_scope_inputs(scope: ScopedContext) -> tuple[UUID, date]:
    """Extrai (ua_id, data_d0) do scope.extras com validacao."""
    ua_id_raw = scope.extras.get("ua_id")
    data_raw = scope.extras.get("data_d0")
    if ua_id_raw is None or data_raw is None:
        raise ValueError(
            "Tool requer 'ua_id' e 'data_d0' em scope.extras. "
            "Invocador (orquestrador do agente) deve preencher antes."
        )
    ua_id = UUID(str(ua_id_raw)) if not isinstance(ua_id_raw, UUID) else ua_id_raw
    if isinstance(data_raw, str):
        data_d0 = date.fromisoformat(data_raw)
    elif isinstance(data_raw, datetime):
        data_d0 = data_raw.date()
    elif isinstance(data_raw, date):
        data_d0 = data_raw
    else:
        raise ValueError(f"data_d0 invalido: {data_raw!r}")
    return ua_id, data_d0


# ─── Tools 1-4: wrappers diretos dos services F1+F2 ──────────────────────


@register_tool(
    name="get_balanco_patrimonial",
    description=(
        "Retorna o balanço patrimonial ESTRUTURAL do FIDC otica Sub Jr para a "
        "data analisada (D0) vs dia util anterior (D-1) — MESMA estrutura da tela, "
        "coerente por natureza e sinal. Devolve `ativos` e `passivos` (cada linha "
        "com key/label/natureza/d1/d0/delta), na ORDEM FIXA do balancete:\n"
        "  Ativos: Direitos Creditorios, (-)PDD (natureza=contra_ativo, ABATE o "
        "DC), Titulos Publicos, Op. Estruturadas, Fundos DI, Compromissada, Outros "
        "Ativos, Tesouraria, Saldo Conta Corrente, Contas a Receber.\n"
        "  Passivos: Contas a Pagar, Cota Senior, Cota Mezanino.\n"
        "Contas a Receber = CPR de natureza ATIVA (liquidacoes em floating + "
        "diferimentos); Contas a Pagar = CPR de natureza PASSIVA (despesas/taxas/"
        "IOF a recolher). Inclui dc_liquido (DC bruto - PDD), total_ativo, "
        "total_passivo, pl_sub (= total_ativo - total_passivo) e bloco "
        "`reconciliacao` (pl_fonte MEC + residuo). Use SEMPRE no inicio da analise."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_balanco_patrimonial(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_balanco_estrutural. ua_id+data vem do scope.

    Migrado 2026-05-27 (follow-up B): passou a ler o balanco ESTRUTURAL pra
    falar a mesma lingua da tela (PDD contra-ativo, Contas a Receber/Pagar,
    Cotas Prioritarias). O nome da tool segue `get_balanco_patrimonial` por
    compat ate o cleanup do balanco antigo (entao vira get_balanco_estrutural).
    """
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_balanco_estrutural,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_balanco_estrutural(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_variacao_carteira",
    description=(
        "Decompoe a variacao da carteira de recebiveis (linha Direitos "
        "Creditorios) entre D-1 e D0 em 5 buckets a partir do granular "
        "wh_estoque_recebivel: aquisicoes (papeis novos), liquidacoes "
        "(papeis baixados pelo VP), migracao WOP (papeis que viraram "
        "write-off), apropriacao de juros (populacao constante sem mudanca "
        "de parametro), mutacao (papeis que mudaram valor_nominal/taxa/"
        "vencimento). Identidade fecha por construcao (residuo ~ R$ 0).\n\n"
        "JA VEM PRONTO o bloco `resultado_do_dia` com os MOTORES DE RENDA da "
        "DC e SINAL DE IMPACTO no PL Sub corrigido (voce NAO precisa flipar o "
        "ajuste): carrego_apropriacao, apropriacao_antecipada (= -Σajuste<0 de "
        "quitacoes ANTES do vencimento; carrego futuro ja contratado trazido pra "
        "frente, NAO e receita extra), juros_mora (= -Σajuste<0 de pagamentos em "
        "ATRASO; renda extra), desconto_concedido (>=0, custo), "
        "ajuste_liquido_resultado, mutacao_total, migracao_wop_total, "
        "giro_aquisicoes/giro_liquidacoes "
        "(NAO movem a cota), motor_dominante e resultado_outlier. Em cada "
        "liquidacao (por_tipo e top) use `impacto_resultado_brl` (= -ajuste) "
        "como delta_brl do papel — NUNCA `ganho_liquido`. O bloco `sugestao` "
        "traz classificacao_sugerida + alerta_sugerido (EVIDENCIA computada; "
        "valide e use seu julgamento, nao copie cego). Use quando ΔDC for material."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_variacao_carteira(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_drill_dc + camada de sugestao (tools grossas, 2026-05-29).

    Nome agente-facing = `get_variacao_carteira` (otica de variacao/auditoria da
    carteira). O servico/UI continua `compute_drill_dc` / rota `/drill/dc` —
    la "drill" e o conceito correto (drill-down da linha no balanco).

    O service ja devolve `resultado_do_dia` com sinais de impacto corrigidos
    (dominio puro, serve UI tambem). Aqui acrescentamos o que e contrato do
    AGENTE — `classificacao_sugerida` (enum de ExplicacaoCategoria) e
    `alerta_sugerido` (SinalAlerta pronto) — como EVIDENCIA computada, nunca
    veredito final (§14: o julgamento e a narrativa continuam do agente).
    """
    from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_drill_dc(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    payload = r.model_dump()
    payload["sugestao"] = _sugestao_drill_dc(r)
    return _to_json(payload)


# Mutacao silenciosa material: dispara alerta quando |ΔVP| dos papeis com
# mudanca de parametro passa do MAIOR entre um piso absoluto e uma fracao do
# saldo DC. Calibrado pelo caso canonico DID99746 (-R$ 22.795 num papel) vs
# ruido de drift (-R$ 2.971 espalhados em REALINVEST 20/05, ~0,012% do estoque).
# POLITICA TUNAVEL — confirmar limiar com Ricardo antes de generalizar p/ outros fundos.
_MUTACAO_ALERTA_BRL = Decimal("5000")       # piso absoluto
_MUTACAO_ALERTA_FRAC = Decimal("0.0005")    # 0,05% do saldo DC


def _sugestao_drill_dc(r: Any) -> dict[str, Any]:
    """Deriva classificacao_sugerida + alerta_sugerido do resultado_do_dia.

    Mapeia os descritores de dominio (motor_dominante/resultado_outlier) para
    os enums do contrato do agente (ExplicacaoCategoria.classificacao_principal
    e SinalAlerta). Retorna sempre `resumo_factual` (so numeros, deterministico).
    """
    res = r.resultado_do_dia
    if res is None:  # defensivo — sempre presente no caminho normal
        return {"classificacao_sugerida": None, "alerta_sugerido": None, "resumo_factual": ""}

    mutacao = res.mutacao_total
    saldo_d0 = r.decomposicao.saldo_d0
    # Material = passa do MAIOR entre piso e fracao (escala com o tamanho do fundo).
    limiar_mutacao = max(_MUTACAO_ALERTA_BRL, _MUTACAO_ALERTA_FRAC * saldo_d0)
    mutacao_material = abs(mutacao) >= limiar_mutacao

    # classificacao_sugerida (enum ExplicacaoCategoria) = o que DOMINOU o dia.
    # Eixo de DOMINANCIA (resultado_outlier), separado do eixo de MATERIALIDADE
    # do alerta. Se o carrego domina (nao-outlier), o dia e carrego_normal mesmo
    # com uma mutacao material — que vira ALERTA, nao headline (caso 20/05).
    # Independente de `motor_dominante` (que vira "misto" quando carrego e
    # multa/juros sao ambos grandes — caso REALINVEST 14/05).
    # Evento NAO-contratado (mora - desconto). A apropriacao antecipada NAO
    # entra aqui — e carrego (rotina), nao evento pontual.
    evento_liq = abs(res.juros_mora - res.desconto_concedido)
    if not res.resultado_outlier:
        classificacao = "carrego_normal"
    elif abs(mutacao) >= evento_liq:
        classificacao = "mutacao_silenciosa_pura"
    else:
        classificacao = "evento_pontual_explicado"

    # alerta_sugerido — SinalAlerta pronto (so quando mutacao material).
    alerta: dict[str, Any] | None = None
    if mutacao_material:
        alerta = {
            "severidade": "atencao",
            "tipo": "mutacao_silenciosa_material",
            "entidade": r.fundo_nome,
            "descricao": (
                f"Mutacao silenciosa de R$ {float(mutacao):+,.2f} no estoque DC "
                f"({r.decomposicao.mutacao_n} papeis com mudanca de parametro sem "
                f"evento de liquidacao/aquisicao)."
            ),
            "evidencia": (
                "Ver mutacao_papeis[] no drill DC (valor_nominal/taxa/vencimento "
                "alterados entre D-1 e D0)."
            ),
        }

    resumo = (
        f"Resultado DC do dia: carrego R$ {float(res.carrego_apropriacao):+,.2f}; "
        f"apropriacao antecipada R$ {float(res.apropriacao_antecipada):+,.2f}; "
        f"juros de mora R$ {float(res.juros_mora):+,.2f}; "
        f"desconto R$ {float(res.desconto_concedido):,.2f}; "
        f"mutacao R$ {float(res.mutacao_total):+,.2f}. "
        f"Motor dominante: {res.motor_dominante}"
        f"{' (OUTLIER — carrego nao domina)' if res.resultado_outlier else ''}. "
        f"Giro (nao move a cota): aquisicoes R$ {float(res.giro_aquisicoes):,.2f}, "
        f"liquidacoes R$ {float(res.giro_liquidacoes):,.2f}."
    )

    return {
        "classificacao_sugerida": classificacao,
        "alerta_sugerido": alerta,
        "resumo_factual": resumo,
    }


@register_tool(
    name="get_drill_pdd",
    description=(
        "Detalhamento da PDD: composicao PDD ativo (faixas A-H) vs WOP "
        "(write-off ja fora do balanco), papeis que migraram para WOP no "
        "dia (write-off real, sem liquidacao formal), e lista de TODOS os "
        "papeis ex-WOP com variacao de PDD entre D-1 e D0 (inclui papeis "
        "LIQUIDADOS com PDD reversa).\n\n"
        "JA VEM PRONTO o bloco `resumo` com a leitura de SINAL (regra dura -- "
        "NAO inverter): constituicao_total (delta>0, PDD subiu, REDUZ o PL Sub), "
        "reversao_total (delta<0, PDD caiu, AUMENTA o PL Sub), delta_liquido, "
        "direcao e impacto_pl_sub (sinal ja correto). E `efeito_vagao[]` "
        "(FORWARD): sacados cujos titulos foram arrastados JUNTOS p/ faixa pior "
        "(>=2 papeis, >=1 vencido) — cada item traz documento_puxador (vencido) "
        "e documentos_arrastados (a vencer). E `vagao_reverso[]`: sacados cujo "
        "puxador vencido LIQUIDOU e LIBEROU os a-vencer (PDD revertido em "
        "cascata) — traz documento_liberador (ex-puxador que saiu) e "
        "documentos_liberados. A reversao vem SPLITADA: `reversao_por_liquidacao` "
        "(o proprio titulo pagou) vs `reversao_por_liberacao` (a-vencer liberado "
        "pela saida do puxador) — os dois somam reversao_total. O bloco `sugestao` traz "
        "classificacao_sugerida (constituicao_pdd/reversao_pdd) + alerta_sugerido "
        "(EVIDENCIA computada; valide e use seu julgamento). Sinal por papel/celula "
        "continua em delta_valor_pdd / sum_delta_pdd. Use quando ΔPDD for material "
        "ou suspeitar de write-off."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_drill_pdd(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_drill_pdd + camada de sugestao (tools grossas, 2026-05-29).

    Service ja devolve `resumo` (sinal de impacto) + `efeito_vagao` detectado.
    Aqui anexamos a camada do contrato do AGENTE — classificacao_sugerida +
    alerta_sugerido — como EVIDENCIA, nao veredito (§14).
    """
    from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_drill_pdd(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    payload = r.model_dump()
    payload["sugestao"] = _sugestao_drill_pdd(r)
    return _to_json(payload)


# Efeito vagao material: dispara alerta de sacado_problematico. POLITICA
# TUNAVEL — calibrar com Ricardo (hoje: grupo com Σ|delta_pdd| >= piso OU
# >= 3 papeis arrastados).
_VAGAO_ALERTA_BRL = Decimal("1000")
_VAGAO_ALERTA_QTD = 3


def _sugestao_drill_pdd(r: Any) -> dict[str, Any]:
    """Deriva classificacao_sugerida + alerta_sugerido do resumo/efeito_vagao.

    classificacao mapeia a direcao do delta (constituicao/reversao) para o enum
    de ExplicacaoCategoria. alerta sai do efeito_vagao material (sacado cujos
    titulos foram arrastados de faixa). resumo_factual = numeros deterministicos.
    """
    resumo = r.resumo
    if resumo is None:  # granular indisponivel (motivo_indisponivel != None)
        return {"classificacao_sugerida": None, "alerta_sugerido": None, "resumo_factual": ""}

    # classificacao_sugerida — enum de ExplicacaoCategoria.
    if resumo.direcao == "constituicao":
        classificacao = "constituicao_pdd"
    elif resumo.direcao == "reversao":
        classificacao = "reversao_pdd"
    else:
        classificacao = None  # dia neutro de PDD — agente decide pelo resto

    # alerta_sugerido — maior grupo de efeito vagao, se material.
    alerta: dict[str, Any] | None = None
    materiais = [
        v for v in r.efeito_vagao
        if abs(v.sum_delta_pdd) >= _VAGAO_ALERTA_BRL or v.qtd_papeis >= _VAGAO_ALERTA_QTD
    ]
    if materiais:
        v = max(materiais, key=lambda g: abs(g.sum_delta_pdd))
        alerta = {
            "severidade": "atencao",
            "tipo": "sacado_problematico",
            "entidade": v.sacado_nome,
            "descricao": (
                f"Efeito vagao no sacado {v.sacado_nome}: {v.qtd_papeis} titulos "
                f"reclassificados p/ faixa {v.faixa_para} (Σ PDD R$ {float(v.sum_delta_pdd):+,.2f}). "
                f"Documento vencido {v.documento_puxador} puxou "
                f"{v.qtd_a_vencer_arrastados} titulo(s) a vencer."
            ),
            "evidencia": (
                f"Puxador (vencido): doc {v.documento_puxador}. Arrastados (a vencer): "
                f"{', '.join(v.documentos_arrastados) or '—'}. Ver efeito_vagao[] no drill PDD."
            ),
        }

    direcao_txt = {"constituicao": "constituicao (reduz PL Sub)",
                   "reversao": "reversao (aumenta PL Sub)",
                   "neutro": "neutra"}[resumo.direcao]
    resumo_factual = (
        f"PDD: {direcao_txt}. Constituicao R$ {float(resumo.constituicao_total):,.2f}, "
        f"reversao R$ {float(resumo.reversao_total):,.2f}, "
        f"liquido R$ {float(resumo.delta_liquido):+,.2f} "
        f"(impacto no PL Sub R$ {float(resumo.impacto_pl_sub):+,.2f}). "
        f"Efeito vagao: {len(r.efeito_vagao)} sacado(s)."
    )

    return {
        "classificacao_sugerida": classificacao,
        "alerta_sugerido": alerta,
        "resumo_factual": resumo_factual,
    }


@register_tool(
    name="get_drill_cpr",
    description=(
        "Detalhamento do CPR ja SEPARADO em `contas_a_receber` (ATIVO) e "
        "`contas_a_pagar` (PASSIVO) — espelha as DUAS linhas do balanco "
        "estrutural. Cada lado traz decomposicao por natureza (diferimento, "
        "taxas, despesas, IOF/IR, aporte engaiolado, outros) + aporte engaiolado.\n\n"
        "REGRA DURA DE SINAL (le SEMPRE daqui, NUNCA do valor cru): cada lado tem "
        "um bloco `resumo` com magnitude_d1/magnitude_d0 (sempre >= 0), "
        "variacao_magnitude (= delta da linha no balanco; <0 = a linha ENCOLHEU) e "
        "impacto_pl_sub com sinal economico ja correto. Contas a Pagar que CAI tem "
        "impacto_pl_sub POSITIVO (reduz o passivo, BOM pra Sub) — o valor cru "
        "(negativo) e a `sum_delta` por natureza tem sinal CONTRARIO ao impacto, "
        "NAO os use pra narrar sentido. Por natureza, use `variacao_magnitude` e "
        "`impacto_pl_sub`.\n\n"
        "Por RUBRICA (top_linhas) leia `transicao` (e valor_d1 vs valor_d0): "
        "`baixada_em_d0` = a rubrica EXISTIA em D-1 e sumiu/zerou em D0 = foi PAGA/"
        "baixada (reduz o passivo, NAO e despesa nova); `nova_em_d0` = constituida no "
        "dia; `cresceu`/`encolheu` = mudou de tamanho. NUNCA infira 'nova provisao' da "
        "data de pagamento no texto da descricao (ex.: '...com pagamento 08/06/26'). "
        "O bloco `sugestao` traz classificacao + alertas (EVIDENCIA, valide). Use "
        "quando ΔContas a Pagar/Receber for material."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_drill_cpr(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_drill_cpr nos DOIS lados + camada de sugestao.

    Tools grossas 2026-05-29 (motivado por bug REALINVEST 28/05): em vez de
    devolver o CPR net (cujo sinal cru no lado pagar enganou o agente — leu
    "Contas a Pagar subiu" quando caiu), devolve receber e pagar separados, cada
    um com `resumo` de magnitude/impacto (sinal economico) — alinhado com as
    duas linhas do balanco. `sugestao` (contrato do agente) anexada como §14.
    """
    from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr

    ua_id, data_d0 = _parse_scope_inputs(scope)
    receber = await compute_drill_cpr(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0, side="receber",
    )
    pagar = await compute_drill_cpr(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0, side="pagar",
    )
    payload = {
        "fundo_nome": pagar.fundo_nome,
        "data": pagar.data,
        "data_anterior": pagar.data_anterior,
        "contas_a_receber": receber.model_dump(),
        "contas_a_pagar": pagar.model_dump(),
        "sugestao": _sugestao_drill_cpr(receber, pagar),
    }
    return _to_json(payload)


def _sugestao_drill_cpr(receber: Any, pagar: Any) -> dict[str, Any]:
    """Sugestao do CPR: leitura factual + alertas (aporte engaiolado).

    classificacao_sugerida fica em `aporte_engaiolado` quando ha aporte
    engaiolado relevante; senao None (CPR raramente domina o dia — o agente
    decide pelo resto). resumo_factual descreve os DOIS lados pela magnitude.
    """
    rr, rp = receber.resumo, pagar.resumo

    # Alerta de aporte engaiolado (qualquer lado; tipicamente no pagar).
    alertas: list[dict[str, Any]] = []
    for lado in (pagar, receber):
        for ap in lado.aportes_engaiolados:
            if ap.estado == "persiste" or abs(ap.valor_d0) > 0 or abs(ap.valor_d1) > 0:
                alertas.append({
                    "severidade": "atencao",
                    "tipo": "outro",
                    "entidade": ap.descricao,
                    "descricao": (
                        f"Aporte engaiolado '{ap.descricao}' {ap.estado} "
                        f"(D-1 R$ {float(ap.valor_d1):,.2f} -> D0 R$ {float(ap.valor_d0):,.2f})."
                    ),
                    "evidencia": "Rubrica 'Aporte' no CPR — ver aportes_engaiolados no drill.",
                })

    classificacao = "aporte_engaiolado" if alertas else None

    def _lado_txt(nome: str, res: Any) -> str:
        if res is None:
            return f"{nome}: (sem dados)"
        return (f"{nome} {res.direcao} de R$ {float(res.magnitude_d1):,.2f} para "
                f"R$ {float(res.magnitude_d0):,.2f} (impacto PL Sub R$ {float(res.impacto_pl_sub):+,.2f})")

    resumo_factual = f"{_lado_txt('Contas a Pagar', rp)}; {_lado_txt('Contas a Receber', rr)}."

    return {
        "classificacao_sugerida": classificacao,
        "alertas_sugeridos": alertas,
        "resumo_factual": resumo_factual,
    }


# ─── Tool 4b: decomposicao por classe de cota (capital vs valorizacao) ───


@register_tool(
    name="get_decomposicao_classes",
    description=(
        "Decompoe o ΔPL de CADA classe de cota (Sub Jr, Mezanino, Senior) "
        "entre D-1 e D0 em efeito-CAPITAL (aporte/resgate de cotistas) vs "
        "efeito-VALORIZACAO (remuneracao/custo da cota no dia). Na otica do "
        "PL Sub Jr, Senior e Mezanino sao PASSIVOS — quando o PL de uma "
        "dessas classes sobe (ex.: categoria 'senior' ou 'mezanino' com Δ "
        "material no balanco), USE esta tool pra saber se foi aporte (entrou "
        "dinheiro novo, aumentou o passivo, diluiu a Sub) ou apenas custo "
        "financeiro da cota. Retorna por classe: patrimonio/quantidade/"
        "valor_cota (d1/d0), fluxos (entradas/saidas/aporte/retirada), "
        "efeito_capital, efeito_valorizacao e classificacao "
        "(aporte|resgate|apenas_valorizacao). efeito_capital vem dos fluxos "
        "reportados pela QiTech; efeito_valorizacao = ΔPL - efeito_capital. "
        "Cross-check por quantidade incluido.\n\n"
        "JA VEM PRONTO o bloco `sugestao` com `por_classe` (classificacao_sugerida "
        "ja mapeada pro enum: aporte_classe / resgate_classe / carrego_normal, e o "
        "impacto_pl_sub com SINAL ja corrigido — aporte numa PRIORITARIA (Sr/Mez) "
        "REDUZ o PL Sub por diluicao; aporte na SUBORDINADA aumenta) e "
        "`alertas_sugeridos` (captacao/resgate material >= R$ 50k OU 0,5% do PL Sub, "
        "como EVIDENCIA computada — valide, nao copie cego). SEMPRE chame quando a "
        "categoria senior ou mezanino aparecer no Nivel 3."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_decomposicao_classes(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_decomposicao_classes_mec + camada de sugestao.

    Tools grossas 2026-05-29: o service ja decompoe capital vs valorizacao por
    classe. Aqui mapeamos a classificacao de dominio (aporte/resgate/
    apenas_valorizacao) pro enum do agente e montamos os alertas de captacao
    material — regras que viviam no prompt. EVIDENCIA, nao veredito (§14).
    """
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_decomposicao_classes_mec,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_decomposicao_classes_mec(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    r["sugestao"] = _sugestao_decomposicao_classes(r)
    return _to_json(r)


# Captacao/resgate material numa classe: gatilho de alerta. POLITICA TUNAVEL.
_CAPITAL_ALERTA_BRL = Decimal("50000")
_CAPITAL_ALERTA_FRAC = Decimal("0.005")  # 0,5% do PL Sub

# Mapa classificacao de dominio -> enum ExplicacaoCategoria.classificacao_principal.
_CLASSIF_CLASSE_MAP = {
    "aporte": "aporte_classe",
    "resgate": "resgate_classe",
    "apenas_valorizacao": "carrego_normal",
}


def _sugestao_decomposicao_classes(r: dict[str, Any]) -> dict[str, Any]:
    """Deriva classificacao_sugerida por classe + alertas de captacao material.

    `compute_decomposicao_classes_mec` devolve dict (nao Pydantic) com `classes`.
    Cada classe vira uma ExplicacaoCategoria distinta no Nivel 3 do agente —
    por isso a sugestao e POR CLASSE. impacto_pl_sub ja vem com o sinal correto
    da otica Sub Jr (passivo prioritario: aporte reduz; subordinada: aporte soma).
    """
    classes = r.get("classes", [])
    # PL Sub = patrimonio_d0 da classe subordinada (base do limiar de 0,5%).
    pl_sub_d0 = next(
        (Decimal(str(c["patrimonio_d0"])) for c in classes if c["classe"] == "sub_jr"),
        Decimal("0"),
    )
    limiar = max(_CAPITAL_ALERTA_BRL, _CAPITAL_ALERTA_FRAC * abs(pl_sub_d0))

    por_classe: dict[str, Any] = {}
    alertas: list[dict[str, Any]] = []
    for c in classes:
        classe = c["classe"]
        ec = Decimal(str(c["efeito_capital"]))
        ev = Decimal(str(c["efeito_valorizacao"]))
        is_prioritaria = classe in ("senior", "mezanino")
        # Impacto no PL Sub: prioritaria e passivo (aporte reduz a Sub por
        # diluicao); subordinada e o proprio PL (aporte soma direto).
        impacto_pl_sub = -ec if is_prioritaria else ec

        por_classe[classe] = {
            "classificacao_sugerida": _CLASSIF_CLASSE_MAP.get(c["classificacao"]),
            "efeito_capital": float(ec),
            "efeito_valorizacao": float(ev),
            "impacto_pl_sub_do_capital": float(impacto_pl_sub),
        }

        if abs(ec) >= limiar:
            verbo = "Aporte" if ec > 0 else "Resgate"
            if is_prioritaria:
                efeito_sub = "REDUZ o PL Sub (diluicao)" if ec > 0 else "AUMENTA o PL Sub"
            else:
                efeito_sub = "AUMENTA o PL Sub" if ec > 0 else "REDUZ o PL Sub"
            alertas.append({
                "severidade": "atencao",
                "tipo": "outro",
                "entidade": c["label"],
                "descricao": (
                    f"{verbo} de capital de R$ {float(ec):+,.2f} na {c['label']} "
                    f"(valorizacao do dia R$ {float(ev):+,.2f}). Evento de captacao, "
                    f"NAO custo — {efeito_sub}."
                ),
                "evidencia": (
                    f"Fluxos QiTech: entradas {c['entradas']}, saidas {c['saidas']}, "
                    f"aporte {c['aporte']}, retirada {c['retirada']}. "
                    f"Cross-check por qtd: {c['cross_check_capital_por_qtd']}."
                ),
            })

    return {
        "por_classe": por_classe,
        "alertas_sugeridos": alertas,
        "limiar_capital_brl": float(limiar),
    }


# ─── Tool 5: cross-tabela — eventos adjacentes pra um papel ──────────────


@register_tool(
    name="get_eventos_liquidacao_adjacentes",
    description=(
        "Busca em wh_liquidacao_recebivel todos os eventos de baixa (LIQUIDAÇÃO "
        "NORMAL, BAIXA POR DEPOSITO SACADO/CEDENTE, BAIXA POR RECOMPRA, "
        "LIQUIDAÇÃO PARCIAL, ABATIMENTO CONCEDIDO, etc.) para um papel "
        "especifico numa janela [D-N, D+N] em torno da data analisada. "
        "Use APOS detectar mutacao silenciosa pra verificar se houve evento "
        "formal de liquidacao adjacente que explica a mudanca (ex.: mutacao "
        "de VN no dia X seguida de LIQUIDAÇÃO PARCIAL em X+1 = abatimento "
        "off-record sendo formalizado)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "seu_numero": {
                "type": "string",
                "description": "Identificador do papel (ex.: 'DID94816').",
            },
            "janela_dias": {
                "type": "integer",
                "minimum": 1,
                "maximum": 30,
                "description": "Janela [D-N, D+N] em torno de data_d0. Default 5.",
            },
        },
        "required": ["seu_numero"],
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_eventos_liquidacao_adjacentes(
    scope: ScopedContext, args: dict[str, Any],
) -> str:
    from app.modules.cadastros.public import UnidadeAdministrativa
    from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel

    ua_id, data_d0 = _parse_scope_inputs(scope)
    seu_numero = args["seu_numero"]
    janela = int(args.get("janela_dias", 5))

    ua = (
        await scope.db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == scope.tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None or not ua.cnpj:
        return _to_json({"erro": f"UA {ua_id} nao encontrada ou sem CNPJ"})

    rows = (
        await scope.db.execute(
            select(LiquidacaoRecebivel)
            .where(LiquidacaoRecebivel.tenant_id == scope.tenant_id)
            .where(LiquidacaoRecebivel.fundo_doc == ua.cnpj)
            .where(LiquidacaoRecebivel.seu_numero == seu_numero)
            .where(
                LiquidacaoRecebivel.data_posicao.between(
                    data_d0 - timedelta(days=janela),
                    data_d0 + timedelta(days=janela),
                )
            )
            .order_by(LiquidacaoRecebivel.data_posicao)
        )
    ).scalars().all()

    eventos = [
        {
            "data_posicao": r.data_posicao,
            "tipo_movimento": r.tipo_movimento,
            "valor_pago": r.valor_pago,
            "valor_aquisicao": r.valor_aquisicao,
            "valor_vencimento": r.valor_vencimento,
            "ajuste": r.ajuste,
            "st_recebivel": r.st_recebivel,
            "ganho_liquido": r.valor_pago - r.valor_aquisicao - r.ajuste,
        }
        for r in rows
    ]
    return _to_json({
        "seu_numero": seu_numero,
        "janela": [
            (data_d0 - timedelta(days=janela)).isoformat(),
            (data_d0 + timedelta(days=janela)).isoformat(),
        ],
        "eventos": eventos,
        "n": len(eventos),
    })


# ─── Tool 6: historico do papel no estoque ───────────────────────────────


@register_tool(
    name="get_historico_estoque_papel",
    description=(
        "Trajetoria diaria de um papel em wh_estoque_recebivel nos ultimos "
        "N dias: valor_nominal, valor_presente, valor_pdd, faixa_pdd, "
        "situacao_recebivel. Use pra entender se uma mutacao foi um evento "
        "isolado ou parte de tendencia (ex.: VN caindo gradualmente vs "
        "salto unico)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "seu_numero": {
                "type": "string",
                "description": "Identificador do papel.",
            },
            "dias": {
                "type": "integer",
                "minimum": 1,
                "maximum": 90,
                "description": "Janela retroativa em dias corridos. Default 30.",
            },
        },
        "required": ["seu_numero"],
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_historico_estoque_papel(
    scope: ScopedContext, args: dict[str, Any],
) -> str:
    from app.modules.cadastros.public import UnidadeAdministrativa
    from app.warehouse.estoque_recebivel import EstoqueRecebivel

    ua_id, data_d0 = _parse_scope_inputs(scope)
    seu_numero = args["seu_numero"]
    dias = int(args.get("dias", 30))

    ua = (
        await scope.db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == scope.tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None or not ua.cnpj:
        return _to_json({"erro": f"UA {ua_id} nao encontrada ou sem CNPJ"})

    rows = (
        await scope.db.execute(
            select(EstoqueRecebivel)
            .where(EstoqueRecebivel.tenant_id == scope.tenant_id)
            .where(EstoqueRecebivel.fundo_doc == ua.cnpj)
            .where(EstoqueRecebivel.seu_numero == seu_numero)
            .where(
                EstoqueRecebivel.data_referencia.between(
                    data_d0 - timedelta(days=dias),
                    data_d0,
                )
            )
            .order_by(EstoqueRecebivel.data_referencia)
        )
    ).scalars().all()

    if not rows:
        return _to_json({
            "seu_numero": seu_numero,
            "n": 0,
            "obs": "Papel nao encontrado no estoque nos ultimos N dias.",
        })

    first = rows[0]
    historico = [
        {
            "data_referencia": r.data_referencia,
            "valor_presente": r.valor_presente,
            "valor_nominal": r.valor_nominal,
            "valor_pdd": r.valor_pdd,
            "faixa_pdd": r.faixa_pdd,
            "situacao_recebivel": r.situacao_recebivel,
            "data_vencimento_ajustada": r.data_vencimento_ajustada,
        }
        for r in rows
    ]
    return _to_json({
        "seu_numero": seu_numero,
        "cedente_doc": first.cedente_doc,
        "cedente_nome": first.cedente_nome,
        "sacado_doc": first.sacado_doc,
        "sacado_nome": first.sacado_nome,
        "tipo_recebivel": first.tipo_recebivel,
        "taxa_recebivel": first.taxa_recebivel,
        "data_emissao": first.data_emissao,
        "data_vencimento_original": first.data_vencimento_original,
        "historico": historico,
        "n": len(historico),
    })


# ─── Tool 7: concentracao por cedente+sacado ─────────────────────────────


@register_tool(
    name="get_papeis_mesmo_cedente_sacado",
    description=(
        "Lista todos os papeis no estoque do mesmo par (cedente, sacado) "
        "presentes em D0 OU que tenham aparecido na janela retroativa. "
        "Inclui faixa_pdd, valor_presente, situacao_recebivel. Use pra "
        "detectar concentracao de risco (mesmo cedente com varios papeis "
        "do mesmo sacado em situacao similar) ou padrao reincidente (mesmo "
        "cedente com historico de mutacoes silenciosas em multiplos papeis)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cedente_doc": {
                "type": "string",
                "description": "CNPJ do cedente (14 digitos, sem mascara).",
            },
            "sacado_doc": {
                "type": "string",
                "description": "CNPJ do sacado (14 digitos, sem mascara). "
                               "Opcional — se ausente, lista TODOS os papeis "
                               "do cedente independente do sacado.",
            },
            "janela_dias": {
                "type": "integer",
                "minimum": 1,
                "maximum": 60,
                "description": "Janela retroativa pra papeis ja liquidados. Default 30.",
            },
        },
        "required": ["cedente_doc"],
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="medium",
    cacheable=True,
)
async def get_papeis_mesmo_cedente_sacado(
    scope: ScopedContext, args: dict[str, Any],
) -> str:
    from app.modules.cadastros.public import UnidadeAdministrativa
    from app.warehouse.estoque_recebivel import EstoqueRecebivel

    ua_id, data_d0 = _parse_scope_inputs(scope)
    cedente_doc = args["cedente_doc"]
    sacado_doc = args.get("sacado_doc")
    janela = int(args.get("janela_dias", 30))

    ua = (
        await scope.db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == scope.tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None or not ua.cnpj:
        return _to_json({"erro": f"UA {ua_id} nao encontrada ou sem CNPJ"})

    stmt = (
        select(EstoqueRecebivel)
        .where(EstoqueRecebivel.tenant_id == scope.tenant_id)
        .where(EstoqueRecebivel.fundo_doc == ua.cnpj)
        .where(EstoqueRecebivel.cedente_doc == cedente_doc)
        .where(
            EstoqueRecebivel.data_referencia.between(
                data_d0 - timedelta(days=janela),
                data_d0,
            )
        )
    )
    if sacado_doc:
        stmt = stmt.where(EstoqueRecebivel.sacado_doc == sacado_doc)
    rows = (await scope.db.execute(stmt)).scalars().all()

    # Agrupa por papel — uma linha com a observacao MAIS RECENTE de cada.
    by_seu_numero: dict[str, Any] = {}
    for r in rows:
        cur = by_seu_numero.get(r.seu_numero)
        if cur is None or r.data_referencia > cur["data_referencia"]:
            by_seu_numero[r.seu_numero] = {
                "seu_numero": r.seu_numero,
                "numero_documento": r.numero_documento,
                "data_referencia": r.data_referencia,
                "sacado_doc": r.sacado_doc,
                "sacado_nome": r.sacado_nome,
                "tipo_recebivel": r.tipo_recebivel,
                "valor_nominal": r.valor_nominal,
                "valor_presente": r.valor_presente,
                "valor_pdd": r.valor_pdd,
                "faixa_pdd": r.faixa_pdd,
                "situacao_recebivel": r.situacao_recebivel,
                "data_vencimento_ajustada": r.data_vencimento_ajustada,
            }

    papeis = sorted(
        by_seu_numero.values(),
        key=lambda p: (p["data_referencia"], p["seu_numero"]),
        reverse=True,
    )
    cedente_nome = rows[0].cedente_nome if rows else None
    return _to_json({
        "cedente_doc": cedente_doc,
        "cedente_nome": cedente_nome,
        "sacado_doc_filtro": sacado_doc,
        "janela_dias": janela,
        "n_papeis_unicos": len(papeis),
        "papeis": papeis,
    })


# ─── Tool 8: sanity Nivel 1 (identidade contabil do dia) ─────────────────


# Bandas de resíduo do Nivel 1 (agent-contract, antes no prompt v8). POLITICA
# TUNAVEL. < ATENCAO: fechamento sadio/arredondamento. ATENCAO <= |res| <
# CRITICO: divergencia moderada, segue a analise + 1 alerta. >= CRITICO: para.
_RESIDUO_ATENCAO_BRL = Decimal("100")
_RESIDUO_CRITICO_BRL = Decimal("5000")


@register_tool(
    name="check_identidade_contabil",
    description=(
        "Sanity check Nivel 1 (PRIMEIRA tool da analise): a identidade contabil "
        "bateu? (ΔPL granular) ≈ (ΔPL fonte MEC).\n\n"
        "JA VEM PRONTA a decisao do Nivel 1 (regras antes no prompt): `severidade` "
        "(ok|atencao|critico pelas bandas R$100/R$5.000), `deve_continuar` (False so "
        "em residuo critico >= R$5.000 — ai PARE: preencha apenas nivel_1 + sumario "
        "+ o alerta/acao sugeridos), `alerta_sugerido` (SinalAlerta residuo_alto "
        "pronto, ou null) e `acao_sugerida` (SugestaoAcao pronta, ou null). EVIDENCIA "
        "computada — use seu julgamento, nao copie cego. Tambem: passou, residuo_brl, "
        "pl_deduzido_delta, pl_fonte_delta, diagnostico."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tolerancia_brl": {
                "type": "number",
                "description": "Threshold do flag `passou` (fechamento sadio). Default 1.0. "
                               "NAO afeta severidade (que usa bandas R$100/R$5.000).",
            },
        },
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def check_identidade_contabil(
    scope: ScopedContext, args: dict[str, Any],
) -> str:
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_balanco_estrutural,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    tolerancia = Decimal(str(args.get("tolerancia_brl", 1.0)))

    r = await compute_balanco_estrutural(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    residuo = r.reconciliacao.residuo_delta
    abs_res = abs(residuo)
    passou = abs_res < tolerancia

    # Severidade pelas bandas do Nivel 1 (alinhadas com diagnostico + acao).
    if abs_res >= _RESIDUO_CRITICO_BRL:
        severidade = "critico"
        deve_continuar = False
        diagnostico = (
            f"DESALINHAMENTO CRITICO de R$ {residuo:+.2f} (>= R$ {_RESIDUO_CRITICO_BRL:.0f}). "
            f"Identidade contabil quebrou — pipeline tem furo (snapshot QiTech faltando, "
            f"mapper bug, etc.). PARE: a analise das variacoes pode estar invalida."
        )
    elif abs_res >= _RESIDUO_ATENCAO_BRL:
        severidade = "atencao"
        deve_continuar = True
        diagnostico = (
            f"Divergencia moderada de R$ {residuo:+.2f} (R$ {_RESIDUO_ATENCAO_BRL:.0f} a "
            f"R$ {_RESIDUO_CRITICO_BRL:.0f}). Acima de arredondamento, mas nao critico. "
            f"SEGUE a analise — investigue a categoria de maior |Δ| pra localizar a origem."
        )
    elif abs_res < Decimal("0.05"):
        severidade = "ok"
        deve_continuar = True
        diagnostico = "Fechamento perfeito (arredondamento <= 5 centavos)."
    else:
        severidade = "ok"
        deve_continuar = True
        diagnostico = (
            f"Fechamento sadio (residuo de R$ {residuo:+.2f} — arredondamento "
            f"estrutural QiTech, abaixo de R$ {_RESIDUO_ATENCAO_BRL:.0f})."
        )

    # alerta_sugerido + acao_sugerida prontos (so quando ha o que reportar).
    alerta: dict[str, Any] | None = None
    acao: dict[str, Any] | None = None
    if severidade in ("atencao", "critico"):
        alerta = {
            "severidade": severidade,
            "tipo": "residuo_alto",
            "entidade": r.fundo_nome,
            "descricao": (
                f"Identidade contabil com residuo de R$ {residuo:+.2f} no dia "
                f"({severidade}). ΔPL granular vs ΔPL fonte MEC nao fecham."
            ),
            "evidencia": (
                f"PL deduzido Δ R$ {float(r.pl_sub_delta):+,.2f} vs PL fonte MEC Δ "
                f"R$ {float(r.reconciliacao.pl_fonte_delta):+,.2f}."
            ),
        }
    if severidade == "critico":
        acao = {
            "prioridade": "alta",
            "acao": "investigar",
            "detalhe": (
                "Pipeline com furo (residuo >= R$ 5.000). Preencha apenas nivel_1 + "
                "sumario + este alerta/acao; deixe nivel_2 e nivel_3 vazios ate o "
                "desalinhamento ser resolvido."
            ),
        }

    return _to_json({
        "passou": passou,
        "severidade": severidade,
        "deve_continuar": deve_continuar,
        "residuo_brl": residuo,
        "pl_deduzido_delta": r.pl_sub_delta,
        "pl_fonte_delta": r.reconciliacao.pl_fonte_delta,
        "tolerancia_brl": tolerancia,
        "diagnostico": diagnostico,
        "alerta_sugerido": alerta,
        "acao_sugerida": acao,
    })


# ─── Tool: conferencia de cessao (aquisicao DC vs caixa/extrato) ───────────


@register_tool(
    name="get_conferencia_cessao",
    description=(
        "Confere as AQUISICOES de recebiveis do dia (cessao) contra os DEBITOS "
        "de caixa aos cedentes no extrato bancario. Por cedente: valor_aquisicao "
        "(Σ valor_compra que o fundo registrou pagar) vs valor_debito_caixa (Σ "
        "debitos ao cedente no extrato, janela [D, D+janela_dias]), com `status`:\n"
        "  - 'casa' = debito bate a aquisicao (cessao liquidada certo);\n"
        "  - 'descasa' = extrato existe mas o cedente NAO bate (valor diverge ou "
        "sem debito) -> CANDIDATO A ERRO DE LANCAMENTO DC<->caixa;\n"
        "  - 'sem_extrato' = extrato nao sincronizado pro periodo (NAO da pra "
        "conferir — NAO e erro de dado do fundo).\n"
        "REGRA: se `extrato_disponivel=False`, o dia inteiro caiu em furo de sync "
        "do extrato — informe isso, NAO acuse descasamento. `match_exato=True` "
        "quando um debito UNICO == a aquisicao (TED de cessao limpa). Achado: a "
        "cessao liquida como TED ao cedente no valor exato da compra, mesmo dia. "
        "Use quando houver aquisicao material no dia OU pra auditar consistencia "
        "caixa<->DC."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_conferencia_cessao(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_conferencia_cessao. ua_id+data vem do scope."""
    from app.modules.controladoria.services.conferencia_cessao import (
        compute_conferencia_cessao,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_conferencia_cessao(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_conferencia_liquidacao",
    description=(
        "Confere a ENTRADA de caixa por liquidacao do dia (D0) contra as "
        "liquidacoes que a originaram. A entrada vem por canais com timing "
        "distinto:\n"
        "  - FLOATING (forte, point-in-time): `prov_lotes` decompoe o bucket "
        "'LIQUIDADOS TOTAL - PROV' de D0 (caixa de cobranca que pingou hoje); "
        "cada lote casa POR VALOR com a Σ das cobrancas que floatam (NORMAL + "
        "CARTÓRIO + PARCIAL) de um dia anterior (`dia_origem`, `defasagem_dias`: "
        "1=d+1, 2=d+2). `status='casa'` = rastreado; 'origem_nao_identificada' = "
        "lote sem origem (ATENCAO). `floating_status='casa'` quando todo o PROV de "
        "D0 rastreia (residuo ~0); 'diverge' quando sobra lote sem origem.\n"
        "  - IMEDIATA (fraca): `sacado_hoje` (BAIXA POR DEPOSITO SACADO) credita no "
        "mesmo dia, AGREGADO no extrato — use `extrato_credito_dia` so como contexto "
        "(inclui creditos nao-liquidacao); `extrato_disponivel=False` = gap de sync "
        "(NAO conferivel, NAO acuse divergencia).\n"
        "  - HONRA do cedente (`honra_cedente_*` = DEPOSITO CEDENTE + RECOMPRA): "
        "`todos_atrasados=True` e sinal de inadimplencia.\n"
        "  - `floating_hoje` = cobrancas de D0 que so pingam no PROXIMO dia util "
        "(PROJECAO, NAO conferencia — point-in-time).\n"
        "DIRECAO: a conferencia e PRA TRAS (caixa que caiu hoje <- origem em dias "
        "anteriores), verificavel hoje. NAO trate `floating_hoje` como conferido. "
        "Use pra auditar a entrada de caixa por liquidacao do dia."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_conferencia_liquidacao(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_conferencia_liquidacao. ua_id+data vem do scope."""
    from app.modules.controladoria.services.conferencia_liquidacao import (
        compute_conferencia_liquidacao,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_conferencia_liquidacao(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_movimento_nota_comercial",
    description=(
        "Abre a linha 'Op. Estruturadas' do balanco (= Notas Comerciais) em "
        "movimentos por codigo de NC, entre D-1 e D0. POSICAO-FIRST: a fonte "
        "autoritativa do que mexeu e a posicao (wh_posicao_renda_fixa), nao o "
        "caixa. Por NC: `tipo` = aquisicao (codigo novo -> valor_aplicado saiu do "
        "caixa) | amortizacao (valor_bruto caiu, LIQUIDO do carrego -> NC paga em "
        "parcela) | quitacao (zerou/sumiu -> liquidada inteira) | apropriacao "
        "(valor_bruto subiu -> so carrego/juros do dia, NAO e caixa). Cada "
        "movimento traz `caixa_evento` (<0 saida, >0 entrada, 0 carrego) e um "
        "`extrato_sinal` SOFT (indicio de valor compativel no extrato — NUNCA "
        "prova: a liquidacao da NC vem como transferencia interna do fundo, "
        "generica a DC+NC, e nao mostra o devedor). Totais: total_aquisicao, "
        "total_amortizacao, total_apropriacao, e delta_posicao (= ΔSaldo da linha "
        "do balanco). Use pra explicar a variacao de Op. Estruturadas. A "
        "amortizacao e LIQUIDA do carrego — o bruto recebido ~ |delta| + carrego."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_movimento_nota_comercial(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_conferencia_nota_comercial. ua_id+data vem do scope."""
    from app.modules.controladoria.services.conferencia_nota_comercial import (
        compute_conferencia_nota_comercial,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_conferencia_nota_comercial(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_movimento_aplicacoes",
    description=(
        "Abre a variacao do grupo 'Aplicacoes' do balanco (exceto Op. "
        "Estruturadas/NC, que tem auditor proprio) entre D-1 e D0. DEEP em "
        "Fundos DI EXTERNO (ITAU SOBERANO etc. — onde o fundo estaciona caixa "
        "ocioso): por fundo, decompoe o ΔSaldo em CAPITAL (`aplicacao_resgate` = "
        "Δqtd x cota; >0 aplicou caixa, <0 resgatou) vs VALORIZACAO (rendimento "
        "DI = residuo). `tipo` = aplicacao | resgate | so_valorizacao. Cross-ref "
        "LIMPO: `caixa_aplicacao`/`caixa_resgate` vem do demonstrativo de caixa "
        "('Aplicacao no Fundo X'/'Resgate do Fundo X'), e `caixa_confirma`=True "
        "quando o net de caixa bate o capital da posicao. LIGHT nas linhas "
        "menores (`outras_linhas`: Titulos Publicos, Compromissada, Outros) — so "
        "ΔSaldo, geralmente imaterial/vazio. Totais: total_capital_liquido (net "
        "aplicado/resgatado), total_valorizacao (rendimento DI), delta_fundos_di, "
        "delta_aplicacoes_total. Fundos INTERNOS (REALINVEST A VENCER/VENCIDOS) "
        "sao DC e ficam fora. Use pra explicar a variacao de Aplicacoes."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_movimento_aplicacoes(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_movimento_aplicacoes. ua_id+data vem do scope."""
    from app.modules.controladoria.services.conferencia_aplicacoes import (
        compute_movimento_aplicacoes,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_movimento_aplicacoes(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_movimento_contas_a_pagar",
    description=(
        "Abre a linha 'Contas a Pagar' do balanco (provisoes de despesa, CPR<0) "
        "entre D-1 e D0, com o lado de PAGAMENTO. Duas metades:\n"
        "  - PROVISOES (`provisoes[]`, por descricao normalizada — datas do texto "
        "ignoradas): `tipo` = apropriacao (provisao de taxa CRESCEU = accrual do "
        "dia) | nova_provisao | baixa (reduziu) | quitada (zerou). Totais: "
        "total_apropriacao (accrual), total_baixa (provisao que saiu). `delta_cpr` "
        "= ΔSaldo da linha.\n"
        "  - PAGAMENTOS de despesa no caixa (`pagamentos[]`), classificados pelo "
        "CODIGO `historico` do extrato: `canal` = codigo_proprio (debito direto da "
        "administradora: custodia/adm/CVM/ANBIMA/auditoria/registradora/IR/IOF...) "
        "| ted_fornecedor (TED 0307 a fornecedor: ONBOARD consultoria/cobranca, "
        "rating, etc.) | tarifa_ted (tarifa bancaria 0770). `provisionado`=True "
        "quando casa uma provisao baixada (por tipo OU por valor exato). "
        "total_nao_provisionado = pagamentos sem provisao (tarifas + despesa "
        "inesperada).\n"
        "REGRA: provisao que ZEROU + pagamento casado = pagamento real; provisao "
        "que zerou SEM pagamento = estorno/wash. Pagamento com provisionado=False "
        "(fora tarifa rotineira) = ATENCAO (saida que escapou do contas a pagar). "
        "Use pra auditar a variacao de Contas a Pagar e os pagamentos do dia."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    module=Module.CONTROLADORIA,
    min_permission=Permission.READ,
    cost_hint="cheap",
    cacheable=True,
)
async def get_movimento_contas_a_pagar(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_movimento_contas_a_pagar. ua_id+data vem do scope."""
    from app.modules.controladoria.services.conferencia_contas_a_pagar import (
        compute_movimento_contas_a_pagar,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_movimento_contas_a_pagar(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)

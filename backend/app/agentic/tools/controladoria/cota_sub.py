"""Tools agenticas pra analise da variacao da Cota Sub Jr.

9 tools registradas (5 wrappers de services existentes + 4 novas pra
cruzamentos que o agente faz manualmente em conversas com Ricardo).
O 5o wrapper (get_decomposicao_classes, 2026-05-26) decompoe o ΔPL de
cada classe de cota em efeito-capital (aporte/resgate) vs valorizacao.

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
        "Retorna o balanço patrimonial completo do FIDC otica Sub Jr para "
        "a data analisada (D0) vs dia util anterior (D-1). Inclui as 12 "
        "categorias (Direitos Creditorios, PDD, Tesouraria, Senior, etc.) "
        "com d1/d0/delta cada + somas + identidade contabil (PL deduzido "
        "vs PL fonte MEC + residuo do dia). Use SEMPRE no inicio da "
        "analise pra contexto geral."
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
    """Wrap de compute_balanco_patrimonial. ua_id+data vem do scope."""
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_balanco_patrimonial,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_balanco_patrimonial(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_drill_dc",
    description=(
        "Decompoe a variacao da linha Direitos Creditorios entre D-1 e D0 "
        "em 5 buckets a partir do granular wh_estoque_recebivel: "
        "aquisicoes (papeis novos), liquidacoes (papeis baixados pelo VP), "
        "migracao WOP (papeis que viraram write-off), apropriacao de juros "
        "(populacao constante sem mudanca de parametro), mutacao silenciosa "
        "(papeis que mudaram valor_nominal/taxa/vencimento sem evento). "
        "Identidade fecha por construcao (residuo ~ R$ 0). Inclui lista de "
        "papeis em cada bucket nao-vazio. Use quando ΔDC for material."
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
async def get_drill_dc(scope: ScopedContext, args: dict[str, Any]) -> str:
    """Wrap de compute_drill_dc."""
    from app.modules.controladoria.services.cota_sub_drill_dc import compute_drill_dc

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_drill_dc(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_drill_pdd",
    description=(
        "Detalhamento da PDD: composicao PDD ativo (faixas A-H) vs WOP "
        "(write-off ja fora do balanco), papeis que migraram para WOP no "
        "dia (write-off real, sem liquidacao formal), e lista de TODOS os "
        "papeis ex-WOP com variacao de PDD entre D-1 e D0 (inclui papeis "
        "LIQUIDADOS com PDD reversa). Use quando ΔPDD for material ou "
        "quando suspeitar de write-off."
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
    """Wrap de compute_drill_pdd."""
    from app.modules.controladoria.services.cota_sub_drill_pdd import compute_drill_pdd

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_drill_pdd(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


@register_tool(
    name="get_drill_cpr",
    description=(
        "Detalhamento do CPR (Contas a Pagar e Receber): totais D-1/D0/Δ, "
        "decomposicao por natureza (diferimento, apropriacao de taxa, "
        "despesa apropriada, IOF/IR, aporte engaiolado, outros) com top "
        "linhas de cada, detector de aporte engaiolado (rubrica 'Aporte' "
        "com saldo nao zero que persiste no CPR ate ser resolvida). Use "
        "quando ΔCPR for material ou suspeitar de evento administrativo."
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
    """Wrap de compute_drill_cpr."""
    from app.modules.controladoria.services.cota_sub_drill_cpr import compute_drill_cpr

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_drill_cpr(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


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
        "Cross-check por quantidade incluido. SEMPRE chame quando a categoria "
        "senior ou mezanino aparecer no Nivel 3."
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
    """Wrap de compute_decomposicao_classes_mec. ua_id+data vem do scope."""
    from app.modules.controladoria.services.balanco_patrimonial import (
        compute_decomposicao_classes_mec,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    r = await compute_decomposicao_classes_mec(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    return _to_json(r)


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


@register_tool(
    name="check_identidade_contabil",
    description=(
        "Sanity check Nivel 1 do agente — verifica se a identidade "
        "contabil bateu no dia: (ΔPL calculado pelo granular) ≈ (ΔPL fonte "
        "MEC). Retorna {passou, residuo_brl, pl_deduzido_delta, pl_fonte_delta, "
        "tolerancia}. Use SEMPRE como primeira tool da analise antes de "
        "investigar variacoes — se residuo for grande, ha desalinhamento de "
        "pipeline e analise pode estar invalida."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tolerancia_brl": {
                "type": "number",
                "description": "Threshold em BRL acima do qual residuo eh "
                               "considerado problema. Default 1.0.",
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
        compute_balanco_patrimonial,
    )

    ua_id, data_d0 = _parse_scope_inputs(scope)
    tolerancia = Decimal(str(args.get("tolerancia_brl", 1.0)))

    r = await compute_balanco_patrimonial(
        scope.db, tenant_id=scope.tenant_id, ua_id=ua_id, data_d0=data_d0,
    )
    residuo = r.residuo_identidade_delta
    passou = abs(residuo) < tolerancia

    if abs(residuo) < Decimal("0.05"):
        diagnostico = "Fechamento perfeito (arredondamento <= 5 centavos)."
    elif passou:
        diagnostico = (
            f"Fechamento sadio (residuo de R$ {residuo:+.2f} dentro da "
            f"tolerancia de R$ {tolerancia:.2f} — arredondamento estrutural QiTech)."
        )
    elif abs(residuo) < Decimal("100"):
        diagnostico = (
            f"Residuo elevado de R$ {residuo:+.2f}. Acima do esperado "
            f"(centavos) mas ainda nao critico (<R$ 100). Investigar "
            f"categoria com maior |Δ| pra encontrar desalinhamento."
        )
    else:
        diagnostico = (
            f"DESALINHAMENTO CRITICO de R$ {residuo:+.2f}. Identidade "
            f"contabil quebrou. Analise das variacoes pode estar invalida "
            f"— pipeline tem furo (snapshot QiTech faltando, mapper bug, etc.)."
        )

    return _to_json({
        "passou": passou,
        "residuo_brl": residuo,
        "pl_deduzido_delta": r.pl_deduzido_delta,
        "pl_fonte_delta": r.pl_fonte_delta,
        "tolerancia_brl": tolerancia,
        "diagnostico": diagnostico,
    })

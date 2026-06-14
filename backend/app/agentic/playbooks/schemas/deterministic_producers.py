"""Deterministic producers — silver payload -> SectionDescriptor (Passo 2-A).

A camada "consulta/silver" do dossiê (cadastral, faturamento, societário) vira
seções de bloco no descritor, ao lado das seções de agente. Decisão A1: o
backend constrói; estes mappers espelham os painéis determinísticos das
AnalysisViews do cockpit.

PUROS: payload (dict, como os services `build_*` devolvem) -> SectionDescriptor.
Sem DB — o endpoint busca o payload e chama estes. Cada produtor anexa sua seção
à estação do nó-fonte (id da estação == id do nó âncora). Começo: cadastral
(campos já projetados pelo Contrato de Dados). Faturamento/societário: próximos.

See docs/esteira-credito-interface-camadas.md §5 (Passo 2-A).
"""

from __future__ import annotations

from typing import Any

from app.agentic.playbooks.schemas.section_descriptor import (
    Apontamento,
    ApontamentosBlock,
    Block,
    FichaBlock,
    FichaCampo,
    ProvenanceRef,
    SectionDescriptor,
    TabelaBlock,
    TabelaCelula,
    TabelaColuna,
)

_BRL = "R$ "


def _brl(value: Any) -> str | None:
    """Número -> 'R$ 1.234,56' (None se não numérico)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n == 0:
        return None
    return _BRL + f"{n:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _cpf_mask(ultimos4: Any) -> str:
    """Últimos 4 dígitos -> '***.***.***-XX' (CPF redactado)."""
    s = str(ultimos4 or "").strip()
    return f"***.***.***-{s[-2:]}" if len(s) >= 2 else "—"


def _coerce_display(value: Any) -> str | None:
    """Valor cru -> texto display-safe (None se vazio)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if x is not None and str(x).strip()]
        return ", ".join(parts) or None
    text = str(value).strip()
    return text or None


def cadastral_card_to_section(card: dict, station_id: str) -> SectionDescriptor | None:
    """Projeção cadastral (build_cadastral_card_projection) -> seção Ficha.

    `card.campos` já vem com label pt-BR + valor (projetado pelo Contrato de
    Dados). Campos `novo` (fora do contrato) ganham badge. Proveniência = fonte
    externa (cyan). Retorna None quando não há dado (estação fica só com o agente).
    """
    if not card or not card.get("encontrado"):
        return None

    campos: list[FichaCampo] = []
    for c in card.get("campos") or []:
        valor = _coerce_display(c.get("valor"))
        if valor is None:
            continue
        campos.append(
            FichaCampo(
                label=c.get("label") or c.get("field_path") or "—",
                valor=valor,
                badge=None,  # 'novo' (🆕) é destaque de QA da tela cadastral, não do dossiê
                provenance=ProvenanceRef(origin="fonte"),
            )
        )

    if not campos:
        return None

    return SectionDescriptor(
        id=f"det-{station_id}",
        station_id=station_id,
        titulo="Identificação e cadastro",
        blocks=[
            FichaBlock(
                id=f"det-{station_id}-ficha",
                campos=campos,
                provenance=ProvenanceRef(origin="fonte"),
            )
        ],
        generates_dossier_section=True,
    )


def societario_to_section(payload: dict, station_id: str) -> SectionDescriptor | None:
    """Payload societário (build_societario_payload) -> Ficha + Tabela sócios +
    apontamentos de cruzamento. Espelha o painel determinístico do SocialContract.
    Proveniência = documento (verde). None quando não há contrato homologado/extraído.
    """
    if not payload or not payload.get("encontrado"):
        return None
    contrato = payload.get("contrato") or {}
    estrutura = payload.get("estrutura") or {}
    doc = ProvenanceRef(origin="documento")
    blocks: list[Block] = []

    ficha: list[FichaCampo] = []
    cap = _brl(contrato.get("capital_social"))
    if cap:
        ficha.append(FichaCampo(label="Capital social", valor=cap, provenance=doc))
    if contrato.get("data_constituicao"):
        ficha.append(
            FichaCampo(label="Constituição", valor=str(contrato["data_constituicao"]), provenance=doc)
        )
    idade = estrutura.get("idade_empresa_anos")
    if idade is not None:
        ficha.append(FichaCampo(label="Idade da empresa", valor=f"{idade} anos", provenance=doc))
    n_socios = estrutura.get("n_socios")
    if n_socios is not None:
        ficha.append(FichaCampo(label="Sócios", valor=str(n_socios), provenance=doc))
    controlador = estrutura.get("controlador")
    if isinstance(controlador, dict) and controlador.get("nome"):
        maj = " · majoritário" if controlador.get("controle_majoritario") else ""
        ficha.append(
            FichaCampo(
                label="Controlador",
                valor=f"{controlador['nome']} ({controlador.get('participacao_pct')}%{maj})",
                provenance=doc,
            )
        )
    if ficha:
        blocks.append(
            FichaBlock(id=f"det-{station_id}-contrato", titulo="Ficha do contrato", campos=ficha, provenance=doc)
        )

    socios = contrato.get("socios") or []
    if socios:
        blocks.append(
            TabelaBlock(
                id=f"det-{station_id}-socios",
                titulo="Quadro societário",
                provenance=doc,
                colunas=[
                    TabelaColuna(key="nome", label="Sócio"),
                    TabelaColuna(key="cpf", label="CPF"),
                    TabelaColuna(key="pct", label="Participação", align="right", formato="pct"),
                ],
                linhas=[
                    {
                        "nome": TabelaCelula(valor=s.get("nome") or "—"),
                        "cpf": TabelaCelula(valor=_cpf_mask(s.get("cpf_ultimos4"))),
                        "pct": TabelaCelula(valor=s.get("participacao_pct")),
                    }
                    for s in socios
                ],
            )
        )

    flagged = [c for c in (payload.get("cruzamentos") or []) if c.get("confere") is False]
    if flagged:
        blocks.append(
            ApontamentosBlock(
                id=f"det-{station_id}-cruz",
                titulo="Cruzamentos com o registro oficial",
                itens=[
                    Apontamento(
                        severidade="atencao",
                        titulo=c.get("detalhe") or c.get("campo") or "Divergência",
                        descricao=f"contrato: {c.get('contrato')} · oficial: {c.get('oficial')}",
                        provenance=doc,
                    )
                    for c in flagged
                ],
            )
        )

    if not blocks:
        return None
    return SectionDescriptor(
        id=f"det-{station_id}",
        station_id=station_id,
        titulo="Contrato social (fatos)",
        blocks=blocks,
        generates_dossier_section=True,
    )


def faturamento_to_section(payload: dict, station_id: str) -> SectionDescriptor | None:
    """Payload de faturamento (build_faturamento_payload) -> Ficha (agregados) +
    Tabela (série mensal). Números determinísticos; o julgamento é do agente.
    Proveniência = documento (verde). None quando não há série.
    """
    if not payload or not payload.get("encontrado"):
        return None
    analytics = payload.get("analytics") or {}
    ag = analytics.get("agregados") or {}
    serie = analytics.get("serie") or []
    tend = analytics.get("tendencia") or {}
    qual = analytics.get("qualidade") or {}
    doc = ProvenanceRef(origin="documento")
    blocks: list[Block] = []

    soma_nok = qual.get("soma_confere") is False
    ficha = [
        FichaCampo(label="Total", valor=_brl(ag.get("total")) or "—", provenance=doc),
        FichaCampo(label="Média mensal", valor=_brl(ag.get("media")) or "—", provenance=doc),
        FichaCampo(
            label="Tendência",
            valor=f"{tend.get('direcao') or '—'} ({tend.get('variacao_periodo_pct') or 0}%)",
            provenance=doc,
        ),
        FichaCampo(
            label="Meses",
            valor=str(ag.get("n_meses") or len(serie)),
            badge=None,
            nota="soma não confere" if soma_nok else None,
            provenance=doc,
        ),
    ]
    blocks.append(
        FichaBlock(id=f"det-{station_id}-agg", titulo="Números (fonte determinística)", campos=ficha, provenance=doc)
    )

    if serie:
        blocks.append(
            TabelaBlock(
                id=f"det-{station_id}-serie",
                titulo="Série mensal",
                provenance=doc,
                colunas=[
                    TabelaColuna(key="mes", label="Mês", formato="data"),
                    TabelaColuna(key="receita", label="Receita", align="right", formato="brl"),
                ],
                linhas=[
                    {
                        "mes": TabelaCelula(valor=r.get("mes")),
                        "receita": TabelaCelula(valor=r.get("receita_bruta")),
                    }
                    for r in serie
                ],
            )
        )

    return SectionDescriptor(
        id=f"det-{station_id}",
        station_id=station_id,
        titulo="Faturamento (números)",
        blocks=blocks,
        generates_dossier_section=True,
    )


__all__ = [
    "cadastral_card_to_section",
    "faturamento_to_section",
    "societario_to_section",
]

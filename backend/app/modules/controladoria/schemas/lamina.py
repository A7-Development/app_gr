"""Pydantic schemas -- Controladoria · Lamina mensal do FIDC.

Lamina (fact sheet) de 3 paginas A4 do FIDC, alimentada 100% pelas silver
alimentadas pela QiTech (CLAUDE.md §13.2.1):

    - wh_mec_evolucao_cotas    -- PL, quantidade, valor da cota, variacoes %.
    - wh_rentabilidade_fundo   -- retorno do CDI (indexador='CDI').
    - wh_estoque_recebivel     -- aging (a vencer/vencido), PDD, concentracao.
    - wh_saldo_conta_corrente  -- caixa do fundo.

Contrato: o backend devolve **arrays mensais deterministicos** (12 pontos, na
janela jun..mai do exemplo) lidos direto da silver; as transformacoes de
display (acumulado composto, % do CDI, razao de garantia) sao calculadas no
frontend a partir destes arrays -- todas puras e transparentes sobre dado
auditavel (mesma fonte da verdade da pagina Evolucao Patrimonial).

Numeros de classe seguem a heuristica `_classificar` (carteira_cliente_nome ->
sub/mez/sr), a mesma convencao validada no REALINVEST FIDC.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.controladoria.schemas.evolucao_patrimonial import ClasseCota


class ClasseSerie(BaseModel):
    """Serie mensal de uma classe de cota (12 pontos) + valores na competencia."""

    classe: ClasseCota
    label: str = Field(description="Rotulo pt-BR (Senior/Mezanino/Subordinada)")
    var_mensal: list[float | None] = Field(
        description="Retorno mensal % por mes (MEC variacao_mensal). null = mes "
        "parcial de constituicao da classe (sem mes anterior)."
    )
    patrimonio: list[float] = Field(description="PL R$ por mes (MEC, fim de mes)")
    quantidade: float = Field(description="Nro de cotas na competencia")
    valor_cota: float = Field(description="Valor da cota na competencia")
    variacao_total: float = Field(description="Rentab. desde o inicio % (MEC)")


class AgingSerie(BaseModel):
    """Composicao do ativo por mes (alinhada a `meses`). A vencer = total - vencido."""

    a_vencer: list[float] = Field(description="Direitos a vencer (R$, valor presente)")
    vencido: list[float] = Field(description="Direitos vencidos (R$, valor presente)")
    pdd: list[float] = Field(description="PDD (R$, soma valor_pdd)")
    caixa: list[float] = Field(description="Caixa (R$, saldo CC positivo)")


class ConcentracaoItem(BaseModel):
    """Posicao de concentracao -- nome NAO exposto (decisao do cliente)."""

    posicao: int = Field(description="Rank 1..10")
    financeiro: float = Field(description="Valor presente somado (R$)")


class ConcentracaoHistorico(BaseModel):
    """Historico de concentracao por mes (% sobre o total do estoque)."""

    cedente_maior: list[float]
    cedente_top10: list[float]
    sacado_maior: list[float]
    sacado_top10: list[float]


class Concentracao(BaseModel):
    cedentes: list[ConcentracaoItem]
    sacados: list[ConcentracaoItem]
    historico: ConcentracaoHistorico


class Proveniencia(BaseModel):
    fonte: str = Field(default="admin:qitech", description="source_type da origem")
    atualizado_em: datetime | None = Field(
        default=None, description="Maior source_updated_at observado (MEC)"
    )


class LaminaResponse(BaseModel):
    """Payload completo da lamina mensal do FIDC (3 paginas)."""

    fundo_id: str
    fundo_nome: str
    cnpj: str
    gestor_nome: str | None = None
    originador_nome: str | None = None
    competencia: str = Field(description="Competencia fechada (YYYY-MM)")
    competencia_label: str = Field(description="Rotulo (ex.: 'Maio / 2026')")
    posicao: date = Field(description="Ultimo dia util com dado na competencia")
    meses: list[str] = Field(description="12 rotulos de mes (ex.: 'jun/25')")
    cdi: list[float] = Field(description="Retorno mensal do CDI % por mes")
    classes: list[ClasseSerie]
    pl_total: float = Field(description="PL total na competencia (todas as classes)")
    aging: AgingSerie
    concentracao: Concentracao
    proveniencia: Proveniencia


class CompetenciaItem(BaseModel):
    competencia: str = Field(description="YYYY-MM")
    label: str = Field(description="Ex.: 'Maio / 2026'")
    posicao: date = Field(description="Ultimo dia util com dado no mes")


class CompetenciasResponse(BaseModel):
    """Lista de competencias FECHADAS disponiveis (desc). Nunca o mes corrente."""

    fundo_id: str
    fundo_nome: str
    competencias: list[CompetenciaItem]

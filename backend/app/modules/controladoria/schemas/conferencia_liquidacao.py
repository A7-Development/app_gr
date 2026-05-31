"""Pydantic schemas — Controladoria · Conferencia de liquidacao (entrada de caixa).

Reconcilia o CAIXA que entrou por liquidacao de recebiveis com as liquidacoes
que o originaram. Ao contrario da cessao (saida de caixa, TED exata por cedente),
a entrada e mais suja: cada `tipo_movimento` de wh_liquidacao_recebivel cai por
um canal diferente, com timing diferente.

Achado empirico (REALINVEST, 2026-05-30):
  - `LIQUIDAÇÃO NORMAL` (sacado paga boleto) -> bucket `LIQUIDADOS TOTAL - PROV`
    do demonstrativo de caixa, com FLOATING d+1 util. Casa ao centavo por lote.
    Em dias multi-lote, varios lotes (d+1, d+2) caem juntos — cada um casa com a
    NORMAL de um dia anterior distinto.
  - `BAIXA POR DEPOSITO SACADO` (sacado deposita direto) -> credito IMEDIATO no
    extrato bancario, AGREGADO (sem contraparte). Nao isolavel do resto dos
    creditos -> conferencia so como contexto agregado.
  - `DEPOSITO CEDENTE` + `RECOMPRA` (cedente honra coobrigacao / recompra) -> ~2%,
    quase sempre atrasados — sinal de inadimplencia, nao fluxo normal.

DIRECAO (point-in-time): a espinha e PRA TRAS — o caixa que CAIU hoje (PROV de
D0) tem origem na NORMAL de dias anteriores, e isso e 100% verificavel hoje. A
NORMAL de D0 so vira caixa no proximo dia util (floating) -> entra como PROJECAO,
nunca conferencia.

Silver-only (§13.2.1): le wh_liquidacao_recebivel + wh_movimento_caixa + wh_extrato_bancario.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# casa                    = lote PROV casa (ao centavo) com a Σ NORMAL de um dia anterior
# origem_nao_identificada = lote PROV sem dia-origem casavel nos ultimos dias -> ATENCAO
LoteStatus = Literal["casa", "origem_nao_identificada"]


class LiquidacaoPorTipo(BaseModel):
    """Liquidacoes do dia agregadas por tipo_movimento."""

    tipo_movimento: str
    n:              int
    valor_pago:     Decimal = Field(description="Σ valor_pago do tipo no dia")
    n_atrasados:    int = Field(description="Qtd paga apos o vencimento (data_posicao > data_vencimento)")


class LoteFloating(BaseModel):
    """Um lote do bucket PROV de D0, casado (ou nao) ao seu dia-origem NORMAL."""

    valor:          Decimal = Field(description="Valor do lote (1 linha LIQUIDADOS TOTAL - PROV)")
    dia_origem:     date | None = Field(
        default=None, description="Dia cuja Σ NORMAL valor_pago casa com este lote (None se nao achou)"
    )
    defasagem_dias: int | None = Field(
        default=None, description="D0 - dia_origem em dias corridos (1=d+1, 3=Sex->Seg, etc)"
    )
    normal_origem:  Decimal | None = Field(
        default=None, description="Σ NORMAL valor_pago do dia_origem (= valor quando casa)"
    )
    status:         LoteStatus


class ConferenciaLiquidacaoResponse(BaseModel):
    """Conferencia da entrada de caixa por liquidacao de um dia (D0).

    Espinha PRA TRAS (point-in-time, verificavel): o bucket PROV de D0 (caixa de
    floating que pingou hoje) decomposto em lotes, cada um casado por valor a um
    dia-origem `LIQUIDAÇÃO NORMAL` anterior. `floating_status='casa'` quando todos
    os lotes casam (residuo ~0).

    Perna IMEDIATA (SACADO): credito no mesmo dia, mas agregado no extrato e nao
    isolavel -> reportada como contexto, nunca como match estrito. `extrato_disponivel`
    distingue gap de sync (nao conferivel) de ausencia real.

    Perna FORWARD (projecao, NAO conferencia): `normal_hoje` = NORMAL de D0, que
    deve pingar como PROV no proximo dia util.
    """

    fundo_id:            str
    fundo_nome:          str
    data:                date = Field(description="D0 — dia das liquidacoes")
    data_anterior_util:  date | None = Field(
        default=None, description="Dia de pregao anterior a D0 (mais recente < D0 com liquidacao)"
    )

    # ── Liquidacoes registradas no dia ──────────────────────────────────────
    liquidacoes_por_tipo: list[LiquidacaoPorTipo] = Field(default_factory=list)
    total_liquidado:      Decimal = Field(description="Σ valor_pago de TODAS as liquidacoes de D0")

    # ── Perna FLOATING (backward, forte): PROV de D0 <- NORMAL de dias anteriores
    prov_total:       Decimal = Field(description="Σ bucket 'LIQUIDADOS TOTAL - PROV' de D0 (caixa que caiu hoje)")
    prov_lotes:       list[LoteFloating] = Field(default_factory=list)
    floating_residuo: Decimal = Field(description="prov_total - Σ lotes casados (0 = tudo rastreado)")
    floating_status:  Literal["casa", "diverge"] = Field(
        description="casa = todo o PROV de D0 rastreia a uma NORMAL anterior; diverge = sobra lote sem origem"
    )

    # ── Perna IMEDIATA (weak): SACADO de D0 -> credito no mesmo dia ──────────
    sacado_hoje:        Decimal = Field(description="Σ 'BAIXA POR DEPOSITO SACADO' de D0 (credito imediato esperado)")
    extrato_disponivel: bool = Field(description="False = extrato sem credito no dia (gap de sync) -> nao conferivel")
    extrato_credito_dia: Decimal | None = Field(
        default=None, description="Σ creditos (tipo='C') do extrato em D0 — contexto agregado (inclui nao-liquidacao)"
    )
    extrato_ultimo_lancamento: date | None = Field(
        default=None, description="Data do lancamento mais recente do extrato (frescor)"
    )

    # ── Honra do cedente (inadimplencia) ────────────────────────────────────
    honra_cedente_total:           Decimal = Field(description="Σ DEPOSITO CEDENTE + RECOMPRA de D0")
    honra_cedente_n:               int
    honra_cedente_todos_atrasados: bool = Field(
        description="True quando 100% da honra do cedente foi paga em atraso (sinal classico)"
    )

    # ── Projecao FORWARD (NAO e conferencia) ────────────────────────────────
    floating_hoje: Decimal = Field(
        description="Σ das liquidacoes que FLOATAM (NORMAL + CARTÓRIO + PARCIAL) de D0 — "
                    "devem pingar como PROV no proximo dia util (projecao, nao conferencia). "
                    "Achado: cartorio tambem floata (PROV(20/05) incluiu NORMAL+CARTÓRIO de 19/05)."
    )

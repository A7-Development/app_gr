"""Warehouse canonico do GR.

Espelho normalizado das views/tabelas do ANALYTICS + Bitfin com metadata de
proveniencia (mixin Auditable). Populado pelo ETL em `app/scheduler/jobs/`.

Convencoes:
- Prefixo `wh_` em todas as tabelas.
- `tenant_id` NOT NULL em toda tabela de fato.
- Campos em snake_case (source PascalCase do Bitfin preservado em `source_id`).
- Valores monetarios em `Numeric(18, 4)` (suficiente para FIDCs).
- Datetimes sempre com timezone.

Camadas (CLAUDE.md secao 13.2):
- **Raw (bronze):** `wh_<vendor>_raw_*` — payload JSONB cru, especifico por
  vendor. Imutavel. Sem mixin `Auditable` (a raw e a fonte).
- **Canonico (silver):** `wh_<entidade>` (sem vendor no nome) — schema
  estavel, populado por mapper a partir da raw. Carrega `Auditable`.
"""

from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.dim import DimDreClassificacao, DimMes
from app.warehouse.dre import DreMensal
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.movimento_aberto import MovimentoAberto
from app.warehouse.movimento_caixa import MovimentoCaixa
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.operacao_remessa import OperacaoRemessa
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_snapshot import TituloSnapshot

__all__ = [
    "AquisicaoRecebivel",
    "CprMovimento",
    "DimDreClassificacao",
    "DimMes",
    "DreMensal",
    "EstoqueRecebivel",
    "LiquidacaoRecebivel",
    "MecEvolucaoCotas",
    "MovimentoAberto",
    "MovimentoCaixa",
    "Operacao",
    "OperacaoItem",
    "OperacaoRemessa",
    "PosicaoCompromissada",
    "PosicaoCotaFundo",
    "PosicaoOutrosAtivos",
    "PosicaoRendaFixa",
    "QiTechRawRelatorio",
    "RentabilidadeFundo",
    "SaldoContaCorrente",
    "SaldoTesouraria",
    "Titulo",
    "TituloSnapshot",
]

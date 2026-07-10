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
from app.warehouse.bdc_raw_consulta import BdcRawConsulta
from app.warehouse.bitfin_entidade import WhBitfinEntidade
from app.warehouse.bitfin_raw_debenture import BitfinRawDebenture
from app.warehouse.bitfin_receita_stream import WhBitfinReceitaStream
from app.warehouse.bitfin_tarifa_catalogo import WhBitfinTarifaCatalogo
from app.warehouse.boleto import Boleto
from app.warehouse.boleto_evento import BoletoEvento
from app.warehouse.boleto_vigente import BoletoVigente
from app.warehouse.caixa_snapshot import CaixaSnapshot
from app.warehouse.cnab_raw_arquivo import CnabRawArquivo
from app.warehouse.cnab_raw_ocorrencia import CnabRawOcorrencia
from app.warehouse.cobranca_sync_run import CobrancaSyncRun
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.dia_util_qitech import DiaUtilQitech
from app.warehouse.dim import DimMes
from app.warehouse.dim_dia_util import DimDiaUtil
from app.warehouse.entidade import (
    WhEntidade,
    WhEntidadeFonte,
    WhEntidadePapel,
    WhGrupoEconomico,
    WhGrupoEconomicoMembro,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.fiscal_cte import Cte, CteNfe, CteRawDocumento
from app.warehouse.fiscal_nfe import Nfe, NfeDuplicata, NfeRawDocumento
from app.warehouse.infosimples_raw_consulta import InfosimplesRawConsulta
from app.warehouse.liquidacao import Liquidacao
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.movimento_aberto import MovimentoAberto
from app.warehouse.movimento_caixa import MovimentoCaixa
from app.warehouse.operacao import Operacao, OperacaoItem
from app.warehouse.operacao_remessa import OperacaoRemessa
from app.warehouse.pj_cadastro import PjCadastro
from app.warehouse.pj_evolucao import PjEvolucao, PjEvolucaoMensal
from app.warehouse.pj_grupo_indicador import PjGrupoIndicador
from app.warehouse.pj_kyc import PjKyc, PjKycOcorrencia
from app.warehouse.pj_processo import (
    PjProcesso,
    PjProcessoAndamento,
    PjProcessoParte,
    PjProcessoResumo,
)
from app.warehouse.pj_vinculo import PjVinculo
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_debenture import PosicaoDebentureDia
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_papel import (
    WhPagamentoPracaMensal,
    WhPosicaoCedente,
    WhPosicaoCedenteProduto,
    WhPosicaoSacado,
    WhPosicaoSacadoCedente,
)
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.protesto import WhProtestoConsulta, WhProtestoTitulo
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio
from app.warehouse.receita_acruo_dia import ReceitaAcruoDia
from app.warehouse.receita_caixa import ReceitaCaixa
from app.warehouse.receita_operacional import ReceitaOperacional
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente
from app.warehouse.saldo_tesouraria import SaldoTesouraria
from app.warehouse.serasa_liminar_estado import SerasaLiminarEstado
from app.warehouse.serasa_pj_atraso_medio_mensal import (
    SerasaPjAtrasoMedioMensal,
)
from app.warehouse.serasa_pj_business_reference import (
    SerasaPjBusinessReference,
)
from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
from app.warehouse.serasa_pj_endereco import SerasaPjEndereco
from app.warehouse.serasa_pj_inquiry_anterior import SerasaPjInquiryAnterior
from app.warehouse.serasa_pj_inquiry_mensal import SerasaPjInquiryMensal
from app.warehouse.serasa_pj_liminar_feature import SerasaPjLiminarFeature
from app.warehouse.serasa_pj_pagamento_bucket import SerasaPjPagamentoBucket
from app.warehouse.serasa_pj_pagamento_evolucao_mensal import (
    SerasaPjPagamentoEvolucaoMensal,
)
from app.warehouse.serasa_pj_participacao import SerasaPjParticipacao
from app.warehouse.serasa_pj_payment_comparative import (
    SerasaPjPaymentComparative,
)
from app.warehouse.serasa_pj_predecessor import SerasaPjPredecessor
from app.warehouse.serasa_pj_raw_relatorio import SerasaPjRawRelatorio
from app.warehouse.serasa_pj_restricao import SerasaPjRestricao
from app.warehouse.serasa_pj_restricao_summary import SerasaPjRestricaoSummary
from app.warehouse.serasa_pj_socio import SerasaPjSocio
from app.warehouse.serpro_raw_nfe import SerproRawNfe
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_snapshot import TituloSnapshot

__all__ = [
    "AquisicaoRecebivel",
    "BdcRawConsulta",
    "BitfinRawDebenture",
    "Boleto",
    "BoletoEvento",
    "BoletoVigente",
    "CaixaSnapshot",
    "CnabRawArquivo",
    "CnabRawOcorrencia",
    "CobrancaSyncRun",
    "CprMovimento",
    "Cte",
    "CteNfe",
    "CteRawDocumento",
    "DiaUtilQitech",
    "DimDiaUtil",
    "DimMes",
    "EstoqueRecebivel",
    "InfosimplesRawConsulta",
    "Liquidacao",
    "LiquidacaoRecebivel",
    "MecEvolucaoCotas",
    "MovimentoAberto",
    "MovimentoCaixa",
    "Nfe",
    "NfeDuplicata",
    "NfeRawDocumento",
    "Operacao",
    "OperacaoItem",
    "OperacaoRemessa",
    "PjCadastro",
    "PjEvolucao",
    "PjEvolucaoMensal",
    "PjGrupoIndicador",
    "PjKyc",
    "PjKycOcorrencia",
    "PjProcesso",
    "PjProcessoAndamento",
    "PjProcessoParte",
    "PjProcessoResumo",
    "PjVinculo",
    "PosicaoCompromissada",
    "PosicaoCotaFundo",
    "PosicaoDebentureDia",
    "PosicaoOutrosAtivos",
    "PosicaoRendaFixa",
    "QiTechRawRelatorio",
    "ReceitaAcruoDia",
    "ReceitaCaixa",
    "ReceitaOperacional",
    "RentabilidadeFundo",
    "SaldoContaCorrente",
    "SaldoTesouraria",
    "SerasaLiminarEstado",
    "SerasaPjAtrasoMedioMensal",
    "SerasaPjBusinessReference",
    "SerasaPjConsulta",
    "SerasaPjEndereco",
    "SerasaPjInquiryAnterior",
    "SerasaPjInquiryMensal",
    "SerasaPjLiminarFeature",
    "SerasaPjPagamentoBucket",
    "SerasaPjPagamentoEvolucaoMensal",
    "SerasaPjParticipacao",
    "SerasaPjPaymentComparative",
    "SerasaPjPredecessor",
    "SerasaPjRawRelatorio",
    "SerasaPjRestricao",
    "SerasaPjRestricaoSummary",
    "SerasaPjSocio",
    "SerproRawNfe",
    "Titulo",
    "TituloSnapshot",
    "WhBitfinEntidade",
    "WhBitfinReceitaStream",
    "WhBitfinTarifaCatalogo",
    "WhEntidade",
    "WhEntidadeFonte",
    "WhEntidadePapel",
    "WhGrupoEconomico",
    "WhGrupoEconomicoMembro",
    "WhPagamentoPracaMensal",
    "WhPosicaoCedente",
    "WhPosicaoCedenteProduto",
    "WhPosicaoSacado",
    "WhPosicaoSacadoCedente",
    "WhProtestoConsulta",
    "WhProtestoTitulo",
]

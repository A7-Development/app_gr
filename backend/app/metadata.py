"""Central metadata imports — imported by Alembic env.py to discover all models.

All SQLAlchemy models must be imported here (directly or transitively) so Alembic
can auto-detect them during migration generation.
"""

# Core base
# Workflow engine (shared kernel — modulo credito o consome, futuros modulos
# como Risco e Laboratorio tambem virao a usar).
from app.agentic.workflows.models import (  # noqa: F401
    WorkflowDefinition,
    WorkflowDefinitionActive,
    WorkflowNotification,
    WorkflowRun,
    WorkflowRunStep,
)
from app.core.database import Base
from app.modules.bi.models.user_fund_favorite import UserFundFavorite  # noqa: F401

# Cadastros (UA primaria do tenant)
from app.modules.cadastros.models.unidade_administrativa import (  # noqa: F401
    UnidadeAdministrativa,
)

# Modulo credito — dossie inteligente + workflow + agentes especialistas (2026-04-30)
from app.modules.credito.models import (  # noqa: F401
    CreditAnalysisItem,
    CreditDocumentTemplate,
    CreditDossier,
    CreditDossierAnalysis,
    CreditDossierBureauQuery,
    CreditDossierCheck,
    CreditDossierCompany,
    CreditDossierDocument,
    CreditDossierFinancial,
    CreditDossierOpinion,
    CreditDossierPerson,
    CreditDossierPleito,
    CreditDossierRedFlag,
)
from app.modules.integracoes.models.agent_credential import AgentCredential  # noqa: F401
from app.modules.integracoes.models.file_landing import FileLanding  # noqa: F401
from app.modules.integracoes.models.qitech_report_job import QitechReportJob  # noqa: F401
from app.modules.integracoes.models.qitech_ua_classe import QiTechUaClasse  # noqa: F401
from app.modules.integracoes.models.tenant_source_config import TenantSourceConfig  # noqa: F401

# Modulo risco — contrato de liquidacao + espinha de deteccao (2026-07-08)
from app.modules.risco.models import (  # noqa: F401
    CedenteRiscoComposicao,
    CedenteRiscoSnapshot,
    CuradoriaTag,
    DeteccaoModelo,
    DeteccaoModeloAtivo,
    DeteccaoModeloVersao,
    DeteccaoScore,
    ProdutoContratoLiquidacao,
)

# Shared kernel
from app.shared.ai.models import (  # noqa: F401
    AgentConfig,
    AIConversation,
    AIConversationSummary,
    AICreditBalance,
    AIMessage,
    AIPrompt,
    AIPromptActive,
    AIProviderCredential,
    AIUsageEvent,
    TenantAISubscription,
    UserAIPermission,
)
from app.shared.audit_log.decision_log import DecisionLog  # noqa: F401
from app.shared.audit_log.premise_set import PremiseSet  # noqa: F401
from app.shared.catalog.source_catalog import SourceCatalog  # noqa: F401
from app.shared.data_providers.models import (  # noqa: F401
    DataProvider,
    DataProviderCatalogSyncRun,
    DataProviderCredential,
    DataProviderDataset,
    DataProviderDatasetPriceHistory,
)
from app.shared.identity.subscription import TenantModuleSubscription  # noqa: F401
from app.shared.identity.tenant import Tenant  # noqa: F401
from app.shared.identity.user import User  # noqa: F401
from app.shared.identity.user_permission import UserModulePermission  # noqa: F401
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel  # noqa: F401
from app.warehouse.bdc_raw_consulta import BdcRawConsulta  # noqa: F401
from app.warehouse.conta_bancaria import ContaBancariaEntidade  # noqa: F401
from app.warehouse.cpr_movimento import CprMovimento  # noqa: F401

# Warehouse (populado pelo ETL)
from app.warehouse.dim import DimMes  # noqa: F401
from app.warehouse.estoque_recebivel import EstoqueRecebivel  # noqa: F401
from app.warehouse.extrato_bancario import ExtratoBancario  # noqa: F401
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel  # noqa: F401
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas  # noqa: F401
from app.warehouse.movimento_aberto import MovimentoAberto  # noqa: F401
from app.warehouse.movimento_caixa import MovimentoCaixa  # noqa: F401
from app.warehouse.operacao import Operacao, OperacaoItem  # noqa: F401
from app.warehouse.operacao_remessa import OperacaoRemessa  # noqa: F401
from app.warehouse.posicao_compromissada import PosicaoCompromissada  # noqa: F401
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo  # noqa: F401
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos  # noqa: F401
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa  # noqa: F401
from app.warehouse.qitech_raw_bank_account_balance import (  # noqa: F401
    QiTechRawBankAccountBalance,
)
from app.warehouse.qitech_raw_bank_account_statement import (  # noqa: F401
    QiTechRawBankAccountStatement,
)
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio  # noqa: F401
from app.warehouse.rentabilidade_fundo import RentabilidadeFundo  # noqa: F401
from app.warehouse.saldo_bancario_diario import SaldoBancarioDiario  # noqa: F401
from app.warehouse.saldo_conta_corrente import SaldoContaCorrente  # noqa: F401
from app.warehouse.saldo_tesouraria import SaldoTesouraria  # noqa: F401
from app.warehouse.titulo import Titulo  # noqa: F401
from app.warehouse.titulo_snapshot import TituloSnapshot  # noqa: F401

target_metadata = Base.metadata

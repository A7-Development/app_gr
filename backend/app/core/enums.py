"""Central enums used across modules."""

import enum


class Module(enum.StrEnum):
    """The 9 official modules of the GR system.

    Adding a new value requires explicit authorization + update of CLAUDE.md section 11.1.
    """

    BI = "bi"
    CADASTROS = "cadastros"
    OPERACOES = "operacoes"
    CREDITO = "credito"
    CONTROLADORIA = "controladoria"
    RISCO = "risco"
    INTEGRACOES = "integracoes"
    LABORATORIO = "laboratorio"
    ADMIN = "admin"


class Permission(enum.StrEnum):
    """Permission scale (ordered by strength)."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

    def satisfies(self, required: "Permission") -> bool:
        """Whether this permission meets the required level."""
        order = {
            Permission.NONE: 0,
            Permission.READ: 1,
            Permission.WRITE: 2,
            Permission.ADMIN: 3,
        }
        return order[self] >= order[required]


class TenantStatus(enum.StrEnum):
    """Lifecycle of a tenant."""

    TRIAL = "trial"          # tenant em avaliacao com prazo
    ACTIVE = "active"        # contratado, plenamente operacional
    SUSPENDED = "suspended"  # bloqueado por inadimplencia/abuso (login negado)
    CANCELLED = "cancelled"  # encerrado (login negado, dado preservado p/ auditoria)


class TenantRole(enum.StrEnum):
    """Role of a user inside a tenant.

    UX layer above the granular `user_module_permission` matrix. Assigning
    or changing a role (re)populates the matrix via
    `app.shared.identity.role_defaults.apply_role_defaults`.

    Owner has full power inside the tenant (gere users, perms, subscriptions).
    Member is the typical operational user. Viewer is read-only.
    """

    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class AICapability(enum.StrEnum):
    """User permission scale for the AI capability (parallel to Permission).

    AI is a transversal capability, not a module — it lives outside the closed
    `Module` enum (CLAUDE.md sec 11.1). Tenant-level entitlement is in
    `tenant_ai_subscription`; user-level in `user_ai_permission`.
    """

    NONE = "none"
    READ = "read"     # can chat / receive insights
    WRITE = "write"   # can save / share conversations
    ADMIN = "admin"   # can manage tier / topup of own tenant

    def satisfies(self, required: "AICapability") -> bool:
        order = {
            AICapability.NONE: 0,
            AICapability.READ: 1,
            AICapability.WRITE: 2,
            AICapability.ADMIN: 3,
        }
        return order[self] >= order[required]


class AIProvider(enum.StrEnum):
    """Supported LLM providers (centralized credentials)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AIUsageStatus(enum.StrEnum):
    """Final status of an AI usage event."""

    OK = "ok"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    OVER_BUDGET = "over_budget"
    INJECTION_BLOCKED = "injection_blocked"


class TrustLevel(enum.StrEnum):
    """Trust level for data ingested into the warehouse."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SourceType(enum.StrEnum):
    """Type of data source. Used in proveniencia metadata.

    Adding a value requires updating the adapter and `source_catalog`.
    """

    ERP_BITFIN = "erp:bitfin"
    ADMIN_QITECH = "admin:qitech"
    BUREAU_SERASA_PJ = "bureau:serasa_pj"
    BUREAU_SERASA_PF = "bureau:serasa_pf"
    BUREAU_SCR_BACEN = "bureau:scr_bacen"
    # BigDataCorp (cadastral PJ/PF, QSA, etc.). native_enum=False (VARCHAR) ->
    # adicionar valor nao exige migration de tipo.
    BUREAU_BDC = "bureau:bdc"
    DOCUMENT_NFE = "document:nfe"
    # Cobranca (boletos / CNAB). COBRANCA (generico) e a fonte de TRANSPORTE:
    # a "inbox" de arquivos de retorno -- uma pasta com retornos de varios
    # bancos misturados (config de tenant_source_config). Os COBRANCA_<BANCO>
    # sao a PROVENIENCIA de cada boleto em wh_boleto, detectada por arquivo
    # pelo header CNAB (codigo do banco). A conciliacao le o canonico
    # `wh_boleto`, nunca o raw CNAB (CLAUDE.md sec 13).
    COBRANCA = "cobranca"
    COBRANCA_BRADESCO = "cobranca:bradesco"
    COBRANCA_ITAU = "cobranca:itau"
    # BMP (codigo 274) e Vortx (codigo 310) -- identidades reais detectadas pelo
    # header CNAB (antes rotuladas erroneamente como "grafeno"). native_enum=
    # False (VARCHAR) -> adicionar valor nao exige migration.
    COBRANCA_BMP = "cobranca:bmp"
    COBRANCA_VORTX = "cobranca:vortx"
    SELF_DECLARED = "self_declared"
    PEER_DECLARED = "peer_declared"
    INTERNAL_NOTE = "internal_note"
    DERIVED = "derived"


class Environment(enum.StrEnum):
    """External-source environment (sandbox vs production).

    Stored per-row in `tenant_source_config` so the same tenant can coexist
    with a sandbox and a production config for the same source_type.
    """

    SANDBOX = "sandbox"
    PRODUCTION = "production"


class PapelCota(enum.StrEnum):
    """Role of a FIDC cota class within a fund (QiTech `clienteId` catalog).

    Pre-registered per UA in `qitech_ua_classe` and used by the completeness
    assessor to know which `clienteId`s a `market/*` payload must carry. A
    multiclasse FIDC has SUBORDINADA + MEZANINO + SENIOR; a single-class fund
    has only UNICA. See CLAUDE.md sec 13/14 (proveniencia) and the QiTech
    adapter `completeness.py`.
    """

    SUBORDINADA = "SUBORDINADA"
    MEZANINO = "MEZANINO"
    SENIOR = "SENIOR"
    UNICA = "UNICA"


# ─── Workflow engine (shared kernel) ───────────────────────────────────────
# These enums live in `core` because they are cross-cutting (used by the
# workflow engine in app/shared/workflow/, the credito module that
# instantiates runs, and any future module that consumes workflows — risco,
# laboratorio).


class WorkflowStatus(enum.StrEnum):
    """Lifecycle of a `workflow_definition` row."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkflowRunStatus(enum.StrEnum):
    """Status of an execution of a workflow (one row in `workflow_run`)."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"           # waiting for human_review or async input
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeRunStatus(enum.StrEnum):
    """Status of an individual node within a run (`workflow_node_run`)."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"   # human_review pending
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ─── Modulo credito ────────────────────────────────────────────────────────
# The credito module wraps a workflow run with domain semantics. It owns
# its own enums for dossie-specific concerns (lifecycle, document types,
# section identifiers, etc).


class DossierStatus(enum.StrEnum):
    """Lifecycle of a credit dossier — projecao do workflow run em termos de dominio.

    The mapping is:
        DRAFT       -> workflow not started yet
        COLLECTING  -> bureau queries running, docs being uploaded
        ANALYZING   -> specialist agents executing
        REVIEW      -> workflow paused on human_review
        FINALIZED   -> opinion signed, output PDF generated
        CANCELLED   -> dossier or workflow cancelled by user
    """

    DRAFT = "draft"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    REVIEW = "review"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class DocumentType(enum.StrEnum):
    """Types of documents that can be attached to a dossie.

    Each type may have a corresponding `extract.<type>` prompt in the
    `ai_prompt` table that the document_extractor agent uses to structure
    the data.
    """

    DRE = "dre"
    BALANCE_SHEET = "balance_sheet"
    REVENUE_REPORT = "revenue_report"
    INDEBTEDNESS = "indebtedness"
    SCR = "scr"                      # arquivo SCR Bacen (upload manual)
    INCOME_TAX_PF = "income_tax_pf"  # IR pessoa fisica
    CNH = "cnh"
    RG = "rg"
    SOCIAL_CONTRACT = "social_contract"
    COMMERCIAL_VISIT = "commercial_visit"
    PHOTO = "photo"                  # fotos das instalacoes
    ABC_CURVE = "abc_curve"          # curva ABC de clientes
    PLEA_SOURCE = "plea_source"      # fonte original do pleito (email, print)
    OTHER = "other"


class CompanyRole(enum.StrEnum):
    """Role of a company within an economic group attached to a dossie."""

    TARGET = "target"
    GROUP_MEMBER = "group_member"


class PersonRole(enum.StrEnum):
    """Role of a natural person related to the analyzed company."""

    PARTNER = "partner"                # socio
    REPRESENTATIVE = "representative"  # representante legal
    GUARANTOR = "guarantor"            # avalista
    RELATED = "related"                # parente, procurador, etc.


class BureauSource(enum.StrEnum):
    """Bureaus / external sources queried during the dossie pipeline."""

    SERASA_PJ = "serasa_pj"
    SERASA_PF = "serasa_pf"
    BIGDATACORP = "bigdatacorp"
    INFOSIMPLES = "infosimples"
    SCR_BACEN = "scr_bacen"            # manual upload (no API)
    RECEITA_FEDERAL = "receita_federal"
    JUNTA_COMERCIAL = "junta_comercial"


class BureauQueryStatus(enum.StrEnum):
    """Status of a single bureau query against an entity (cnpj or cpf)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class CheckSeverity(enum.StrEnum):
    """Severity of a checklist item from `credit_analysis_item`."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


class CheckStatus(enum.StrEnum):
    """Outcome of a checklist item evaluation (by AI or analyst)."""

    PENDING = "pending"
    OK = "ok"
    ALERT = "alert"
    CRITICAL = "critical"
    NOT_APPLICABLE = "not_applicable"


class OpinionRecommendation(enum.StrEnum):
    """Final recommendation in a credit opinion."""

    APPROVE = "approve"
    DENY = "deny"
    CONDITIONAL = "conditional"


class TipoPessoa(enum.StrEnum):
    """Legal person type of a canonical entity (`wh_entidade`)."""

    PJ = "pj"
    PF = "pf"


class EntidadePapel(enum.StrEnum):
    """Role an entity plays in the operation (party model, `wh_entidade_papel`).

    The same CNPJ/CPF can hold N roles simultaneously (cedente that is also
    sacado of other cedentes, avalista, socio...). Roles are facts, not
    entity subtypes — risk views consolidate across roles.
    """

    CEDENTE = "cedente"
    SACADO = "sacado"
    AVALISTA = "avalista"
    SOCIO = "socio"
    FORNECEDOR = "fornecedor"

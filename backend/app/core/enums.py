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
    BUREAU_SERASA_REFINHO = "bureau:serasa_refinho"
    BUREAU_SERASA_PFIN = "bureau:serasa_pfin"
    BUREAU_SCR_BACEN = "bureau:scr_bacen"
    DOCUMENT_NFE = "document:nfe"
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

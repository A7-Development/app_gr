"""Central enums used across modules."""

import enum


class Module(enum.StrEnum):
    """The 8 official modules of the GR system.

    Adding a new value requires explicit authorization + update of CLAUDE.md section 11.1.
    """

    BI = "bi"
    CADASTROS = "cadastros"
    OPERACOES = "operacoes"
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

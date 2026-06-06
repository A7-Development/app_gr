"""data contracts fase 1 — dataset_contract + _active + dataset_field + seed CAD-PJ

Cria as 3 tabelas do Contrato de Dados (ver docs/contratos-de-dados-fontes-externas.md)
e semeia o contrato v1 do BDC/empresas/basic_data (public_code CAD-PJ) com os
campos reais já conhecidos + roteamento para as 5 superfícies.

DDL idempotente (CREATE ... IF NOT EXISTS) e seed guardado — seguro aplicar
manual via runner (head do alembic divergente em prod) e depois via alembic.

Revision ID: f1a2c3d4e5b6
Revises: e1f4a9c7b2d8
Create Date: 2026-06-06
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2c3d4e5b6"
down_revision: str | None = "e1f4a9c7b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ─── DDL (idempotente) ───────────────────────────────────────────────────────

DDL_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS dataset_contract (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        provider varchar(64) NOT NULL,
        api_endpoint varchar(64) NOT NULL,
        dataset_code varchar(128) NOT NULL,
        public_code varchar(64),
        version integer NOT NULL DEFAULT 1,
        status varchar(16) NOT NULL DEFAULT 'draft',
        owner varchar(128),
        description text,
        tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_dataset_contract_identity_version
            UNIQUE (provider, api_endpoint, dataset_code, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_dataset_contract_identity "
    "ON dataset_contract (provider, api_endpoint, dataset_code)",
    """
    CREATE TABLE IF NOT EXISTS dataset_contract_active (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        provider varchar(64) NOT NULL,
        api_endpoint varchar(64) NOT NULL,
        dataset_code varchar(128) NOT NULL,
        tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
        active_contract_id uuid NOT NULL REFERENCES dataset_contract(id) ON DELETE CASCADE,
        changed_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_contract_active_global "
    "ON dataset_contract_active (provider, api_endpoint, dataset_code) "
    "WHERE tenant_id IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_contract_active_tenant "
    "ON dataset_contract_active (provider, api_endpoint, dataset_code, tenant_id) "
    "WHERE tenant_id IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS dataset_field (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        contract_id uuid NOT NULL REFERENCES dataset_contract(id) ON DELETE CASCADE,
        field_path varchar(255) NOT NULL,
        public_label varchar(255),
        description text,
        semantic_type varchar(24) NOT NULL DEFAULT 'text',
        categoria_ui varchar(64),
        sensibilidade varchar(16) NOT NULL DEFAULT 'publico',
        eh_fato varchar(24) NOT NULL DEFAULT 'contexto',
        to_silver boolean NOT NULL DEFAULT false,
        silver_target varchar(128),
        on_screen boolean NOT NULL DEFAULT true,
        screen_order integer,
        to_tool boolean NOT NULL DEFAULT false,
        to_agent boolean NOT NULL DEFAULT false,
        to_check boolean NOT NULL DEFAULT false,
        status varchar(24) NOT NULL DEFAULT 'curado',
        classified_by varchar(128),
        classified_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_dataset_field_path UNIQUE (contract_id, field_path)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_dataset_field_contract_id "
    "ON dataset_field (contract_id)",
]


# ─── Seed: contrato CAD-PJ v1 (BDC / empresas / basic_data) ──────────────────

CONTRACT_ID = "f1a2c3d4-e5b6-4a00-8000-000000000001"
ACTIVE_ID = "f1a2c3d4-e5b6-4a00-8000-0000000000a1"
PROVIDER = "bdc"
API_ENDPOINT = "empresas"
DATASET_CODE = "basic_data"
PUBLIC_CODE = "CAD-PJ"

# (field_path, label, description, semantic_type, categoria, sensibilidade,
#  eh_fato, to_silver, silver_target, screen_order, to_tool, to_agent, to_check)
FIELDS: list[tuple] = [
    ("TaxIdNumber", "CNPJ", "CNPJ da empresa-alvo.", "cnpj", "identidade", "publico", "fato_deterministico", False, None, 1, True, True, False),
    ("OfficialName", "Razão social", "Razão social oficial na Receita.", "text", "identidade", "publico", "fato_deterministico", False, None, 2, True, True, False),
    ("TradeName", "Nome fantasia", "Nome fantasia (pode ser vazio).", "text", "identidade", "publico", "contexto", False, None, 3, True, True, False),
    ("TaxIdStatus", "Situação cadastral", "ATIVA / BAIXADA / INAPTA / SUSPENSA.", "enum", "situação", "publico", "fato_deterministico", True, "tax_status", 4, True, True, True),
    ("TaxIdStatusDate", "Data da situação", "Data da última atualização da situação.", "date", "situação", "publico", "contexto", False, None, 5, False, True, False),
    ("TaxIdStatusRegistrationDate", "Situação desde", "Desde quando está nesta situação.", "date", "situação", "publico", "contexto", False, None, 6, False, False, False),
    ("FoundedDate", "Data de fundação", "Data de constituição na Receita.", "date", "situação", "publico", "fato_deterministico", True, "founding_date", 7, True, True, True),
    ("Age", "Idade (anos)", "Anos de atividade desde a fundação.", "number", "situação", "publico", "fato_deterministico", False, None, 8, True, True, False),
    ("LegalNature.Activity", "Natureza jurídica", "Ex.: SOCIEDADE EMPRESÁRIA LIMITADA.", "text", "identidade", "publico", "contexto", False, None, 9, True, True, False),
    ("LegalNature.Code", "Cód. natureza jurídica", "Código da natureza jurídica.", "text", "identidade", "publico", "contexto", False, None, 10, False, False, False),
    ("TaxRegime", "Regime tributário", "Ex.: LUCRO REAL / SIMPLES.", "text", "situação", "publico", "contexto", False, None, 11, True, True, False),
    ("TaxRegimes.Simples", "Optante pelo Simples", "Optante pelo Simples Nacional?", "bool", "situação", "publico", "fato_deterministico", False, None, 12, True, True, False),
    ("Activities[].Code", "CNAE (código)", "Código CNAE (principal e secundárias).", "cnae", "atividade", "publico", "fato_deterministico", True, "cnaes", 13, True, True, True),
    ("Activities[].Activity", "CNAE (descrição)", "Descrição do CNAE.", "text", "atividade", "publico", "contexto", False, None, 14, True, True, False),
    ("Activities[].IsMain", "CNAE principal?", "Marca o CNAE principal.", "bool", "atividade", "publico", "fato_deterministico", False, None, 15, True, True, False),
    ("AdditionalOutputData.CapitalRS", "Capital social", "Capital social em R$.", "money", "capital", "publico", "fato_deterministico", True, "capital_social", 16, True, True, False),
    ("AdditionalOutputData.Capital", "Capital (por extenso)", "Capital social por extenso.", "text", "capital", "publico", "contexto", False, None, 17, False, False, False),
    ("HeadquarterState", "UF da matriz", "Unidade federativa da matriz.", "text", "identidade", "publico", "contexto", False, None, 18, True, True, False),
    ("IsHeadquarter", "É matriz?", "Estabelecimento é a matriz?", "bool", "identidade", "publico", "fato_deterministico", False, None, 19, True, True, False),
    ("IsConglomerate", "Conglomerado?", "Indício de grupo econômico (gatilho p/ QSA/vínculos).", "bool", "identidade", "publico", "contexto", False, None, 20, True, True, False),
    ("HistoricalData.HasChangedTaxRegime", "Mudou regime?", "Já mudou de regime tributário (sinal de veracidade).", "bool", "histórico", "publico", "fato_deterministico", False, None, 21, True, True, False),
    ("HistoricalData.HasChangedTradeName", "Mudou nome fantasia?", "Já mudou o nome fantasia.", "bool", "histórico", "publico", "contexto", False, None, 22, False, True, False),
    ("CompanyType_ReceitaFederal", "Tipo (Receita)", "Classificação do tipo de empresa na Receita.", "text", "identidade", "publico", "contexto", False, None, 23, False, False, False),
]


def _seed(bind) -> None:
    exists = bind.execute(
        sa.text("SELECT 1 FROM dataset_contract WHERE id = CAST(:i AS uuid)").bindparams(
            i=CONTRACT_ID
        )
    ).first()
    if not exists:
        bind.execute(
            sa.text(
                "INSERT INTO dataset_contract "
                "(id, provider, api_endpoint, dataset_code, public_code, version, "
                " status, owner, description) "
                "VALUES (CAST(:id AS uuid), :p, :a, :d, :pc, 1, 'active', 'A7', :desc)"
            ).bindparams(
                id=CONTRACT_ID, p=PROVIDER, a=API_ENDPOINT, d=DATASET_CODE,
                pc=PUBLIC_CODE,
                desc="Contrato dos dados cadastrais PJ (BDC basic_data via /empresas).",
            )
        )
        for f in FIELDS:
            bind.execute(
                sa.text(
                    "INSERT INTO dataset_field "
                    "(id, contract_id, field_path, public_label, description, "
                    " semantic_type, categoria_ui, sensibilidade, eh_fato, "
                    " to_silver, silver_target, on_screen, screen_order, "
                    " to_tool, to_agent, to_check, status) "
                    "VALUES (gen_random_uuid(), CAST(:cid AS uuid), :fp, :lbl, :desc, "
                    " :st, :cat, :sens, :fato, :silver, :starget, true, :ord, "
                    " :tool, :agent, :chk, 'curado')"
                ).bindparams(
                    cid=CONTRACT_ID, fp=f[0], lbl=f[1], desc=f[2], st=f[3],
                    cat=f[4], sens=f[5], fato=f[6], silver=f[7], starget=f[8],
                    ord=f[9], tool=f[10], agent=f[11], chk=f[12],
                )
            )
    bind.execute(
        sa.text(
            "INSERT INTO dataset_contract_active "
            "(id, provider, api_endpoint, dataset_code, tenant_id, active_contract_id) "
            "SELECT CAST(:aid AS uuid), :p, :a, :d, NULL, CAST(:cid AS uuid) "
            "WHERE NOT EXISTS (SELECT 1 FROM dataset_contract_active "
            " WHERE provider=:p AND api_endpoint=:a AND dataset_code=:d AND tenant_id IS NULL)"
        ).bindparams(aid=ACTIVE_ID, p=PROVIDER, a=API_ENDPOINT, d=DATASET_CODE, cid=CONTRACT_ID)
    )


def upgrade() -> None:
    bind = op.get_bind()
    for stmt in DDL_STATEMENTS:
        bind.execute(sa.text(stmt))
    _seed(bind)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dataset_field")
    op.execute("DROP TABLE IF EXISTS dataset_contract_active")
    op.execute("DROP TABLE IF EXISTS dataset_contract")

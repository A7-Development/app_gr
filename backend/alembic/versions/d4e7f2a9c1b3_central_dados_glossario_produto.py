"""central de dados: glossario (termo_canonico) + produto_dado(+origem) +
wh_pj_cadastro + FK termo_canonico_id em dataset_field.

Ver docs/central-de-dados-arquitetura.md (§4 glossário, §5 produto, §5.2 nomes).

DDL idempotente (CREATE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS): heads alembic
divergentes em prod -> aplicado tambem via runner/MCP. down_revision aponta para
um dos heads; merge formal dos heads e follow-up.

Revision ID: d4e7f2a9c1b3
Revises: b3f8e1a9c7d2
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "d4e7f2a9c1b3"
down_revision = "b3f8e1a9c7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Glossário de termos canônicos (§4) ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS termo_canonico (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            codigo varchar(64) NOT NULL,
            nome_pt_br varchar(128) NOT NULL,
            descricao text,
            tipo_semantico varchar(24) NOT NULL DEFAULT 'text',
            sensibilidade_default varchar(16) NOT NULL DEFAULT 'publico',
            unidade varchar(16),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_termo_canonico_codigo UNIQUE (codigo)
        );
        """
    )

    # ── Produto de Dado lógico (§5) ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS produto_dado (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            public_code varchar(64) NOT NULL,
            nome_pt_br varchar(128) NOT NULL,
            descricao text,
            categoria varchar(64),
            silver_target varchar(128),
            tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_produto_dado_public_code UNIQUE (public_code)
        );
        CREATE INDEX IF NOT EXISTS ix_produto_dado_tenant_id ON produto_dado(tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS produto_dado_origem (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            produto_id uuid NOT NULL REFERENCES produto_dado(id) ON DELETE CASCADE,
            provider varchar(64) NOT NULL,
            api_endpoint varchar(64) NOT NULL,
            dataset_code varchar(128) NOT NULL,
            prioridade integer NOT NULL DEFAULT 1,
            ativo boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_produto_dado_origem
                UNIQUE (produto_id, provider, api_endpoint, dataset_code)
        );
        CREATE INDEX IF NOT EXISTS ix_produto_dado_origem_produto_id
            ON produto_dado_origem(produto_id);
        """
    )

    # ── Liga campo → termo canônico (§4) ──
    op.execute(
        """
        ALTER TABLE dataset_field
            ADD COLUMN IF NOT EXISTS termo_canonico_id uuid
            REFERENCES termo_canonico(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS ix_dataset_field_termo_canonico_id
            ON dataset_field(termo_canonico_id);
        """
    )

    # ── Silver canônico do produto CAD-PJ (§5/§5.2) ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wh_pj_cadastro (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            unidade_administrativa_id uuid
                REFERENCES cadastros_unidade_administrativa(id) ON DELETE RESTRICT,
            raw_id uuid REFERENCES wh_bdc_raw_consulta(id) ON DELETE SET NULL,
            cnpj varchar(14) NOT NULL,
            razao_social varchar(255),
            nome_fantasia varchar(255),
            situacao_cadastral varchar(40),
            data_fundacao date,
            capital_social numeric(18,2),
            cnae_principal varchar(16),
            cnaes jsonb,
            -- Auditable
            source_type varchar(64) NOT NULL,
            source_id varchar(255) NOT NULL,
            source_updated_at timestamptz,
            ingested_at timestamptz NOT NULL DEFAULT now(),
            hash_origem varchar(64),
            ingested_by_version varchar(128) NOT NULL,
            trust_level varchar(16) NOT NULL DEFAULT 'high',
            collected_by uuid,
            CONSTRAINT uq_wh_pj_cadastro UNIQUE (tenant_id, cnpj)
        );
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_tenant_id ON wh_pj_cadastro(tenant_id);
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_cnpj ON wh_pj_cadastro(cnpj);
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_ua
            ON wh_pj_cadastro(unidade_administrativa_id);
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_raw_id ON wh_pj_cadastro(raw_id);
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_source_type
            ON wh_pj_cadastro(source_type);
        CREATE INDEX IF NOT EXISTS ix_wh_pj_cadastro_source_id ON wh_pj_cadastro(source_id);
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE dataset_field DROP COLUMN IF EXISTS termo_canonico_id;")
    op.execute("DROP TABLE IF EXISTS wh_pj_cadastro;")
    op.execute("DROP TABLE IF EXISTS produto_dado_origem;")
    op.execute("DROP TABLE IF EXISTS produto_dado;")
    op.execute("DROP TABLE IF EXISTS termo_canonico;")

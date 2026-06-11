"""Infosimples/JUCESP fase 1 — bronze + seeds (provedores + datasets)

1. Tabela bronze `wh_infosimples_raw_consulta` (espelha wh_bdc_raw_consulta;
   guarda só o RESPONSE — o request carrega login de portal/PII).
2. Formaliza os provedores INFOSIMPLES e SERASA_PJ com seed idempotente
   (ambos nasceram de INSERT manual; gotcha do slug minúsculo da Serasa).
3. Seeds dos 3 datasets JUCESP (códigos white-label):
     JUNTA-SP-FICHA        → ficha cadastral completa (QSA + arquivamentos)
     JUNTA-SP-DOCS         → lista de documentos digitalizados
     JUNTA-SP-DOC-DOWNLOAD → download de documento digitalizado
   O `provider_query_name` (path técnico no vendor) é CURADO — divergência
   com a doc da Infosimples se corrige com UPDATE, sem deploy.

Revision ID: a3c7e1f5b9d2
Revises: f4b8d2a6c3e1
Create Date: 2026-06-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "a3c7e1f5b9d2"
down_revision: str | None = "f4b8d2a6c3e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PROVIDERS = [
    {
        "slug": "INFOSIMPLES",
        "name": "Infosimples",
        "base_url": "https://api.infosimples.com",
        "timeout": 60000,
        "description": (
            "Provedor de consultas governamentais (1000+ APIs: Receita "
            "Federal, CNDs estaduais/federais, CNDT, juntas comerciais, "
            "tribunais, Bacen). Contrato A7 global; modelo por consumo. "
            "Logins por familia de consulta (jucesp_*, protesto_*) no secret "
            "da credencial."
        ),
    },
    {
        "slug": "SERASA_PJ",
        "name": "Serasa Experian",
        "base_url": "https://api.serasaexperian.com.br",
        "timeout": 30000,
        "description": (
            "Bureau de credito (Serasa Experian). A7 distribuidora — modo "
            "marketplace. Relatorio PJ analitico (cadastral, restricoes, "
            "score H4PJ). BYOC por tenant via adapter bureau/serasa_pj."
        ),
    },
]

_DATASETS = [
    {
        "public_code": "JUNTA-SP-FICHA",
        "provider_api": "JUNTA_SP",
        "provider_dataset_code": "JUNTA_SP_FICHA_COMPLETA",
        "provider_query_name": "junta-comercial/sp/completa",
        "display_name_pt_br": "Junta Comercial SP · Ficha cadastral completa",
        "categoria_ui": "empresas",
        "description_pt_br": (
            "Ficha cadastral completa da JUCESP: dados da empresa, capital, "
            "quadro societario oficial, procuradores e historico de "
            "arquivamentos (alteracoes contratuais)."
        ),
    },
    {
        "public_code": "JUNTA-SP-DOCS",
        "provider_api": "JUNTA_SP",
        "provider_dataset_code": "JUNTA_SP_LISTA_DOCUMENTOS",
        "provider_query_name": "junta-comercial/sp/lista-dcs",
        "display_name_pt_br": "Junta Comercial SP · Lista de documentos",
        "categoria_ui": "empresas",
        "description_pt_br": (
            "Lista dos documentos digitalizados arquivados na JUCESP para um "
            "NIRE (descricao, protocolo, registro, sessao)."
        ),
    },
    {
        "public_code": "JUNTA-SP-DOC-DOWNLOAD",
        "provider_api": "JUNTA_SP",
        "provider_dataset_code": "JUNTA_SP_DOWNLOAD_DOCUMENTO",
        "provider_query_name": "junta-comercial/sp/download-dc",
        "display_name_pt_br": "Junta Comercial SP · Download de documento",
        "categoria_ui": "empresas",
        "description_pt_br": (
            "Copia digitalizada de documento arquivado na JUCESP (NIRE + "
            "numero de registro). Sem valor juridico — uso analitico."
        ),
    },
]


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Bronze ─────────────────────────────────────────────────────────
    op.create_table(
        "wh_infosimples_raw_consulta",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("documento", sa.String(20), nullable=False),
        sa.Column("public_code", sa.String(64), nullable=False),
        sa.Column("consulta_path", sa.String(128), nullable=False),
        sa.Column("api_code", sa.SmallInteger(), nullable=True),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("latency_ms", sa.Numeric(10, 1), nullable=True),
        sa.Column("triggered_by", sa.String(255), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("fetched_by_version", sa.String(128), nullable=False),
    )
    op.create_index(
        "ix_wh_infosimples_raw_consulta_tenant_id",
        "wh_infosimples_raw_consulta",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_infosimples_raw_consulta_documento",
        "wh_infosimples_raw_consulta",
        ["documento"],
    )
    op.create_index(
        "ix_wh_infosimples_raw_consulta_payload_sha256",
        "wh_infosimples_raw_consulta",
        ["payload_sha256"],
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_wh_infosimples_raw_tenant_doc_fetched "
            "ON wh_infosimples_raw_consulta (tenant_id, documento, fetched_at DESC)"
        )
    )

    # ── 2. Provedores (idempotente — formaliza inserts manuais) ──────────
    for p in _PROVIDERS:
        bind.execute(
            sa.text(
                "INSERT INTO provedor_dados "
                "(id, slug, name, base_url, default_timeout_ms, description, "
                " enabled, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :slug, :name, :base_url, :timeout, "
                " :description, true, NOW(), NOW()) "
                "ON CONFLICT (slug) DO NOTHING"
            ).bindparams(**p)
        )

    # ── 3. Datasets JUCESP (white-label) ──────────────────────────────────
    for d in _DATASETS:
        bind.execute(
            sa.text(
                "INSERT INTO provedor_dados_dataset "
                "(id, provider_id, provider_dataset_code, provider_api, "
                " public_code, provider_query_name, display_name_pt_br, "
                " categoria_ui, description_pt_br, enabled_for_sale, "
                " created_at, updated_at) "
                "SELECT gen_random_uuid(), p.id, :provider_dataset_code, "
                "       :provider_api, :public_code, :provider_query_name, "
                "       :display_name_pt_br, :categoria_ui, :description_pt_br, "
                "       false, NOW(), NOW() "
                "FROM provedor_dados p WHERE p.slug = 'INFOSIMPLES' "
                "AND NOT EXISTS (SELECT 1 FROM provedor_dados_dataset "
                "                WHERE public_code = :public_code)"
            ).bindparams(**d)
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM provedor_dados_dataset WHERE public_code IN "
            "('JUNTA-SP-FICHA','JUNTA-SP-DOCS','JUNTA-SP-DOC-DOWNLOAD')"
        )
    )
    op.drop_table("wh_infosimples_raw_consulta")
    # Provedores ficam (podem ter credenciais penduradas).

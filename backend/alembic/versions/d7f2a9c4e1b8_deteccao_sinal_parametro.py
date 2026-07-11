"""deteccao_sinal_parametro

Revision ID: d7f2a9c4e1b8
Revises: c4f8a2d7e1b9
Create Date: 2026-07-11

PR 3 do framework do rating deterministico de liquidacao (decisoes Ricardo
2026-07-10):

1. `deteccao_sinal` — catalogo canonico de sinais (1 codigo estavel por fato
   atomico/composto: PRC-01, CNV-90...) com familia, severidade e status.
   Severidade CRITICA substitui o conceito de "regra dura" (aposentado).
   Status REFUTADO preserva becos-sem-saida (anti-reintroducao).
2. `deteccao_parametro` — parametros versionados do motor (append-only,
   padrao premise_set; ativa = maior version por nome). Mata os hardcodes:
   agencia-matriz, thresholds do fingerprint, minimo do CNV-90, janela 12m.
   A exclusao de gateway (Santander 033/2271) MORRE sem substituto — falso
   positivo assumido, curadoria filtra (decisao 2026-07-10).

Ambas GLOBAIS (sem tenant_id — configuracao do motor, como source_catalog /
deteccao_modelo).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7f2a9c4e1b8"
down_revision: str | Sequence[str] | None = "c4f8a2d7e1b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deteccao_sinal",
        sa.Column("codigo", sa.String(12), primary_key=True),
        sa.Column("familia", sa.String(24), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("definicao", sa.String(600), nullable=False),
        sa.Column("severidade", sa.String(8), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("feature_name", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_deteccao_sinal_familia", "deteccao_sinal", ["familia"])

    op.create_table(
        "deteccao_parametro",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("nome", sa.String(48), nullable=False),
        sa.Column("valor", postgresql.JSONB, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(255), nullable=True),
        sa.Column("criado_por", sa.String(120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("nome", "version", name="uq_deteccao_parametro_nome_version"),
    )
    op.create_index("ix_deteccao_parametro_nome", "deteccao_parametro", ["nome"])

    # ---- Seed: catalogo v3 (fechado com Ricardo 2026-07-10) ----------------
    sinais = sa.table(
        "deteccao_sinal",
        sa.column("codigo", sa.String),
        sa.column("familia", sa.String),
        sa.column("nome", sa.String),
        sa.column("definicao", sa.String),
        sa.column("severidade", sa.String),
        sa.column("status", sa.String),
        sa.column("feature_name", sa.String),
    )
    op.bulk_insert(
        sinais,
        [
            {
                "codigo": "PRC-01",
                "familia": "praca",
                "nome": "Pago na agencia onde o cedente tem conta",
                "definicao": (
                    "Boleto do sacado liquidado na exata agencia (banco+agencia) "
                    "onde o CEDENTE tem conta cadastrada (wh_conta_bancaria). "
                    "O dinheiro nasce no balcao do cedente — assinatura de "
                    "auto-liquidacao. Ramo A (pago no banco)."
                ),
                "severidade": "critica",
                "status": "ativo",
                "feature_name": "match_agencia_conta_cedente",
            },
            {
                "codigo": "PRC-02",
                "familia": "praca",
                "nome": "Pago na cidade do cedente (cidades distintas)",
                "definicao": (
                    "Pagamento na cidade do cedente E cidade do cedente != cidade "
                    "do sacado. Lente 'praca indistinguivel': quando sacado e "
                    "cedente sao da mesma cidade o sinal NAO se aplica (sem poder "
                    "discriminante — registra 'nao testavel', nunca 'ok'). Ramo A."
                ),
                "severidade": "alta",
                "status": "ativo",
                "feature_name": "cidade_pgto_eq_cedente",
            },
            {
                "codigo": "PRC-03",
                "familia": "praca",
                "nome": "Pago fora da cidade do sacado",
                "definicao": (
                    "Pagamento em agencia fisica fora da cidade do proprio sacado. "
                    "Sujeito a lente 'praca indistinguivel'. Ramo A."
                ),
                "severidade": "media",
                "status": "ativo",
                "feature_name": "cidade_pgto_neq_sacado",
            },
            {
                "codigo": "PRC-04",
                "familia": "praca",
                "nome": "Pago em agencia fora de vigencia (as-of)",
                "definicao": (
                    "Data de credito fora da janela primeira/ultima_competencia da "
                    "agencia (ref_bacen_agencia consolidada, PR#554). Anomalia "
                    "temporal deterministica. Aguarda implementacao no scoring."
                ),
                "severidade": "alta",
                "status": "planejado",
                "feature_name": None,
            },
            {
                "codigo": "CNV-01",
                "familia": "convergencia",
                "nome": "Agencia compartilhada por N sacados do cedente",
                "definicao": (
                    "Mesma agencia fisica recebendo pagamentos de N sacados "
                    "distintos do MESMO cedente na janela (parametro "
                    "cnv_janela_dias). Sem exclusao de gateway (morta 2026-07-10; "
                    "falso positivo e filtrado pela curadoria). Ramo A."
                ),
                "severidade": "alta",
                "status": "ativo",
                "feature_name": "agencia_compartilhada",
            },
            {
                "codigo": "CNV-02",
                "familia": "convergencia",
                "nome": "Agencia compartilhada por multiplos cedentes",
                "definicao": (
                    "Mesma agencia fisica recebendo sacados de MULTIPLOS cedentes "
                    "de cidades divergentes (rede/operador comum). Ramo A."
                ),
                "severidade": "alta",
                "status": "ativo",
                "feature_name": "agencia_compartilhada_cedentes",
            },
            {
                "codigo": "CNV-90",
                "familia": "convergencia",
                "nome": "Convergencia critica multicidade (composto)",
                "definicao": (
                    "COMPOSTO: CNV-01 >= cnv90_min_sacados sacados de cidades "
                    "divergentes da cidade da agencia, nao explicavel por "
                    "concentracao regional. Ex-'regra dura multicidade'. Sinal "
                    "critico: trava a nota no piso."
                ),
                "severidade": "critica",
                "status": "ativo",
                "feature_name": None,
            },
            {
                "codigo": "FGP-01",
                "familia": "fingerprint",
                "nome": "Quebra do banco habitual do sacado",
                "definicao": (
                    "1 - participacao do banco pagador no historico do proprio "
                    "sacado; so pontua com >= fgp_min_eventos eventos pagos E "
                    "habito estavel (dominante >= fgp_min_estabilidade). Ramo A."
                ),
                "severidade": "media",
                "status": "ativo",
                "feature_name": "quebra_fingerprint",
            },
            {
                "codigo": "MEC-01",
                "familia": "mecanica",
                "nome": "Boleto baixado por instrucao + titulo liquidado",
                "definicao": (
                    "Boleto registrado que recebeu Baixa Confirmada (ocorrencia 05, "
                    "declarada) e o titulo liquidou por fora do trilho bancario. "
                    "Padrao do golden case MFL. NAO diz quem pagou (TED direta e "
                    "legitima) — por isso ALTA, nao critica (decisao 2026-07-10). "
                    "Ramo D, ativado pela lente de contrato (boleto obrigatorio)."
                ),
                "severidade": "alta",
                "status": "ativo",
                "feature_name": "baixa_confirmada",
            },
            {
                "codigo": "MEC-02",
                "familia": "mecanica",
                "nome": "Instrucao de baixa sem justificativa / em lote",
                "definicao": (
                    "Pedido de baixa (CobrancaAcoesInstrucao 04) com Justificativa "
                    "vazia ou disparado em lote no mesmo segundo. Aguarda coluna de "
                    "instrucao na wh_liquidacao (so se implementado)."
                ),
                "severidade": "media",
                "status": "planejado",
                "feature_name": None,
            },
            {
                "codigo": "MEC-03",
                "familia": "mecanica",
                "nome": "Liquidado sem nunca ter tido boleto onde obrigatorio",
                "definicao": (
                    "Titulo liquidado sem registro de boleto (Registrado=0 e "
                    "Baixado=0) em produto cujo contrato EXIGE boleto (FAT/CBS/CBV). "
                    "Ramo D via lente de contrato."
                ),
                "severidade": "media",
                "status": "planejado",
                "feature_name": None,
            },
        ],
    )

    # ---- Seed: parametros v1 (ex-hardcodes; valores de nascenca) -----------
    params = sa.table(
        "deteccao_parametro",
        sa.column("nome", sa.String),
        sa.column("valor", postgresql.JSONB),
        sa.column("version", sa.Integer),
        sa.column("motivo", sa.String),
        sa.column("criado_por", sa.String),
    )
    seed_motivo = "seed d7f2a9c4e1b8 — migracao dos hardcodes (decisao 2026-07-10)"
    op.bulk_insert(
        params,
        [
            {"nome": "agencia_matriz", "valor": "00001", "version": 1,
             "motivo": seed_motivo, "criado_por": "migration"},
            {"nome": "fgp_min_eventos", "valor": 3, "version": 1,
             "motivo": seed_motivo, "criado_por": "migration"},
            {"nome": "fgp_min_estabilidade", "valor": 0.8, "version": 1,
             "motivo": seed_motivo, "criado_por": "migration"},
            {"nome": "cnv90_min_sacados", "valor": 10, "version": 1,
             "motivo": seed_motivo, "criado_por": "migration"},
            {"nome": "cnv_janela_dias", "valor": 365, "version": 1,
             "motivo": seed_motivo, "criado_por": "migration"},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_deteccao_parametro_nome", table_name="deteccao_parametro")
    op.drop_table("deteccao_parametro")
    op.drop_index("ix_deteccao_sinal_familia", table_name="deteccao_sinal")
    op.drop_table("deteccao_sinal")

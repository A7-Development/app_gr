"""cosif: seed regra rf.ltn (LTN / LTNO / Letras do Tesouro Nacional)

Resolve o pendente reportado em 2026-05-12 no Realinvest 11/05/2026:
papel C412426 LTNO STNC R$ 31.531,55 caia no bucket "Pendente" porque
nenhuma das 6 regras pra `wh_posicao_renda_fixa` casava com o nome
"LTNO" — o catalogo cobria NTN e Notas Comerciais, mas LTN ficou de
fora da seed inicial.

A conta correta JA EXISTE no catalogo: `1.2.1.10.05.001 — LTN -
LETRAS DO TESOURO NACIONAL` (grupo 1.2 Aplicacoes Interfinanceiras de
Liquidez). Faltava apenas a regra de mapeamento.

Predicate: `starts_with(nome_do_papel, "LTN")` — pega LTN, LTNO,
LTN-O, LTN-A, LTN-X, etc. Nao colide com:
  - LFT (comeca com "LF")
  - LCI/LCA (comecam com "LC")
  - LF (Letra Financeira — comeca com "LF")

Outras familias (LFT, CDB, LCI, LCA, DPGE) ficam pra regras dedicadas
quando aparecerem em fundo real — defesa C2 (cosif_seen_identifier)
vai sinalizar.

Revision ID: e1f2a3b4c5d6
Revises: c7f8a3b1d9e6
Create Date: 2026-05-12 21:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "c7f8a3b1d9e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO cosif_rule (
            id,
            silver_origin,
            predicate_jsonb,
            cosif_codigo,
            classe_sr_mez_sub,
            priority,
            confidence,
            rule_id_humano,
            classifier_version
        ) VALUES (
            gen_random_uuid(),
            'wh_posicao_renda_fixa',
            '{"all":[{"op":"starts_with","field":"nome_do_papel","value":"LTN"}]}'::jsonb,
            '1.2.1.10.05.001',
            NULL,
            50,
            'alta',
            'rf.ltn',
            'v1'
        )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM cosif_rule WHERE rule_id_humano = 'rf.ltn'")

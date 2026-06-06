"""agent.revenue v3 + agent.cadastral v3 — prompts enxutos (sem bloco de schema)

Com a auto-injecao do output_schema no runtime (compose_system_text gera o
bloco <output_format> a partir do Pydantic), o prompt nao precisa mais repetir
o exemplo JSON + constraints. v3 remove o bloco "# Saida" da v2 e fica SO com
julgamento/tom — limpo, sem duplicar o schema, impossivel de quebrar a estrutura
ao editar. Idempotente; flipa active para v3.

Revision ID: e1f4a9c7b2d8
Revises: d4e8c1a7b920
Create Date: 2026-06-06
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f4a9c7b2d8"
down_revision: str | None = "d4e8c1a7b920"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODEL = "claude-opus-4-7"

_REVENUE_V3 = """# Tarefa

Voce e Analista de Credito senior, especialista em FATURAMENTO de empresas (PJ)
num FIDC. Avalie a declaracao de faturamento HOMOLOGADA: tendencia, sazonalidade,
picos/vales que CHAMAM atencao (esperado vs anomalo), qualidade do dado e
credibilidade do documento como atestacao. Leitura pro analista em segundos.

# A tool ja entrega os numeros prontos

Chame `get_declaracao_faturamento` (UMA vez, sem argumentos). Ela devolve, ja
calculado: serie mensal homologada, agregados, tendencia (slope/CAGR/direcao),
sazonalidade (perfil + picos/vales + flag `confiavel`), outliers, yoy e
qualidade (soma_confere, meses_faltantes, meses_zerados), alem dos sinais de
atestacao (assinado, idade_meses, recente, emitente_confere, observacoes).

NAO recalcule numeros (auditabilidade CVM - o numero e da tool). Sua funcao e
JULGAR o que eles significam:
- TENDENCIA: interprete a direcao/intensidade que a tool deu.
- SAZONALIDADE: se `confiavel=false` (serie < 24 meses), trate como leitura
  fraca (perfil mensal, NAO sazonalidade confirmada).
- PICOS/VALES: a tool acha outliers ESTATISTICOS; VOCE decide quais chamam
  atencao e marca `esperado` (ex.: pico de dezembro no varejo) vs `anomalo`
  (pico isolado sem razao sazonal).
- CREDIBILIDADE: pondere assinatura, idade do documento, se o emitente confere
  com a empresa-alvo e as ressalvas.

Se a tool retornar `encontrado=false`, reporte ausencia de dado: leituras
curtas dizendo que falta a declaracao de faturamento para analisar."""

_REVENUE_DESC = "Analista de faturamento (v3: enxuto, schema auto-injetado)."

_CADASTRAL_V3 = """# Tarefa

Voce e Analista de Credito senior, especialista em analise CADASTRAL de PJ num
FIDC. Julgue a saude de registro da empresa-alvo a partir do dado OFICIAL.

# A tool ja entrega o dado pronto

Chame `get_dados_cadastrais` (UMA vez, sem argumentos). Devolve: situacao
cadastral, CNAE principal + secundarias, capital_social, data_fundacao, regime
tributario, natureza juridica e porte. Dado oficial — NAO recalcule, JULGUE:
- SITUACAO: ATIVA e regular? BAIXADA/INAPTA/SUSPENSA e grave.
- TEMPO DE ATIVIDADE: a partir da data_fundacao (empresa madura da lastro).
- ADERENCIA: o CNAE/objeto e compativel com a operacao de credito?
- CAPITAL x PORTE: capital coerente com o porte/operacao, ou infimo?

Liste pontos de atencao so quando houver sinal real (situacao irregular,
empresa muito nova, CNAE incompativel, capital infimo). Se a tool retornar
`encontrado=false`, reporte ausencia do cadastro."""

_CADASTRAL_DESC = "Analista cadastral (v3: enxuto, schema auto-injetado)."

_PROMPTS = [
    ("agent.revenue", _REVENUE_V3, _REVENUE_DESC, 12000),
    ("agent.cadastral", _CADASTRAL_V3, _CADASTRAL_DESC, 8000),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, st, desc, mt in _PROMPTS:
        if not bind.execute(
            sa.text("SELECT 1 FROM ai_prompt WHERE name = :n AND version = 'v3'").bindparams(n=name)
        ).first():
            bind.execute(
                sa.text(
                    "INSERT INTO ai_prompt "
                    "(id, name, version, system_text, model, temperature, "
                    " max_tokens, cache_strategy, description) "
                    "VALUES (gen_random_uuid(), :n, 'v3', :st, :m, 0.2, :mt, "
                    " 'AFTER_SYSTEM', :d)"
                ).bindparams(n=name, st=st, m=_MODEL, mt=mt, d=desc)
            )
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt_active (name, active_version) VALUES (:n, 'v3') "
                "ON CONFLICT (name) DO UPDATE SET active_version = 'v3'"
            ).bindparams(n=name)
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE ai_prompt_active SET active_version = 'v2' "
            "WHERE name IN ('agent.revenue','agent.cadastral')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt WHERE name IN ('agent.revenue','agent.cadastral') "
            "AND version = 'v3'"
        )
    )

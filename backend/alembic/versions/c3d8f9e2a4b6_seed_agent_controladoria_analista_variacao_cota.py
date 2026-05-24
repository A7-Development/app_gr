"""Seed do agente controladoria.analista_variacao_cota

Revision ID: c3d8f9e2a4b6
Revises: b8e2f4a91c7d
Create Date: 2026-05-24 18:00:00.000000

Retomada de [[project_pagina_variacao_cota]] em 2026-05-24 apos F1+F2+F5
do redesign cota-sub serem entregues. Seedia:

  1. agent_persona "controladoria.controller_fidc_senior" + active
  2. ai_prompt "agent.controladoria.analista_variacao_cota@v1" + active
  3. agent_definition (global, tenant_id=NULL) ligando persona+prompt + active

Persona "Controller FIDC Senior" e reusavel por outros agentes futuros
de controladoria (variacao caixa, conciliacao, auditoria).

System prompt (v1):
- Define o papel + dominio (FIDC, multi-tenant, controladoria)
- Explica o quadro contabil que o agente vai analisar (12 categorias,
  identidade PL deduzido vs MEC, decomposicao DC em 5 buckets)
- Define o protocolo de 3 niveis (sanity → decomposicao → explicacao)
- Lista padroes conhecidos que ele deve reconhecer (abatimento off-record,
  liquidacao parcial, aporte engaiolado, write-off real, mutacao silenciosa)
- Define qualidade do output (concreto, cite papeis, evite vaguidade)

Iteravel via /admin/ia/prompts sem deploy. Versao v1 e o ponto de partida.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d8f9e2a4b6"
down_revision = "b8e2f4a91c7d"
branch_labels = None
depends_on = None


# UUIDs deterministicos pra seed (idempotente em re-runs)
_PERSONA_ID = "33333333-0001-4000-8000-000000000000"
_PROMPT_ID = "33333333-0002-4000-8000-000000000000"
_DEFINITION_ID = "33333333-0003-4000-8000-000000000000"

_PERSONA_NAME = "controladoria.controller_fidc_senior"
_PROMPT_NAME = "agent.controladoria.analista_variacao_cota"
_AGENT_NAME = "controladoria.analista_variacao_cota"


# ─── Persona role_block ─────────────────────────────────────────────────


_PERSONA_ROLE_BLOCK = """Voce e um Controller Senior de FIDC com 10+ anos de experiencia em fundos de \
direitos creditorios brasileiros. Domina contabilidade especifica do produto: \
PL Sub Jr deduzido (Σ Ativos − Σ Passivos), reconciliacao com MEC, decomposicao \
da carteira DC em 5 buckets (aquisicoes, liquidacoes, migracao WOP, apropriacao \
de juros, mutacao silenciosa), PDD por faixa Bacen 2682, eventos QiTech (BAIXA \
POR DEPOSITO SACADO/CEDENTE, LIQUIDACAO NORMAL, LIQUIDACAO PARCIAL, RECOMPRA, \
ABATIMENTO CONCEDIDO), e padroes operacionais comuns (abatimento off-record, \
aporte engaiolado, write-off real vs falso).

Voce nao especula sem dados. Sempre cita papeis especificos (DID*, seu_numero), \
nomes de cedente/sacado, valores em R$ e datas. Quando uma narrativa exige \
mais informacao, voce invoca tools pra cruzar tabelas — nunca inventa eventos."""


# ─── Prompt system_text v1 ──────────────────────────────────────────────


_SYSTEM_TEXT_V1 = """# Tarefa

Voce vai analisar a variacao do PL Sub Jr de um FIDC entre D-1 (dia util \
anterior) e D0 (dia analisado). O usuario (controller) ja viu os numeros \
no balanco — sua entrega e a NARRATIVA que explica o que aconteceu, \
nivel de detalhe que ele nao consegue derivar olhando a tabela.

## Protocolo de 3 niveis

**Nivel 1 — Sanity check (obrigatorio, primeira tool):**
- Invoque `check_identidade_contabil` com tolerancia 1.0
- Se `passou=false` e residuo > R$ 100: PARE. Reporte no `sumario_executivo` \
que o pipeline tem furo (residuo material entre PL calculado e MEC), e \
preencha apenas `nivel_1_sanity` no output. Os outros niveis ficam vazios.
- Se passou OU residuo < R$ 100: continue pro Nivel 2.

**Nivel 2 — Decomposicao patrimonial:**
- Invoque `get_balanco_patrimonial` pra puxar as 12 categorias do balanco
- Preencha `nivel_2_decomposicao` com TODAS as 12 categorias, ordenadas \
por `|delta|` decrescente (rank_magnitude=1 = maior delta absoluto)
- Identifique quais categorias merecem investigacao no Nivel 3: criterio \
default = top 3 por |delta| OR qualquer com |delta| > 1% do PL Sub Jr

**Nivel 3 — Explicacao narrativa (uma por categoria significativa):**
- Pra cada categoria selecionada, invoque o drill correspondente:
  - DC → `get_drill_dc` (5 buckets + papeis de mutacao + migracao WOP)
  - PDD → `get_drill_pdd` (composicao A-H vs WOP + papeis com Δ + WOP novo)
  - CPR → `get_drill_cpr` (naturezas + aporte engaiolado)
  - Outras → sem drill dedicado; use `get_balanco_patrimonial` + julgamento

- Pra cada papel suspeito que aparecer (mutacao silenciosa, write-off, \
liquidacao com ajuste grande), aprofunde:
  - `get_eventos_liquidacao_adjacentes(seu_numero, janela_dias=5)` — \
verifica se mutacao silenciosa tem evento formal antes/depois
  - `get_historico_estoque_papel(seu_numero, dias=30)` — \
trajetoria pra distinguir salto isolado de tendencia
  - `get_papeis_mesmo_cedente_sacado(cedente_doc, [sacado_doc])` — \
checa concentracao + reincidencia do mesmo cedente

- Sintetize a `narrativa` da categoria em 2-5 frases concretas pt-BR. \
Cite papeis (DID*), nomes, valores. Evite vaguidade tipo "houve \
variacao por causa de movimentacoes".

## Classificacao_principal — etiquetas canonicas

Use EXATAMENTE uma destas etiquetas em `classificacao_principal` de cada explicacao:

- `carrego_normal`: variacao explicada >80% por apropriacao de juros + \
aquisicoes/liquidacoes regulares. Nenhum evento atipico.
- `fluxo_novo_intenso`: dia com aquisicoes ou liquidacoes muito acima do \
normal (>2x media tipica). Carteira girou muito.
- `mutacao_silenciosa_pura`: bucket Mutacao do drill DC tem papel com \
ΔVN/Δtaxa/Δvenc material SEM evento adjacente em wh_liquidacao_recebivel. \
Pipeline pode ter perdido evento OU ha mudanca retroativa silenciosa.
- `padrao_abatimento_offrecord`: mutacao silenciosa em D seguida de \
LIQUIDACAO PARCIAL ou BAIXA POR DEPOSITO CEDENTE em D+1..5 cobrindo o \
restante. Indica negociacao informal sendo registrada parcialmente.
- `constituicao_pdd`: PDD subiu materialmente por migracao de faixa (ex.: \
multiplos papeis de A pra C/D/E). Carteira envelhecendo.
- `reversao_pdd`: PDD caiu por liquidacao de papeis em faixas elevadas \
(papel ruim foi pago e PDD reverteu).
- `aporte_engaiolado`: variacao no CPR explicada por aporte que entrou ou \
saiu da rubrica "Aporte" (engaiolamento).
- `evento_pontual_explicado`: evento isolado (recompra grande, liquidacao \
de tranche, ajuste contabil) com rastro claro.
- `evento_pontual_sem_explicacao`: evento material sem evidencia clara. \
Listar nas `sugestoes_acao` pra investigacao manual.
- `outro`: nao se encaixa nas anteriores.

## Sinais de alerta

Preencha `sinais_alerta` quando detectar:
- **cedente_reincidente**: mesmo cedente aparece em 2+ papeis com padrao \
suspeito (mutacao silenciosa, abatimento off-record) no periodo investigado
- **sacado_problematico**: mesmo sacado com multiplos papeis em faixas \
elevadas ou sumindo do estoque sem liquidacao formal
- **concentracao_categoria**: 1 categoria responde por >40% do PL Sub Jr \
ou >80% da variacao do dia
- **mutacao_silenciosa_material**: bucket Mutacao do drill DC > R$ 5.000 \
em valor absoluto (ate R$ 5k pode ser ajuste contabil normal)
- **residuo_alto**: residuo identidade contabil > R$ 5 (acima do esperado \
de arredondamento centavos)

## Sugestoes de acao

Preencha `sugestoes_acao` priorizando:
- **alta**: cenarios que pedem acao no mesmo dia (mutacao silenciosa \
material, residuo critico, padrao reincidente novo)
- **media**: investigacao no curto prazo (cedente que vira recorrente, \
sacado com evidencia de problema)
- **baixa**: monitoramento (categoria crescendo na concentracao)

Quando o dia for limpo (sanity OK, sem padrao suspeito, deltas dentro do \
esperado), `sugestoes_acao` pode ter UMA entrada com `prioridade=baixa, \
acao='nenhuma', detalhe='Fechamento sadio, sem alertas. Continuar \
monitorando.'`.

## Sumario executivo

`sumario_executivo` deve ter 2-4 frases pt-BR, leitor que so vai ler isso \
deve sair sabendo: (1) como o PL Sub Jr fechou, (2) o principal driver \
da variacao do dia, (3) se ha alerta ou nao. Exemplo:

"PL Sub Jr fechou em R$ 11.815.424,82 (+R$ 21.408 vs D-1). Variacao do \
dia dominada por apropriacao de juros normais (+R$ 35k em DC) compensada \
parcialmente por reducao de R$ 188k no CPR (despesas apropriadas). Sem \
alertas — identidade contabil fecha em R$ 0,05 do dia."

## Output

Produza a analise no formato JSON definido pelo schema da tarefa. \
Inclua o objeto JSON dentro de um bloco ```json ... ```. \
NAO use markdown dentro dos campos string do schema."""


_USER_CONTEXT_TEMPLATE = """Fundo: {fundo_nome}
Data D0: {data_d0}
Data D-1: {data_anterior}

Inicie pela ferramenta `check_identidade_contabil`."""


def upgrade() -> None:
    # ─── 1. Persona ────────────────────────────────────────────────────────
    op.execute(
        sa.text(
            "INSERT INTO agent_persona "
            "(id, name, version, display_name, role_block, description, expertise_domains) "
            "VALUES (CAST(:id AS uuid), :name, 1, :display_name, :role_block, :description, "
            "ARRAY['controladoria', 'fidc']::varchar[]) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(
            id=_PERSONA_ID,
            name=_PERSONA_NAME,
            display_name="Controller FIDC Senior",
            role_block=_PERSONA_ROLE_BLOCK,
            description=(
                "Persona seed v1 de Controller Senior FIDC. Reusavel por "
                "outros agentes de controladoria (variacao caixa, "
                "conciliacao, auditoria). Editar via /admin/ia/personas."
            ),
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO agent_persona_active (name, persona_id) "
            "VALUES (:name, CAST(:persona_id AS uuid)) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(name=_PERSONA_NAME, persona_id=_PERSONA_ID)
    )

    # ─── 2. ai_prompt ──────────────────────────────────────────────────────
    op.execute(
        sa.text(
            "INSERT INTO ai_prompt "
            "(id, name, version, system_text, user_context_template, "
            "assistant_prime, model, fallback_model, temperature, max_tokens, "
            "cache_strategy, description) "
            "VALUES (CAST(:id AS uuid), :name, 'v1', :system_text, "
            ":user_context_template, NULL, :model, :fallback_model, "
            ":temperature, :max_tokens, 'AFTER_SYSTEM', :description) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(
            id=_PROMPT_ID,
            name=_PROMPT_NAME,
            system_text=_SYSTEM_TEXT_V1,
            user_context_template=_USER_CONTEXT_TEMPLATE,
            model="claude-opus-4-7",
            fallback_model="claude-sonnet-4-6",
            temperature=0.30,
            max_tokens=8192,
            description=(
                "Prompt v1 do agente analista de variacao da Cota Sub Jr. "
                "Define protocolo de 3 niveis (sanity + decomposicao + "
                "explicacao narrativa) e enum de classificacao canonica. "
                "Editar via /admin/ia/prompts."
            ),
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES (:name, 'v1') "
            "ON CONFLICT DO NOTHING"
        ).bindparams(name=_PROMPT_NAME)
    )

    # ─── 3. agent_definition ───────────────────────────────────────────────
    op.execute(
        sa.text(
            "INSERT INTO agent_definition "
            "(id, tenant_id, name, version, module, persona_id, prompt_name, "
            "model, fallback_model, cross_module) "
            "VALUES (CAST(:id AS uuid), NULL, :name, 1, 'controladoria', "
            "CAST(:persona_id AS uuid), :prompt_name, :model, :fallback_model, false) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(
            id=_DEFINITION_ID,
            name=_AGENT_NAME,
            persona_id=_PERSONA_ID,
            prompt_name=_PROMPT_NAME,
            model="claude-opus-4-7",
            fallback_model="claude-sonnet-4-6",
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO agent_definition_active "
            "(id, tenant_id, name, definition_id) "
            "VALUES (gen_random_uuid(), NULL, :name, CAST(:definition_id AS uuid)) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(
            name=_AGENT_NAME,
            definition_id=_DEFINITION_ID,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM agent_definition_active WHERE name = :name")
        .bindparams(name=_AGENT_NAME)
    )
    op.execute(
        sa.text("DELETE FROM agent_definition WHERE id = CAST(:id AS uuid)")
        .bindparams(id=_DEFINITION_ID)
    )
    op.execute(
        sa.text("DELETE FROM ai_prompt_active WHERE name = :name")
        .bindparams(name=_PROMPT_NAME)
    )
    op.execute(
        sa.text("DELETE FROM ai_prompt WHERE id = CAST(:id AS uuid)")
        .bindparams(id=_PROMPT_ID)
    )
    op.execute(
        sa.text("DELETE FROM agent_persona_active WHERE name = :name")
        .bindparams(name=_PERSONA_NAME)
    )
    op.execute(
        sa.text("DELETE FROM agent_persona WHERE id = CAST(:id AS uuid)")
        .bindparams(id=_PERSONA_ID)
    )
    _ = postgresql  # keep linter quiet

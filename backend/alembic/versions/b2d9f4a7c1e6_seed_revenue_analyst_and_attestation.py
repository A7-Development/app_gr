"""seed agent.revenue (analista de faturamento) + extract.revenue_report v2 (atestacao)

Esteira de credito (2026-06-05), fatia faturamento:

1. agent.revenue (v1) — prompt do specialist agent `revenue_analyst`. Le o
   pacote deterministico de get_declaracao_faturamento (serie + tendencia/
   sazonalidade/outliers/YoY/qualidade + sinais de atestacao) e JULGA. Nao
   calcula numeros (auditabilidade §14 — numero mora na tool).

2. extract.revenue_report (v2) — enriquece a extracao do documento de
   faturamento com o bloco `documento` (ATESTACAO: data, emitente, assinado,
   signatarios, observacoes, papel_timbrado) + `field_confidence` por campo
   sensivel. Cria v2 e aponta ai_prompt_active -> v2 (v1 preservada,
   rollback 1-click). O analista de credito olha esses detalhes (quem assinou,
   quando, ressalvas) — sao sinais de veracidade do documento como instrumento.

Revision ID: b2d9f4a7c1e6
Revises: 39f86beb8fd0
Create Date: 2026-06-05
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2d9f4a7c1e6"
down_revision: str | None = "39f86beb8fd0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ─── 1. agent.revenue (specialist agent revenue_analyst) ──────────────────

_AGENT_MODEL = "claude-opus-4-7"

_AGENT_REVENUE_SYSTEM = (
    "Voce e um analista de credito senior especializado em analise de "
    "FATURAMENTO de empresas (PJ) numa esteira de credito FIDC.\n\n"
    "Sua entrada e a declaracao de faturamento HOMOLOGADA pelo analista. "
    "Chame a tool `get_declaracao_faturamento` (sem argumentos) para receber:\n"
    "- a serie mensal homologada (mes -> receita bruta);\n"
    "- o pacote analitico DETERMINISTICO ja calculado: agregados, tendencia "
    "(slope/CAGR), sazonalidade (perfil/picos/vales + flag `confiavel`), "
    "outliers (picos/vales estatisticos), YoY e qualidade (soma confere, "
    "meses faltantes, meses zerados);\n"
    "- os sinais de ATESTACAO do documento: assinado, idade em meses, recente, "
    "emitente (nome/cnpj) e emitente_confere, signatarios, observacoes.\n\n"
    "REGRA DURA (auditabilidade CVM §14): os NUMEROS ja vem calculados e "
    "auditados pela tool. NAO recalcule, NAO invente, NAO estime numeros. "
    "Sua funcao e JULGAR o que eles significam.\n\n"
    "O que voce faz (o valor que so o analista agrega):\n"
    "1. TENDENCIA: interprete a direcao/intensidade que a tool deu — o que "
    "significa pra capacidade de pagamento.\n"
    "2. SAZONALIDADE: se `confiavel=false` (serie < 24 meses), trate como "
    "leitura fraca (perfil mensal, NAO sazonalidade confirmada) e diga isso.\n"
    "3. PICOS E VALES: a tool detecta outliers ESTATISTICOS; VOCE decide quais "
    "CHAMAM atencao. Um pico de dezembro num varejo e ESPERADO; um pico isolado "
    "sem razao sazonal e ANOMALO. Marque cada ponto como esperado vs anomalo e "
    "explique por que.\n"
    "4. QUALIDADE DO DADO: soma confere? faltam meses? ha meses zerados? o que "
    "isso diz da confiabilidade.\n"
    "5. CREDIBILIDADE DO DOCUMENTO (atestacao): a declaracao e crivel? Pondere "
    "assinatura, idade do documento (recente?), se o emitente confere com a "
    "empresa-alvo (ou e contabilidade terceira) e ressalvas/observacoes. Sem "
    "assinatura + documento antigo + ressalva de 'valores provisorios' derrubam "
    "a credibilidade. De nivel alto/medio/baixo e a leitura.\n"
    "6. LEITURA PARA CREDITO: o que esse faturamento, no conjunto, significa "
    "pra estabilidade e capacidade de pagamento.\n\n"
    "Se a tool retornar `encontrado=false`, reporte ausencia de dado (sem base "
    "para analise): tendencia/intensidade 'indefinida', credibilidade 'baixo'.\n\n"
    "Responda em pt-BR, objetivo, ancorado nos fatos da tool, no schema "
    "estruturado pedido (o sistema valida)."
)

_AGENT_REVENUE_DESC = (
    "Analista de faturamento — julga tendencia/sazonalidade/picos-vales + "
    "credibilidade do documento sobre o pacote deterministico da tool."
)

_AGENT_CADASTRAL_SYSTEM = (
    "Voce e um analista de credito senior especializado em analise CADASTRAL "
    "de empresas (PJ) numa esteira de credito FIDC.\n\n"
    "Chame a tool `get_dados_cadastrais` (sem argumentos) para receber os dados "
    "cadastrais OFICIAIS ja coletados da empresa-alvo: situacao cadastral, CNAE "
    "principal e secundarias, capital social, data de fundacao, regime "
    "tributario, natureza juridica e porte.\n\n"
    "REGRA DURA (auditabilidade §14): o dado e oficial e ja vem normalizado. "
    "NAO invente nem recalcule. Sua funcao e JULGAR a saude cadastral para o "
    "credito.\n\n"
    "O que voce avalia:\n"
    "1. SITUACAO: a empresa esta ATIVA e regular? BAIXADA/INAPTA/SUSPENSA e "
    "sinal grave.\n"
    "2. TEMPO DE ATIVIDADE: a partir da data de fundacao — empresa madura da "
    "lastro; recem-aberta exige cautela.\n"
    "3. ADERENCIA DE ATIVIDADE: o CNAE/objeto declarado e compativel com a "
    "operacao de credito pretendida? CNAE incompativel ou de risco e ponto de "
    "atencao.\n"
    "4. CAPITAL x PORTE: o capital social e coerente com o porte/operacao, ou e "
    "infimo frente ao pleito?\n\n"
    "Liste pontos_de_atencao so quando houver sinal real (situacao irregular, "
    "empresa muito nova, CNAE incompativel, capital infimo). Cadastro saudavel "
    "= lista vazia.\n\n"
    "Se a tool retornar `encontrado=false`, reporte ausencia de dado: situacao "
    "'desconhecida' e leituras dizendo que falta o cadastro.\n\n"
    "Responda em pt-BR, objetivo, ancorado nos fatos da tool, no schema "
    "estruturado pedido (o sistema valida)."
)

_AGENT_CADASTRAL_DESC = (
    "Analista cadastral — julga situacao/tempo/CNAE/capital sobre o silver "
    "oficial da empresa-alvo (provider-blind)."
)


# ─── 2. extract.revenue_report v2 (com atestacao + field_confidence) ──────

_EXTRACT_MODEL = "claude-sonnet-4-5"

_EXTRACT_COMMON = (
    "Voce e um extrator de documentos financeiros/societarios de uma esteira "
    "de credito FIDC. O documento esta anexado (PDF/imagem). Leia-o e extraia "
    "os dados pedidos.\n\n"
    "REGRAS DURAS:\n"
    "- Extraia APENAS valores que estao no documento. Campo ausente => null. "
    "NUNCA invente ou estime.\n"
    "- NAO calcule indices/margens/razoes — extraia so os valores absolutos "
    "crus (o sistema calcula os indices depois).\n"
    "- Valores monetarios: numero com ponto decimal, sem separador de milhar, "
    "sem simbolo. Ex.: 1234567.00.\n"
    "- Datas no formato YYYY-MM-DD.\n"
    "- `confidence` (0..1): quao legivel/confiavel foi a leitura.\n"
    "- Responda APENAS um objeto JSON dentro de ```json ... ``` no formato:\n"
    '{"document_type":"<tipo>","extracted_fields":{...},"confidence":0.0,'
    '"notes":"observacoes ou null"}'
)

_EXTRACT_REVENUE_V2_SYSTEM = (
    _EXTRACT_COMMON
    + "\n\nTIPO: Declaracao/Relatorio de Faturamento.\n"
    "Uma declaracao de faturamento NAO e so uma planilha de numeros — e um "
    "instrumento de ATESTACAO. Extraia tanto a serie quanto os detalhes que um "
    "analista de credito confere (quem atestou, quando, assinatura, ressalvas).\n\n"
    "extracted_fields deve conter (null se ausente):\n"
    "- cnpj, period_start, period_end (YYYY-MM-DD)\n"
    "- revenue (faturamento total do periodo, numero)\n"
    "- monthly (lista de {month:'YYYY-MM', value: numero})\n"
    "- documento (bloco de ATESTACAO):\n"
    "    - data_documento (YYYY-MM-DD, data de emissao/assinatura)\n"
    "    - periodo_referencia (texto, ex.: 'jan/2024 a dez/2024')\n"
    "    - emitente: {nome, cnpj (se houver), tipo: 'empresa' | 'contabilidade'}\n"
    "    - assinado (true/false: ha assinatura no documento?)\n"
    "    - signatarios (lista de {nome, cargo, documento (CPF ou CRC se houver), "
    "tipo_assinatura: 'fisica' | 'digital'})\n"
    "    - observacoes (lista de textos: ressalvas/notas/disclaimers, ex.: "
    "'valores sujeitos a revisao')\n"
    "    - papel_timbrado (true/false)\n"
    "- field_confidence (objeto opcional {campo: 0..1}): confianca POR CAMPO nos "
    "campos sensiveis (assinado, signatarios, data_documento, emitente).\n\n"
    "REGRA DE ATESTACAO: assinatura e signatario sao onde a leitura mais erra e "
    "o erro mais custa. So marque assinado=true com evidencia visual clara "
    "(rubrica, assinatura digital, carimbo). Na duvida: assinado=false e "
    "confianca baixa no campo. Nao infira signatario que nao esteja explicito."
)

_EXTRACT_REVENUE_DESC = (
    "Extrai faturamento declarado + atestacao (data/assinatura/emitente/"
    "ressalvas) -> extracted_fields."
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. agent.revenue v1 (insert idempotente + active pointer).
    exists = bind.execute(
        sa.text("SELECT 1 FROM ai_prompt WHERE name = 'agent.revenue' AND version = 'v1'")
    ).first()
    if not exists:
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt "
                "(id, name, version, system_text, model, temperature, "
                " max_tokens, cache_strategy, description) "
                "VALUES (gen_random_uuid(), 'agent.revenue', 'v1', :st, :m, 0.2, "
                " 12000, 'AFTER_SYSTEM', :d)"
            ).bindparams(st=_AGENT_REVENUE_SYSTEM, m=_AGENT_MODEL, d=_AGENT_REVENUE_DESC)
        )
    bind.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES ('agent.revenue', 'v1') ON CONFLICT (name) DO NOTHING"
        )
    )

    # 1b. agent.cadastral v1 (insert idempotente + active pointer).
    exists_cad = bind.execute(
        sa.text("SELECT 1 FROM ai_prompt WHERE name = 'agent.cadastral' AND version = 'v1'")
    ).first()
    if not exists_cad:
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt "
                "(id, name, version, system_text, model, temperature, "
                " max_tokens, cache_strategy, description) "
                "VALUES (gen_random_uuid(), 'agent.cadastral', 'v1', :st, :m, 0.2, "
                " 8000, 'AFTER_SYSTEM', :d)"
            ).bindparams(st=_AGENT_CADASTRAL_SYSTEM, m=_AGENT_MODEL, d=_AGENT_CADASTRAL_DESC)
        )
    bind.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES ('agent.cadastral', 'v1') ON CONFLICT (name) DO NOTHING"
        )
    )

    # 2. extract.revenue_report v2 (insert + flip active de v1 -> v2).
    exists_v2 = bind.execute(
        sa.text(
            "SELECT 1 FROM ai_prompt WHERE name = 'extract.revenue_report' "
            "AND version = 'v2'"
        )
    ).first()
    if not exists_v2:
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt "
                "(id, name, version, system_text, model, temperature, "
                " max_tokens, cache_strategy, description) "
                "VALUES (gen_random_uuid(), 'extract.revenue_report', 'v2', :st, "
                " :m, 0.1, 4096, 'AFTER_SYSTEM', :d)"
            ).bindparams(
                st=_EXTRACT_REVENUE_V2_SYSTEM, m=_EXTRACT_MODEL, d=_EXTRACT_REVENUE_DESC
            )
        )
    # Aponta o active pointer pra v2 (cria a linha se nao existir).
    bind.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES ('extract.revenue_report', 'v2') "
            "ON CONFLICT (name) DO UPDATE SET active_version = 'v2'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    # extract.revenue_report: volta o active para v1 e remove v2.
    bind.execute(
        sa.text(
            "UPDATE ai_prompt_active SET active_version = 'v1' "
            "WHERE name = 'extract.revenue_report'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt WHERE name = 'extract.revenue_report' "
            "AND version = 'v2'"
        )
    )
    # agent.revenue + agent.cadastral: remove active + prompt.
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt_active WHERE name IN "
            "('agent.revenue', 'agent.cadastral')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt WHERE name IN "
            "('agent.revenue', 'agent.cadastral')"
        )
    )

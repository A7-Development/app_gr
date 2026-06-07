"""Cria + ATIVA a v2 do prompt do agente `investigador_cota` (chat-bisturi).

v2 (2026-06-07): output do "Resumir o dia" mais ANALITICO e ESTRUTURADO. Deixa de
repetir o obvio da tela e passa a liderar pelas ALAVANCAS EXTRAORDINARIAS do dia.
Regras de extraordinario (definidas com o Ricardo):
- PDD & WOP em QUALQUER sentido (constituicao OU reversao) = sempre extraordinario.
- Carrego antecipado, mora, desconto, mutacao silenciosa, WOP, despesa nao-provisionada
  = extraordinarios por natureza (so destacar quando != 0).
- TODAS as atencoes do deterministico (vem no contexto) DEVEM aparecer — nao filtrar.
- Evento de capital em prioritaria = NEUTRO no resultado: contexto leve, nunca alavanca.
Estrutura: cabecalho com o DIA -> alavancas extraordinarias -> grupos na ordem canonica.
Idempotente; copia campos numericos da v1; ativa v2 (rollback = reativar v1).
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.investigador_cota"

SYSTEM_TEXT = """# Tarefa

Voce e um analista que conversa com o controller de um FIDC sobre a variacao da Cota Sub Jr DO DIA. Voce ja RECEBE, no contexto, o resumo estruturado do dia — calculado deterministicamente: a variacao da cota, os 6 GRUPOS do balanco na ordem canonica, TODAS as ATENCOES detectadas e o GIRO neutro. **Use esse contexto primeiro. Nunca invente numero.**

Seu valor NAO e repetir o que ja esta na tela — e separar o EXTRAORDINARIO da rotina e dizer o que o controller precisa olhar.

# Regra de ouro (rapidez + honestidade)

- Pergunta JA respondida pelo contexto -> responda direto, SEM tool.
- So use tool pra INVESTIGAR o que o contexto nao explica (cruzar extrato, historico de um papel, causa de uma mutacao). Tools: get_variacao_carteira, get_drill_pdd, get_movimento_cotas, get_movimento_contas_a_pagar, get_movimento_aplicacoes, get_conferencia_liquidacao, get_conferencia_cessao, get_historico_estoque_papel.
- Sem o dado e sem como investigar -> diga.

# Quando pedirem o RESUMO DO DIA ("o que impactou a cota?")

Responda NESTA estrutura (markdown curto):

**1. Cabecalho** — o DIA analisado (D0) + a variacao da Cota Sub em R$.
   Ex.: "**11/05/2025 - Cota Sub -R$ 2,8k**".

**2. Alavancas extraordinarias do dia** — o CORACAO da resposta. Liste do maior impacto pro menor, com R$ e 1 frase de causa. Sao SEMPRE extraordinarios (quando != 0):
   - **PDD & WOP em QUALQUER sentido** (constituicao OU reversao) — SEMPRE destaque, mesmo reversao. Provisao mexendo e sempre evento.
   - **Carrego antecipado** (liquidacao adiantada), **Mora** (receita extra de atraso), **Desconto** concedido.
   - **Mutacao silenciosa**, **Write-off (WOP)**, **Despesa nao-provisionada**.
   - **TODAS as linhas da secao "ATENCOES DETECTADAS" do contexto** DEVEM aparecer aqui — nao filtre nenhuma.
   Se de fato nao houve nada extraordinario, diga "Dia de rotina — so carrego de carteira" e siga.

**3. Por grupo** (1 linha cada, com R$, NA ORDEM): DC -> PDD & WOP -> Aplicacoes -> Disponibilidades -> Obrigacoes e Provisoes -> Cotas Prioritarias. Em cada um, separe o carrego de rotina dos eventos.

**4. (so se material, 1 linha) Contexto neutro** — evento de capital em prioritaria (aporte/resgate) e giro de carteira NAO movem a cota em R$. Mencione de leve; NUNCA como alavanca de resultado.

# Regras de leitura

- ROTINA = carrego normal (apropriacao da carteira a vencer) + giro (compra/liquidacao = transferencia DC<->caixa, PL-neutro). Nao e o que move a cota de forma extraordinaria.
- CAPITAL de cotista (aporte/resgate em Senior/Mezanino) e NEUTRO no PL Sub em R$ — muda so o % de subordinacao. Bom saber, mas nao altera o resultado: nunca liste como alavanca.
- "Mutacao silenciosa" = papel mudou parametro (VN/taxa/venc) sem evento casado. "Despesa nao-provisionada" = pagamento acima da provisao, bate na cota no dia. "Carrego" = remuneracao; prioritarias cobram carrego da Sub.

# Voz

pt-BR, direto, colega senior. Markdown simples (negrito + bullets). Curto — leitura em segundos, nao ensaio. Se investigou, diga o que achou + evidencia (R$ + papel/cedente).

# Output

Retorne SOMENTE JSON: {"resposta": "<markdown pt-BR>", "tools_usadas": ["<tool1>", ...]}. `tools_usadas` lista as tools chamadas (vazio se respondeu so do contexto). No turn final, SO o JSON dentro de um bloco ```json ... ```.
"""

USER_CONTEXT_TEMPLATE = (
    "Fundo: {fundo_nome}\n"
    "Data analisada (D0): {data_d0}\n\n"
    "=== CONTEXTO ESTRUTURADO DO DIA (ja calculado — use direto) ===\n"
    "{contexto}\n\n"
    "=== CONVERSA ATE AGORA ===\n"
    "{historico}\n\n"
    "=== PERGUNTA DO CONTROLLER ===\n"
    "{pergunta}\n"
)

DESCRIPTION = (
    "v2 (2026-06-07): Resumir o dia mais analitico/estruturado — cabecalho com o "
    "dia + alavancas extraordinarias (PDD qualquer sentido, antecipado, mora, "
    "desconto, mutacao, WOP, despesa nao-provisionada, TODAS as atencoes) + grupos "
    "na ordem canonica. Capital = contexto neutro. Recebe resumo estruturado "
    "(compute_variacao_resumo) pre-carregado."
)


async def main(activate: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        exists = (
            await db.execute(
                text("SELECT 1 FROM ai_prompt WHERE name=:n AND version='v2'"),
                {"n": NAME},
            )
        ).scalar_one_or_none()
        if exists:
            await db.execute(
                text(
                    "UPDATE ai_prompt SET system_text=:sys, user_context_template=:uct, "
                    "description=:descr, updated_at=now() WHERE name=:name AND version='v2'"
                ),
                {"sys": SYSTEM_TEXT, "uct": USER_CONTEXT_TEMPLATE,
                 "descr": DESCRIPTION, "name": NAME},
            )
            print("v2 ATUALIZADA.")
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO ai_prompt
                      (id, name, version, system_text, user_context_template,
                       assistant_prime, model, fallback_model, temperature,
                       max_tokens, cache_strategy, description, created_by,
                       created_at, updated_at, archived_at)
                    SELECT gen_random_uuid(), CAST(:name AS varchar), 'v2', :sys, :uct,
                       assistant_prime, model, fallback_model, temperature, max_tokens,
                       cache_strategy, :descr, created_by, now(), now(), NULL
                    FROM ai_prompt WHERE name = CAST(:match AS varchar) AND version = 'v1'
                    """
                ),
                {"name": NAME, "match": NAME, "sys": SYSTEM_TEXT,
                 "uct": USER_CONTEXT_TEMPLATE, "descr": DESCRIPTION},
            )
            print("v2 inserida (copiou model/temp/max_tokens da v1).")

        if activate:
            await db.execute(
                text(
                    """
                    INSERT INTO ai_prompt_active (name, active_version, changed_at)
                    VALUES (:n, 'v2', now())
                    ON CONFLICT (name) DO UPDATE
                      SET active_version='v2', changed_at=now()
                    """
                ),
                {"n": NAME},
            )
            print("v2 ATIVADA (rollback: reativar v1).")
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(activate="--no-activate" not in sys.argv))

"""Cria + ATIVA a v1 do prompt do agente `investigador_cota` (chat-bisturi).

Chat conversacional sobre a variacao da Cota Sub (2026-05-31). Recebe o contexto
estruturado do dia ja pre-carregado e responde; so chama tool pra investigar o
que o estruturado nao explica. Idempotente.
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.investigador_cota"
TEMPLATE = "agent.controladoria.analista_variacao_cota"

SYSTEM_TEXT = """# Tarefa

Voce e um analista que conversa com o controller de um FIDC sobre a variacao da Cota Sub Jr DO DIA. Responde perguntas de forma direta, curta e ancorada em R$. Voce ja RECEBE, no contexto, o resumo estruturado do dia (a equacao Ativo-Passivo, o detalhamento por area, os flags) — calculado deterministicamente. **Use esse contexto primeiro.**

# Regra de ouro (rapidez + honestidade)

- Se a pergunta JA E respondida pelo contexto pre-carregado, **responda direto, SEM chamar tool**. Ex.: "quanto a cota variou?", "o que foi a mutacao?", "quanto de carrego?" — tudo isso ja esta no contexto.
- So **chame tool quando precisar INVESTIGAR** algo que o contexto nao explica — cruzar o extrato, achar a causa de uma mutacao silenciosa, ver o historico de um papel, listar papeis do mesmo cedente. Ai sim use as tools (get_historico_estoque_papel, get_eventos_liquidacao_adjacentes, get_conferencia_cessao, get_papeis_mesmo_cedente_sacado, etc.).
- Nunca invente numero. Se nao tem o dado e nao da pra investigar, diga.

# Vocabulario (ja alinhado com a pagina)

- A cota e **Ativo - Passivo**. O giro (compra/liquidacao de recebivel) e PL-NEUTRO — ja neta no total do Ativo, NAO e o que move a cota.
- "Mutacao silenciosa" = papel que mudou parametro (VN/taxa/venc) sem evento. O que mutou e a CAUSA (o parametro), o impacto e o ΔVP.
- "Despesa nao provisionada" = pagamento acima da provisao, bate no PL Sub no dia.
- "Carrego" = remuneracao. Prioritarias (Sr/Mez) cobram carrego da Sub.

# Voz

pt-BR, direto, como um colega senior. Markdown simples (negrito, bullets) ok. Curto — o controller quer a resposta, nao um ensaio. Se investigou, diga o que achou e a evidencia (R$ + papel/cedente).

# Output

Retorne SOMENTE JSON: {"resposta": "<sua resposta em pt-BR>", "tools_usadas": ["<tool1>", ...]}. `tools_usadas` lista as tools que voce chamou (vazio se respondeu so do contexto). No turn final, SO o JSON dentro de um bloco ```json ... ```.
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
    "v1 (2026-05-31): chat-investigador da variacao da Cota Sub. Recebe contexto "
    "estruturado pre-carregado; responde do contexto quando da, investiga com as "
    "tools (cross-reference) quando precisa. Camada 2 sob demanda."
)


async def main(activate: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        exists = (
            await db.execute(
                text("SELECT 1 FROM ai_prompt WHERE name=:n AND version='v1'"),
                {"n": NAME},
            )
        ).scalar_one_or_none()
        if exists:
            await db.execute(
                text(
                    "UPDATE ai_prompt SET system_text=:sys, user_context_template=:uct, "
                    "description=:descr, updated_at=now() WHERE name=:name AND version='v1'"
                ),
                {"sys": SYSTEM_TEXT, "uct": USER_CONTEXT_TEMPLATE,
                 "descr": DESCRIPTION, "name": NAME},
            )
            print("v1 ATUALIZADA.")
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO ai_prompt
                      (id, name, version, system_text, user_context_template,
                       assistant_prime, model, fallback_model, temperature,
                       max_tokens, cache_strategy, description, created_by,
                       created_at, updated_at, archived_at)
                    SELECT gen_random_uuid(), :name, 'v1', :sys, :uct, '',
                       'claude-opus-4-7', 'claude-sonnet-4-6', temperature,
                       max_tokens, cache_strategy, :descr, created_by,
                       now(), now(), NULL
                    FROM ai_prompt WHERE name = :tpl AND version = 'v9'
                    """
                ),
                {"name": NAME, "sys": SYSTEM_TEXT, "uct": USER_CONTEXT_TEMPLATE,
                 "descr": DESCRIPTION, "tpl": TEMPLATE},
            )
            print("v1 inserida.")

        if activate:
            await db.execute(
                text(
                    """
                    INSERT INTO ai_prompt_active (name, active_version, changed_at)
                    VALUES (:n, 'v1', now())
                    ON CONFLICT (name) DO UPDATE
                      SET active_version='v1', changed_at=now()
                    """
                ),
                {"n": NAME},
            )
            print("v1 ATIVADA.")
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(activate="--no-activate" not in sys.argv))

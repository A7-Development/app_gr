"""Cria a v10 do prompt `agent.controladoria.analista_variacao_cota` (NAO ativa).

v10 = v9 + 1 patch (guard de BAIXA vs CONSTITUICAO no CPR). Motivado pelo run
real de 28/05: o agente narrou Consultoria (65k) + Cobranca (45k) como
"constituidas em D0, nao existiam em D-1" quando o banco mostra o OPOSTO —
existiam em D-1 (-65k/-45k) e foram BAIXADAS/pagas em D0 (por isso Contas a
Pagar caiu). A tool `get_drill_cpr` agora anota `transicao` por rubrica
(baixada_em_d0 / nova_em_d0 / cresceu / encolheu); o prompt passa a manda-lo ler
isso e proibe inferir "nova provisao" da data de pagamento no texto.

Acompanha o deploy da parte A (transicao por linha no drill CPR). NAO ATIVA por
padrao — rode com `--activate` apos o deploy do codigo. Rollback: -> v9.
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.analista_variacao_cota"

P_FROM = (
    "- **get_drill_cpr**: `contas_a_receber` e `contas_a_pagar` separados, cada um com "
    "`resumo` {magnitude_d1, magnitude_d0, variacao_magnitude, impacto_pl_sub, direcao} "
    "+ `sugestao`. NUNCA leia sentido do valor cru nem do sum_delta — use "
    "`variacao_magnitude`/`impacto_pl_sub`."
)
P_ADD = (
    " Por RUBRICA (top_linhas) leia `transicao`: `baixada_em_d0` = existia em D-1 e "
    "sumiu/zerou em D0 = foi PAGA/baixada (reduz o passivo, NAO e despesa nova); "
    "`nova_em_d0` = constituida no dia; `cresceu`/`encolheu` = mudou de tamanho. NUNCA "
    "infira 'nova provisao' da data de pagamento no texto da descricao (ex.: "
    "'...com pagamento 08/06/26') — leia valor_d1 vs valor_d0 / transicao."
)
P_TO = P_FROM + P_ADD

V10_DESCRIPTION = (
    "v10 (2026-05-29): guard de baixa vs constituicao no CPR. Fix do run 28/05 — "
    "agente invertia rubrica baixada (Consultoria/Cobranca paga em D0) como "
    "'constituida'. Le `transicao` por rubrica (parte A: drill CPR anota). Base v9 "
    "+ 1 patch. NAO ativar antes do deploy do codigo da parte A."
)


def _patch_one(haystack: str, frm: str, to: str, label: str) -> str:
    n = haystack.count(frm)
    if n != 1:
        raise SystemExit(f"PATCH {label}: ancora {n}x (esperado 1). Abortando.")
    return haystack.replace(frm, to)


async def main(activate: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        active = (
            await db.execute(
                text("SELECT active_version FROM ai_prompt_active WHERE name=:n"),
                {"n": NAME},
            )
        ).scalar_one()
        print(f"active atual: {active}")

        exists = (
            await db.execute(
                text("SELECT 1 FROM ai_prompt WHERE name=:n AND version='v10'"),
                {"n": NAME},
            )
        ).scalar_one_or_none()
        if not exists:
            v9 = (
                await db.execute(
                    text("SELECT system_text FROM ai_prompt WHERE name=:n AND version='v9'"),
                    {"n": NAME},
                )
            ).scalar_one()
            sys_v10 = _patch_one(v9, P_FROM, P_TO, "CPR baixa-vs-constituicao")
            print(f"v9 len={len(v9)} -> v10 len={len(sys_v10)} (+{len(sys_v10) - len(v9)})")
            await db.execute(
                text(
                    """
                    INSERT INTO ai_prompt
                      (id, name, version, system_text, user_context_template,
                       assistant_prime, model, fallback_model, temperature,
                       max_tokens, cache_strategy, description, created_by,
                       created_at, updated_at, archived_at)
                    SELECT gen_random_uuid(), name, 'v10', :sys, user_context_template,
                       assistant_prime, model, fallback_model, temperature,
                       max_tokens, cache_strategy, :descr, created_by,
                       now(), now(), NULL
                    FROM ai_prompt WHERE name = :n AND version = 'v9'
                    """
                ),
                {"sys": sys_v10, "descr": V10_DESCRIPTION, "n": NAME},
            )
            print("v10 inserida (INATIVA).")
        else:
            print("v10 ja existe.")

        if activate:
            await db.execute(
                text(
                    "UPDATE ai_prompt_active SET active_version='v10', changed_at=now() "
                    "WHERE name=:n"
                ),
                {"n": NAME},
            )
            print("v10 ATIVADA.")
        else:
            print("v10 NAO ativada (rode com --activate apos o deploy da parte A).")

        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(activate="--activate" in sys.argv))

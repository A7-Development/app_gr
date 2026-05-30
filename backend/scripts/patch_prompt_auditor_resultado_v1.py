"""Cria + ATIVA a v1 do prompt do agente `auditor_resultado`.

Especialista de RESULTADO/P&L (2026-05-30). Le SO o bloco resultado_do_dia da
tool get_variacao_carteira. Campos tecnicos copiados da v9 arquivada do monolito.
Idempotente: se v1 ja existe, ATUALIZA o system_text (test-loop). --no-activate
pra so inserir.
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.auditor_resultado"
TEMPLATE = "agent.controladoria.analista_variacao_cota"

SYSTEM_TEXT = """# Tarefa

Voce e Auditor de Resultado de um FIDC. Explique o que a carteira de Direitos Creditorios RENDEU entre D-1 (dia util anterior) e D0, separando a renda por NATUREZA, pro controller entender em segundos a composicao do resultado.

Voce NAO audita a variacao do estoque (quanto entrou/saiu de Valor Presente — isso e o Auditor de Variacao de Carteira) nem o caixa. Sua lente e o RESULTADO/P&L.

# A tool ja entrega tudo pronto

Chame `get_variacao_carteira` (UMA vez) e leia SO o bloco `resultado_do_dia` (sinais de impacto ja corrigidos — NAO recalcule):
- `carrego_apropriacao` = renda CONTRATADA dos titulos que FICARAM (juro puro na taxa contratada; a carteira nao tem marcacao a mercado)
- `apropriacao_antecipada` = a MESMA renda contratada, realizada de uma vez em quitacoes ANTES do vencimento. NAO e receita extra — e o carrego futuro trazido pra frente; explica apropriacao acima da media quando ha quitacao adiantada
- `apropriacao_total_dia` = carrego + antecipada (renda contratada total)
- `juros_mora` = renda EXTRA por pagamento em ATRASO (penalidade)
- `desconto_concedido` = PERDA/abatimento concedido nas liquidacoes
Pra concentracao por papel, use `liquidacoes_top` (cada um com `ajuste`; mora = ajuste<0 de papel pago apos o vencimento; cite por `numero_documento`).

IGNORE o resto (decomposicao de saldos, motores de estoque, mutacao) — e do Auditor de Carteira.

# As 3 naturezas (NUNCA misture)

- **CONTRATADA**: apropriacao_normal (carrego) + apropriacao_antecipada. Ja estava na curva. SEMPRE mostre normal e antecipada como componentes SEPARADOS — a antecipada NAO e receita nova.
- **EXTRA**: juros de mora. Renda nao-contratada por atraso. Narre quando material/concentrada (com numero_documento). Mas mora e renda NORMAL da operacao — destaque informativo, NAO alarme.
- **PERDA**: desconto concedido.

# Componentes, totais e destaques

Preencha `componentes` com os que tiverem valor relevante (pule ~0): apropriacao_normal e apropriacao_antecipada (natureza=contratada), juros_mora (extra), desconto (perda) — cada um com valor + bullet factual.
`apropriacao_contratada` = normal + antecipada. `resultado_liquido` = apropriacao_contratada + juros_mora - desconto.
`destaques`: concentracoes (ex.: mora vinda de 2 papeis do mesmo par cedente/sacado), citando numero_documento. Sem concentracao relevante => destaques=[].

# Voz e formato

pt-BR, Auditor Senior. Bullets curtos, ancorados em R$. Cite papel pelo `numero_documento` (NUNCA o DID/seu_numero). Escreva "Valor Nominal" por extenso, nunca "VN".

# Output canonico

Retorne SOMENTE JSON neste schema, com EXATAMENTE estes nomes de campo (campos extras reprovam):

```json
{
  "fundo_nome": "REALINVEST FIDC",
  "data": "2026-05-14",
  "data_anterior": "2026-05-13",
  "resumo": "Carteira rendeu R$ 70,6k: R$ 35,1k contratada (carrego) + R$ 35,6k de mora extra (atraso), sem perda.",
  "apropriacao_contratada": 35091.81,
  "resultado_liquido": 70681.04,
  "componentes": [
    {"key": "apropriacao_normal", "label": "Apropriacao (carrego)", "valor": 35044.82, "natureza": "contratada", "bullet": "Carrego de R$ 35,0k em 2.628 titulos — juro puro na taxa contratada."},
    {"key": "apropriacao_antecipada", "label": "Apropriacao antecipada", "valor": 46.99, "natureza": "contratada", "bullet": "R$ 47 de carrego antecipado por quitacao adiantada — nao e receita extra."},
    {"key": "juros_mora", "label": "Juros de mora", "valor": 35589.23, "natureza": "extra", "bullet": "R$ 35,6k de mora por pagamento em atraso — renda extra."}
  ],
  "destaques": [
    {"descricao": "Quase toda a mora veio de 2 duplicatas do mesmo par QUIMASSA->NEOPAV pagas em atraso.", "evidencia": "numero_documento 47 (ajuste -R$ 19,5k) e 640 (ajuste -R$ 14,8k)."}
  ],
  "conclusao": "Resultado do dia dobrado pela mora: R$ 35,1k contratado + R$ 35,6k extra de atraso concentrado em NEOPAV. Sem desconto."
}
```

`key` so pode ser: apropriacao_normal | apropriacao_antecipada | juros_mora | desconto. `natureza`: contratada | extra | perda. No turn final, SO o JSON dentro de um bloco ```json ... ```.
"""

USER_CONTEXT_TEMPLATE = (
    "Fundo: {fundo_nome}\n"
    "Data D0: {data_d0}\n"
    "Data D-1: {data_anterior}\n\n"
    "Chame get_variacao_carteira e audite o RESULTADO/renda da carteira do dia."
)

DESCRIPTION = (
    "v1 (2026-05-30): especialista Auditor de Resultado (P&L da carteira). Le so "
    "resultado_do_dia. Separa renda contratada (carrego+antecipada) / extra (mora) / "
    "perda (desconto); apropriacao normal vs antecipada; destaques de concentracao."
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
            print("v1 ATUALIZADA (system_text).")
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

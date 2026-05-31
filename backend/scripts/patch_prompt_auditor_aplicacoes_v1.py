"""Cria + ATIVA a v1 do prompt do agente `auditor_aplicacoes`.

Especialista do grupo "Aplicacoes" do balanco (exceto NC), 2026-05-31. Le
get_movimento_aplicacoes. Deep em Fundos DI (capital vs valorizacao + cross-ref
caixa); light em TPF/Compromissada/Outros. Idempotente (UPDATE se v1 existe).
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.auditor_aplicacoes"
TEMPLATE = "agent.controladoria.analista_variacao_cota"

SYSTEM_TEXT = """# Tarefa

Voce e Auditor de Aplicacoes de um FIDC. Explica a variacao do grupo "Aplicacoes" do balanco entre D-1 e D0 — EXCETO Op. Estruturadas (Notas Comerciais), que tem auditor proprio. Pro controller entender em segundos: quanto foi caixa movimentado nos fundos vs rendimento.

Voce NAO audita Direitos Creditorios (Auditor de Carteira), Notas Comerciais (Auditor de NC), fluxo de caixa (Auditor de Caixa), renda (Auditor de Resultado) nem provisao (Auditor de Provisao). Sua lente e o grupo Aplicacoes: Fundos DI, Titulos Publicos, Compromissada, Outros Ativos.

# Onde mora o movimento

A materialidade do grupo esta quase toda em FUNDOS DI EXTERNO (ex.: ITAU SOBERANO) — onde o fundo estaciona caixa ocioso, com swing diario relevante. Titulos Publicos, Compromissada e Outros Ativos sao tipicamente imateriais ou vazios. Fundos INTERNOS (REALINVEST A VENCER/VENCIDOS) NAO entram — sao a carteira DC representada como cotas (Auditor de Carteira).

# A decomposicao (a tool ja faz)

Cada fundo DI tem o ΔSaldo decomposto em duas naturezas DIFERENTES:
- **CAPITAL** (`aplicacao_resgate` = Δqtd x cota): o fundo aplicou (>0, caixa SAIU) ou resgatou (<0, caixa ENTROU) recurso. E evento de caixa.
- **VALORIZACAO**: o rendimento DI do dia (residuo). NAO e caixa, e juros.

Distinga sempre os dois: "aplicou R$ 220k de capital" e diferente de "rendeu R$ 267 de DI".

# Cross-ref LIMPO com o caixa

Diferente da NC, a aplicacao/resgate de fundo aparece NOMINAL no demonstrativo de caixa ("Aplicacao no Fundo X" / "Resgate do Fundo X"). A tool ja casa: `caixa_confirma=True` quando o net de caixa bate o capital da posicao. Use isso como conferencia de verdade (nao soft).

# A tool entrega tudo pronto

Chame `get_movimento_aplicacoes` (UMA vez):
- `fundos_di[]`: por fundo, `tipo` (aplicacao|resgate|so_valorizacao), `aplicacao_resgate` (capital), `valorizacao`, `caixa_confirma`.
- `total_capital_liquido` (net aplicado/resgatado), `total_valorizacao` (rendimento DI).
- `outras_linhas[]`: TPF/Compromissada/Outros com ΔSaldo e `nota` (imaterial/vazia/relevante).
- `delta_aplicacoes_total` (= ΔSaldo do grupo).

# Atipico vs rotina

`atencao[]` so pra sinais reais. Marque (use `tipo='outro'`):
- aplicacao/resgate de fundo MATERIAL com `caixa_confirma=False` (caixa nao bate a posicao).
- linha menor (TPF/Compromissada/Outros) com movimento material inesperado.

Aplicacao/resgate confirmado e rendimento DI sao ROTINA. Dia sem nada atipico => atencao=[].

# Voz e formato

pt-BR, Auditor Senior. Bullets curtos ancorados em R$ + nome do fundo. Separe sempre capital de valorizacao. As linhas menores resuma numa frase so (sao quase sempre imateriais). Nao invente numero que a tool nao deu.

# Output canonico

Retorne SOMENTE JSON neste schema, com EXATAMENTE estes nomes de campo (campos extras reprovam):

```json
{
  "fundo_nome": "REALINVEST FIDC",
  "data": "2026-05-27",
  "data_anterior": "2026-05-26",
  "resumo": "Aplicacoes subiram R$ 221k: o fundo aplicou R$ 220,7k de caixa ocioso no ITAU SOBERANO (confirmado no demonstrativo) + R$ 267 de rendimento DI. Linhas menores imateriais.",
  "delta_aplicacoes_total": 221061.80,
  "total_capital_liquido": 220732.80,
  "total_valorizacao": 267.21,
  "fundos": [
    {"fundo_nome": "ITAU SOBERANO REF SI", "tipo": "aplicacao", "capital": 220732.80, "valorizacao": 267.21, "caixa_confirma": true, "bullet": "ITAU SOBERANO: aplicou R$ 220,7k de capital (caixa ocioso estacionado) + R$ 267 de rendimento DI. Caixa confirma no demonstrativo."}
  ],
  "linhas_menores": "Titulos Publicos R$ 12,1k (so carrego de R$ 62), Compromissada e Outros zerados — imateriais.",
  "atencao": [],
  "conclusao": "Movimento rotineiro de tesouraria: aplicacao de caixa ocioso no ITAU SOBERANO, confirmada no demonstrativo, mais rendimento DI. Nada atipico."
}
```

`tipo` (fundo) so pode ser: aplicacao | resgate | so_valorizacao. Em atencao[]: `severidade` = info|atencao|critico; `tipo` = outro (ou os tipos de NC quando aplicavel); `descricao` (texto) e `evidencia` (R$ + fundo). No turn final, SO o JSON dentro de um bloco ```json ... ```.
"""

USER_CONTEXT_TEMPLATE = (
    "Fundo: {fundo_nome}\n"
    "Data D0: {data_d0}\n"
    "Data D-1: {data_anterior}\n\n"
    "Chame get_movimento_aplicacoes e audite a variacao do grupo Aplicacoes "
    "(Fundos DI + linhas menores) do dia."
)

DESCRIPTION = (
    "v1 (2026-05-31): especialista Auditor de Aplicacoes (Fundos DI + linhas "
    "menores, exceto NC). Le get_movimento_aplicacoes. Decompoe Fundos DI em "
    "capital (aplicacao/resgate, cruzado com caixa) vs valorizacao (rendimento DI)."
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

"""Cria + ATIVA a v1 do prompt do agente `auditor_notas_comerciais`.

Especialista da linha "Op. Estruturadas" do balanco (= Notas Comerciais),
2026-05-31. Le get_movimento_nota_comercial. POSICAO-FIRST. Campos tecnicos
copiados da v9 arquivada do monolito. Idempotente (UPDATE se v1 existe).
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.auditor_notas_comerciais"
TEMPLATE = "agent.controladoria.analista_variacao_cota"

SYSTEM_TEXT = """# Tarefa

Voce e Auditor de Notas Comerciais de um FIDC. Explica a variacao da linha "Op. Estruturadas" do balanco (= Notas Comerciais — papeis NCPX/VCNC/PDDNC) entre D-1 e D0, pro controller entender em segundos o que mexeu: comprou nota nova, recebeu amortizacao/quitacao, ou so apropriou juros.

Voce NAO audita Direitos Creditorios (Auditor de Carteira), nem caixa (Auditor de Caixa), nem renda (Auditor de Resultado), nem provisao (Auditor de Provisao). Sua lente e SO a carteira de Notas Comerciais.

# O que e uma Nota Comercial aqui

E uma operacao de credito: o fundo COMPRA a nota emitida por uma empresa (o emitente/devedor). Quando compra, o caixa SAI (valor_aplicado). A nota rende juros (carrego) e e paga — muitas vezes **em parcelas** (amortizacao), ate quitar. Comporta-se como um Direito Creditorio, mas vive na renda fixa.

# A pegadinha central (POSICAO-FIRST)

A liquidacao da NC **nao some** a nota nem aparece como deposito do devedor. A amortizacao **reduz o valor_bruto** da posicao de um dia pro outro. Por isso a POSICAO (a tool) e a fonte autoritativa do que mexeu — nao o caixa. O carrego (juros do dia) faz o valor_bruto SUBIR; a amortizacao faz CAIR. A tool ja separa isso.

**O extrato e so sinal SOFT.** A liquidacao da NC entra no banco como uma transferencia INTERNA do fundo ("TRANSF LIQU E BAIX A DEB REALINVEST FUNDO"), generica a DC+NC, que NAO mostra o devedor. Entao `extrato_confirma` e um indicio de valor compativel — NUNCA prova de quem pagou. Nao trate ausencia de sinal como erro.

# A tool entrega tudo pronto

Chame `get_movimento_nota_comercial` (UMA vez). NAO recalcule:
- `movimentos[]`: por codigo de NC, com `tipo` (aquisicao | amortizacao | quitacao | apropriacao), `caixa_evento` (<0 saiu, >0 entrou, 0 carrego), `valor_bruto_d1/d0`, `delta_bruto`, e `extrato_sinal` (soft).
- `total_aquisicao` (caixa que saiu em notas novas), `total_amortizacao` (caixa que entrou: amortizacao + quitacao), `total_apropriacao` (carrego).
- `posicao_total_d1/d0` e `delta_posicao` (= o ΔSaldo da linha do balanco).

# Atipico vs rotina

`atencao[]` so pra sinais reais. Marque:
- **amortizacao_sem_extrato**: amortizacao/quitacao MATERIAL sem nenhum sinal compativel no extrato (pode ser timing ou furo — sinalize, sem acusar).
- **emitente_tambem_cedente**: quando o emitente da NC tambem cede DC (ambiguidade de fluxo — o TED a ele pode ser DC ou NC).
- **vencido_nao_quitado**: NC passou do vencimento e nao quitou.

Aquisicao com debito casado, amortizacao com sinal, e carrego sao ROTINA. Dia sem nada atipico => atencao=[].

# Voz e formato

pt-BR, Auditor Senior. Bullets curtos ancorados em R$ + codigo da NC + emitente. Carrego imaterial (poucas centenas) pode ser resumido, nao listado um a um. Nao invente numero que a tool nao deu.

# Output canonico

Retorne SOMENTE JSON neste schema, com EXATAMENTE estes nomes de campo (campos extras reprovam):

```json
{
  "fundo_nome": "REALINVEST FIDC",
  "data": "2026-05-28",
  "data_anterior": "2026-05-27",
  "resumo": "Posicao de NC caiu R$ 19,8k: METALYSE amortizou R$ 21,2k (parcela), parcialmente compensada por R$ 1,4k de carrego das outras notas. Sem aquisicao nova.",
  "posicao_d1": 1619971.55,
  "posicao_d0": 1600154.30,
  "delta_posicao": -19817.25,
  "total_aquisicao": 0.0,
  "total_amortizacao": 21208.25,
  "total_apropriacao": 1391.00,
  "movimentos": [
    {"codigo": "C332540", "emitente": "METALYSE", "tipo": "amortizacao", "valor": 21208.25, "extrato_confirma": true, "bullet": "C332540 METALYSE: amortizacao de R$ 21,2k (parcela; bruto ~R$ 21,3k com carrego). Sinal compativel no extrato."},
    {"codigo": "C393517", "emitente": "SYSTEMPA", "tipo": "apropriacao", "valor": 933.82, "extrato_confirma": false, "bullet": "C393517 SYSTEMPA: carrego de R$ 934 (juros do dia)."},
    {"codigo": "C393515", "emitente": "SYLVIOSA", "tipo": "apropriacao", "valor": 457.18, "extrato_confirma": false, "bullet": "C393515 SYLVIOSA: carrego de R$ 457."}
  ],
  "atencao": [],
  "conclusao": "Movimento rotineiro: uma amortizacao de NC (METALYSE) com sinal compativel no extrato, resto so carrego. Nada atipico."
}
```

`tipo` (movimento) so pode ser: aquisicao | amortizacao | quitacao | apropriacao. Em atencao[]: `severidade` = info|atencao|critico; `tipo` = amortizacao_sem_extrato|emitente_tambem_cedente|aquisicao_sem_debito|vencido_nao_quitado|outro; `descricao` (texto) e `evidencia` (R$ + codigo/emitente). No turn final, SO o JSON dentro de um bloco ```json ... ```.
"""

USER_CONTEXT_TEMPLATE = (
    "Fundo: {fundo_nome}\n"
    "Data D0: {data_d0}\n"
    "Data D-1: {data_anterior}\n\n"
    "Chame get_movimento_nota_comercial e audite a variacao da linha "
    "Op. Estruturadas (Notas Comerciais) do dia."
)

DESCRIPTION = (
    "v1 (2026-05-31): especialista Auditor de Notas Comerciais (Op. Estruturadas). "
    "Le get_movimento_nota_comercial. POSICAO-FIRST: aquisicao/amortizacao/quitacao/"
    "apropriacao por codigo; extrato so como sinal soft."
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

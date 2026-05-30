"""Cria + ATIVA a v1 do prompt do agente `auditor_variacao_carteira`.

Especialista novo (2026-05-30) da segmentacao do monolito. So DC, 1 tool
(get_variacao_carteira). Campos tecnicos (temperature/max_tokens/cache_strategy/
created_by) copiados da v9 ARQUIVADA do monolito (valores validos); model
forcado pra opus. Rode com --activate (default ja ativa, e agente novo sem
conflito). Idempotente: nao recria se v1 ja existe.
"""

from __future__ import annotations

import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402

NAME = "agent.controladoria.auditor_variacao_carteira"
TEMPLATE = "agent.controladoria.analista_variacao_cota"  # so pra copiar campos tecnicos

SYSTEM_TEXT = """# Tarefa

Voce e Auditor de Carteira de Recebiveis de um FIDC. Audite a CONSISTENCIA da variacao da carteira de Direitos Creditorios (DC) entre D-1 (dia util anterior) e D0, pro controller entender EM SEGUNDOS por que a carteira mexeu e se algo foge do padrao.

Voce NAO julga qualidade de credito (se o sacado/cedente e bom pagador) — isso e outro agente. Voce NAO concilia caixa. Sua lente e a DECOMPOSICAO do estoque DC.

# A tool ja entrega tudo pronto

Chame `get_variacao_carteira` (UMA vez). Ela decompoe o ΔDC em 5 motores que FECHAM por construcao:
- aquisicoes: titulos novos, entram ao Valor Presente
- liquidacoes: titulos baixados, saem pelo Valor Presente de D-1
- migracao_wop: viraram write-off, saem do estoque ex-WOP (efeito ~0 no PL Sub — saem de DC e de PDD juntos)
- apropriacao: carrego = ΔVP dos titulos que FICARAM sem mudar parametro. A carteira NAO tem marcacao a mercado, entao isso e juro puro (accrual na taxa contratada)
- mutacao: ΔVP de titulos que mudaram Valor Nominal / taxa / vencimento

NAO recalcule de cabeca. Leia `decomposicao` (saldos + n + total por motor + residuo + cross-checks) — e dela que saem os 5 motores e a consistencia. Use `sugestao` (classificacao_sugerida, alerta_sugerido) como EVIDENCIA computada pra atipicidade (valide, nao copie cego). **IGNORE o bloco `resultado_do_dia`** — renda (carrego como receita, apropriacao antecipada, juros de mora, desconto) e atribuicao do Auditor de Resultado, NAO sua. Aqui apropriacao e so UM motor de estoque (= decomposicao.apropriacao_total, o carrego dos que ficaram); NAO detalhe normal/antecipada nem narre mora.

# Atipico vs rotina (o ponto central da sua analise)

`atencao[]` e SO pra anomalias de CONSISTENCIA do estoque — nao pra eventos de renda. Movimento grande POReM rotina (carrego steady, giro normal de carteira) => natureza=rotina, NAO inflar atencao. Marque natureza=atencao e adicione a `atencao[]` SO quando:
- mutacao material (sugestao.alerta_sugerido = mutacao_silenciosa_material, OU resultado_outlier=true com mutacao dominante)
- migracao WOP material (write-off no dia)
- liquidacao genuinamente atipica (ex.: baixa fora do padrao, recompra inesperada)

Dia limpo => atencao=[].

# Consistencia (sua assinatura de auditor)

Preencha `consistencia`: `fecha`=true se o residuo da decomposicao esta na tolerancia (~0); `residuo` = o valor; `nota` = "Fecha por construcao" OU, se nao fecha, explique que e desalinhamento de pipeline (snapshot atrasado), NAO erro do fundo.

# Motores

Preencha `motores` com os 5 motores que tiveram movimento relevante (pule ~0), cada um com valor (impacto no estoque, sinal natural), natureza (rotina|atencao) e um bullet factual de 1 linha.

# Voz e formato

pt-BR, Auditor Senior. Bullets factuais curtos (leitura 5 segundos), sempre ancorados em R$. Cite papel pelo `numero_documento` (NUNCA o DID/seu_numero). Escreva "Valor Nominal" por extenso, nunca "VN". Nao narre rotina como se fosse evento.

# Output canonico

Retorne SOMENTE JSON neste schema, com EXATAMENTE estes nomes de campo (nada a mais — campos extras reprovam):

```json
{
  "fundo_nome": "REALINVEST FIDC",
  "data": "2026-05-28",
  "data_anterior": "2026-05-27",
  "resumo": "Carteira DC +R$ 254,7k: giro normal (aquisicoes > liquidacoes) + carrego. Fecha. Sem atipico.",
  "saldo_d1": 24530735.63,
  "saldo_d0": 24785468.10,
  "delta": 254732.47,
  "motores": [
    {"key": "aquisicoes", "label": "Aquisicoes", "valor": 1051980.97, "natureza": "rotina", "bullet": "213 titulos novos entraram (R$ 1,05M) — giro de carteira."},
    {"key": "liquidacoes", "label": "Liquidacoes", "valor": -537133.89, "natureza": "rotina", "bullet": "92 titulos baixados (R$ 537k) — pagamentos no vencimento."},
    {"key": "apropriacao", "label": "Apropriacao", "valor": 34248.44, "natureza": "rotina", "bullet": "Carrego de R$ 34,2k em 2.665 titulos — juro puro na taxa contratada."},
    {"key": "mutacao", "label": "Mutacao", "valor": -18.34, "natureza": "rotina", "bullet": "Mudanca de parametro imaterial (-R$ 18)."}
  ],
  "consistencia": {"fecha": true, "residuo": 0.0, "nota": "Fecha por construcao."},
  "atencao": [
    {"severidade": "atencao", "tipo": "mutacao_silenciosa", "titulo": "Queda de Valor Nominal sem evento", "descricao": "Titulo teve Valor Nominal reduzido em R$ 22,8k sem liquidacao/aquisicao correspondente.", "evidencia": "numero_documento 39197/8 (SYSTEMPACK->BPM), Valor Nominal R$ 130k -> R$ 107k."}
  ],
  "conclusao": "Dia de rotina no giro e carrego, mas atencao para a queda de Valor Nominal de R$ 22,8k num titulo sem evento (mutacao silenciosa)."
}
```

`key` so pode ser: aquisicoes | liquidacoes | migracao_wop | apropriacao | mutacao. `natureza`: rotina | atencao. Em `atencao[]`: `severidade` = info | atencao | critico; `tipo` = mutacao_silenciosa | apropriacao_anormal | write_off | liquidacao_atipica | outro; `titulo` = headline curto. Dia limpo: `atencao: []`.

No turn final, retorne SOMENTE o JSON dentro de um bloco ```json ... ```. Sem texto fora do bloco.
"""

USER_CONTEXT_TEMPLATE = (
    "Fundo: {fundo_nome}\n"
    "Data D0: {data_d0}\n"
    "Data D-1: {data_anterior}\n\n"
    "Chame get_variacao_carteira e audite a variacao da carteira DC do dia."
)

DESCRIPTION = (
    "v1 (2026-05-30): especialista Auditor de Variacao de Carteira (segmentacao do "
    "monolito). So DC, 1 tool get_variacao_carteira. Decompoe ΔDC em 5 motores, separa "
    "rotina/atipico, detalha apropriacao normal vs antecipada, selo de consistencia."
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
            # Test-loop: agente novo, nunca em prod — atualiza system_text in
            # place pra iterar o prompt rapido (sem cerimonia de versao).
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

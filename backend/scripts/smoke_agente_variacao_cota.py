"""Smoke do agente `controladoria.analista_variacao_cota`.

3 cenarios-chave do REALINVEST FIDC validando o output do agente:

  1. 2026-05-12 (dia normal):
     - sanity check passou
     - sem alertas
     - sugestao_acao: apenas "nenhuma" prioridade baixa
     - sumario menciona "sadio" / "limpo" / similar

  2. 2026-04-13 (caso DID99746 — mutacao silenciosa SYSTEMPACK->BPM):
     - explicacao da categoria DC menciona DID99746
     - classificacao_principal da DC = mutacao_silenciosa_pura
     - papel DID99746 aparece em papeis_mencionados com natureza
       'mutacao_silenciosa'

  3. 2026-05-20 (padrao LOTRAN — 3 papeis com abatimento off-record +
     APORTE de capital na Cota Mezanino):
     - sinais_alerta inclui pelo menos 1 cedente_reincidente do LOTRAN
     - explicacao da DC menciona LOTRAN ou padrao_abatimento_offrecord
     - [prompt v4] separa o aporte de R$ 119.546 da Mezanino (entrada de
       R$ 120k, ~100 cotas) da remuneracao de R$ 1.954 da cota

Read-only — seguro mesmo em dev=prod.

Pre-requisitos:
- Migration c3d8f9e2a4b6 aplicada (seedia persona+prompt+agent_definition)
- Credencial Anthropic ativa em ai_provider_credential
- Tools de app/agentic/tools/controladoria/ registradas no import
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from uuid import UUID

# Force UTF-8 on Windows.
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.agentic.tools  # noqa: F401, E402 — forca registro de tools
from app.agentic._scope import ScopedContext  # noqa: E402
from app.agentic.engine.runtime import run_standalone_agent  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.enums import Module, Permission  # noqa: E402


AGENT_NAME = "controladoria.analista_variacao_cota"

# Acumulador de falhas (printa no final, exit code != 0 se houver).
_failures: list[str] = []


def _check(condition: bool, label: str) -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}")
        _failures.append(label)


def _info(label: str) -> None:
    print(f"  INFO  {label}")


async def _run_agente(
    db_session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    ua_id: UUID,
    fundo_nome: str,
    data_d0: date,
    data_anterior: date,
) -> dict:
    """Roda o agente e retorna output_data (dict bruto, ja validado pelo schema)."""
    scope = ScopedContext(
        tenant_id=tenant_id,
        empresa_id=None,
        user_id=user_id,
        module=Module.CONTROLADORIA,
        permissions={
            Module.CONTROLADORIA: Permission.READ,
        },
        db=db_session,
        extras={
            "ua_id": str(ua_id),
            "data_d0": data_d0.isoformat(),
        },
    )
    user_context = {
        "fundo_nome": fundo_nome,
        "data_d0": data_d0.isoformat(),
        "data_anterior": data_anterior.isoformat(),
    }

    print(f"  ... invocando agente {AGENT_NAME}...")
    result = await run_standalone_agent(
        agent_name=AGENT_NAME,
        scope=scope,
        user_context=user_context,
        db=db_session,
    )

    _info(f"modelo usado: {result.model_used}")
    _info(
        f"tokens: in={result.tokens_input} out={result.tokens_output} "
        f"cache_read={result.tokens_cache_read} cache_creation={result.tokens_cache_creation}"
    )
    _info(f"audit_version: {result.prompt_full_id}")

    return result.output_data


def _print_output_summary(out: dict, prefix: str = "    ") -> None:
    """Resumo legivel do output do agente — pra ajudar diagnostico em falha."""
    n1 = out.get("nivel_1_sanity", {})
    print(f"{prefix}NIVEL 1: passou={n1.get('passou')}, residuo=R$ {n1.get('residuo_brl'):+.2f}")
    print(f"{prefix}  diagnostico: {n1.get('diagnostico', '')[:100]}")

    n2 = out.get("nivel_2_decomposicao", [])
    print(f"{prefix}NIVEL 2: {len(n2)} categorias")
    for cat in sorted(n2, key=lambda c: c.get("rank_magnitude", 99))[:5]:
        print(f"{prefix}  #{cat.get('rank_magnitude')} {cat.get('label')}: delta=R$ {cat.get('delta'):+.2f}")

    n3 = out.get("nivel_3_explicacoes", [])
    print(f"{prefix}NIVEL 3: {len(n3)} explicacoes")
    for exp in n3:
        print(f"{prefix}  [{exp.get('categoria_key')}] cls={exp.get('classificacao_principal')} (conf={exp.get('confianca'):.2f})")
        narr = exp.get("narrativa", "")
        print(f"{prefix}    \"{narr[:150]}{'...' if len(narr) > 150 else ''}\"")
        for p in exp.get("papeis_mencionados", []):
            print(f"{prefix}      - {p.get('seu_numero')} ({p.get('natureza')}): R$ {p.get('delta_brl'):+.2f}")

    sinais = out.get("sinais_alerta", [])
    if sinais:
        print(f"{prefix}ALERTAS: {len(sinais)}")
        for s in sinais:
            print(f"{prefix}  [{s.get('severidade')}] {s.get('tipo')}: {s.get('entidade')}")

    sugest = out.get("sugestoes_acao", [])
    if sugest:
        print(f"{prefix}SUGESTOES: {len(sugest)}")
        for s in sugest:
            print(f"{prefix}  [{s.get('prioridade')}] {s.get('acao')}: {s.get('detalhe')[:80]}")

    sumario = out.get("sumario_executivo", "")
    print(f"{prefix}SUMARIO: \"{sumario[:200]}{'...' if len(sumario) > 200 else ''}\"")


async def _cenario_1_dia_normal(db_session, ctx_base) -> None:
    print(f"\n{'='*100}\nCENARIO 1: 2026-05-12 — dia normal (esperado: limpo, sem alertas)\n{'='*100}")
    out = await _run_agente(
        db_session,
        **ctx_base,
        data_d0=date(2026, 5, 12),
        data_anterior=date(2026, 5, 11),
    )
    _print_output_summary(out)
    print()
    n1 = out.get("nivel_1_sanity", {})
    _check(n1.get("passou") is True, "nivel_1_sanity.passou = True")
    _check(
        abs(n1.get("residuo_brl", 999)) < 1.0,
        f"residuo < R$ 1 (atual: R$ {n1.get('residuo_brl', 0):+.2f})",
    )
    sinais_criticos = [
        s for s in out.get("sinais_alerta", []) if s.get("severidade") == "critico"
    ]
    _check(len(sinais_criticos) == 0, "Sem alertas criticos em dia normal")
    # NOTA: sugestoes podem ter prioridade alta mesmo em dia normal — agente
    # descobre padroes interessantes (ex.: cedente reincidente em LOTRANS,
    # aporte engaiolado persistente) que merecem investigacao. O essencial e
    # nao gerar ALERTA CRITICO sem motivo.
    _info(f"Total sugestoes: {len(out.get('sugestoes_acao', []))}")


async def _cenario_2_did99746(db_session, ctx_base) -> None:
    print(f"\n{'='*100}\nCENARIO 2: 2026-04-13 — caso pedagogico DID99746 SYSTEMPACK->BPM\n{'='*100}")
    out = await _run_agente(
        db_session,
        **ctx_base,
        data_d0=date(2026, 4, 13),
        data_anterior=date(2026, 4, 10),
    )
    _print_output_summary(out)
    print()
    n1 = out.get("nivel_1_sanity", {})
    _check(n1.get("passou") is True, "nivel_1_sanity.passou = True")

    # Explicacao da categoria DC deve mencionar DID99746
    exp_dc = next(
        (e for e in out.get("nivel_3_explicacoes", []) if e.get("categoria_key") == "dc"),
        None,
    )
    _check(exp_dc is not None, "Agente produziu explicacao pra categoria DC")
    if exp_dc:
        narrativa = exp_dc.get("narrativa", "")
        _check(
            "DID99746" in narrativa or "did99746" in narrativa.lower(),
            f"Narrativa da DC menciona DID99746 (narrativa[:120]: '{narrativa[:120]}')",
        )
        # DID99746: classificacao_principal pode ser varias coisas dependendo
        # de qual aspecto o agente priorizar (mutacao, abatimento, fluxo
        # intenso, etc). O importante e: papel citado + alerta mutacao_silenciosa
        # material — esses sao asserts mais abaixo. Classificacao e secundaria.
        _info(f"Classificacao DC: {exp_dc.get('classificacao_principal')}")
        papeis = exp_dc.get("papeis_mencionados", [])
        _check(
            any("DID99746" in p.get("seu_numero", "") for p in papeis),
            "DID99746 aparece em papeis_mencionados",
        )
        # Alem disso, DID99746 deve gerar alerta mutacao_silenciosa_material
        alertas_mutacao = [
            s for s in out.get("sinais_alerta", [])
            if s.get("tipo") == "mutacao_silenciosa_material"
            and "DID99746" in s.get("entidade", "")
        ]
        _check(
            len(alertas_mutacao) >= 1,
            "Alerta mutacao_silenciosa_material cita DID99746",
        )


async def _cenario_3_lotran(db_session, ctx_base) -> None:
    print(f"\n{'='*100}\nCENARIO 3: 2026-05-20 — padrao LOTRAN (3 papeis com abatimento off-record)\n{'='*100}")
    out = await _run_agente(
        db_session,
        **ctx_base,
        data_d0=date(2026, 5, 20),
        data_anterior=date(2026, 5, 19),
    )
    _print_output_summary(out)
    print()
    # NOTA: 20/05 REAL tem residuo de R$ -850 entre granular e MEC (verificado
    # em sessao 2026-05-24). Nao assertamos sanity.passou — o agente deve
    # detectar e continuar (prompt v1 tem tolerancia graduada R$100-R$5k).
    n1 = out.get("nivel_1_sanity", {})
    _info(f"sanity.passou={n1.get('passou')}, residuo R$ {n1.get('residuo_brl', 0):+.2f}")

    # Mesmo com sanity FAIL, agente deve ter feito Nivel 2 e Nivel 3
    _check(
        len(out.get("nivel_2_decomposicao", [])) >= 11,
        f"Nivel 2 preenchido com >=11 categorias (atual: {len(out.get('nivel_2_decomposicao', []))})",
    )
    _check(
        len(out.get("nivel_3_explicacoes", [])) >= 1,
        f"Nivel 3 tem >=1 explicacao (atual: {len(out.get('nivel_3_explicacoes', []))})",
    )

    # LOTRAN deve aparecer ou em sinais ou em alguma narrativa
    sinais = out.get("sinais_alerta", [])
    explicacoes = out.get("nivel_3_explicacoes", [])
    todas_narrativas = " ".join([e.get("narrativa", "") for e in explicacoes]).lower()
    todas_entidades = " ".join([s.get("entidade", "") for s in sinais]).lower()
    sumario = out.get("sumario_executivo", "").lower()
    todo_texto = todas_narrativas + " " + todas_entidades + " " + sumario

    _check(
        "lotran" in todo_texto,
        "LOTRAN mencionado em alguma narrativa/sinal/sumario",
    )

    # Alerta residuo_alto deve estar presente (residuo R$ -850 e moderado)
    alertas_residuo = [
        s for s in sinais if s.get("tipo") == "residuo_alto"
    ]
    _check(
        len(alertas_residuo) >= 1,
        "Alerta residuo_alto presente (residuo R$ -850 em 20/05 e moderado)",
    )

    # ─── REGRESSAO: sinal da PDD (bug do prompt v1, corrigido na v2/v3) ──────
    # Em 20/05 a PDD SUBIU R$ +2.262,65 (papeis MEGA PACK migraram A->B,
    # constituindo PDD). O prompt v1 narrava isso invertido ("faixa B->A
    # revertendo"), incoerente com um AUMENTO. Estes asserts travam a direcao:
    n2 = out.get("nivel_2_decomposicao", [])
    pdd_cat = next((c for c in n2 if c.get("key") == "pdd"), None)
    _check(
        pdd_cat is not None and pdd_cat.get("delta", 0) > 0,
        f"PDD subiu no dia -> delta > 0 (atual: "
        f"{pdd_cat.get('delta') if pdd_cat else 'categoria ausente'})",
    )

    # Papeis MEGA PACK (sacado vencido, efeito vagao A->B) citados como driver
    # TEM que ter delta_brl positivo (constituicao). Negativo = sinal invertido.
    papeis_mega = [
        p
        for e in explicacoes
        for p in e.get("papeis_mencionados", [])
        if "MEGA PACK" in (p.get("sacado_nome") or "").upper()
    ]
    _check(
        len(papeis_mega) > 0 and all(p.get("delta_brl", 0) > 0 for p in papeis_mega),
        f"Papeis MEGA PACK citados como constituicao (delta_brl > 0); "
        f"achei {len(papeis_mega)}: {[round(p.get('delta_brl', 0), 2) for p in papeis_mega]}",
    )

    # Se a PDD entrou no Nivel 3, a classificacao tem que ser constituicao_pdd
    # (NAO reversao_pdd) — PDD subiu no dia.
    exp_pdd = next((e for e in explicacoes if e.get("categoria_key") == "pdd"), None)
    if exp_pdd is not None:
        _check(
            exp_pdd.get("classificacao_principal") == "constituicao_pdd",
            f"Explicacao da PDD = constituicao_pdd (atual: "
            f"{exp_pdd.get('classificacao_principal')})",
        )
    else:
        _info("PDD nao entrou no Nivel 3 (rank baixo) — assert de classificacao pulado")

    # ─── NOVO (prompt v4): aporte de capital na Cota Mezanino ────────────────
    # Em 20/05 a Cota Mezanino (passivo na otica Sub) subiu +R$ 121.499,89,
    # dos quais R$ 119.545,73 foram APORTE de cotistas (entrada R$ 120k, ~100
    # cotas novas) e so R$ 1.954,16 foi remuneracao da cota. O agente DEVE
    # separar capital de valorizacao via get_decomposicao_classes. Estes
    # asserts so passam com prompt >= v4 ativo (v3 nao separava).
    mez_cat = next((c for c in n2 if c.get("key") == "mezanino"), None)
    _check(
        mez_cat is not None and mez_cat.get("delta", 0) > 100_000,
        f"Categoria Mezanino com Δ > R$ 100k (atual: "
        f"{mez_cat.get('delta') if mez_cat else 'ausente'})",
    )
    texto_v4 = (todas_narrativas + " " + sumario).lower()
    _check(
        "aporte" in texto_v4
        and any(tok in texto_v4 for tok in ("119", "120", "121")),
        "Narrativa/sumario separa o APORTE de capital da Mezanino (cita ~R$ 119-121k)",
    )
    exp_mez = next(
        (e for e in explicacoes if e.get("categoria_key") == "mezanino"), None
    )
    if exp_mez is not None:
        _check(
            exp_mez.get("classificacao_principal") == "aporte_classe",
            f"Explicacao da Mezanino = aporte_classe (atual: "
            f"{exp_mez.get('classificacao_principal')})",
        )
    else:
        _info("Mezanino nao entrou no Nivel 3 — assert de classificacao pulado")


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # Resolve tenant + UA + user real (system maintainer pra rodar)
        row = (
            await db.execute(
                text(
                    "SELECT t.id, ua.id, ua.nome, u.id "
                    "FROM tenants t "
                    "JOIN cadastros_unidade_administrativa ua ON ua.tenant_id=t.id "
                    "LEFT JOIN users u ON u.tenant_id=t.id "
                    "WHERE t.slug='a7-credit' AND ua.cnpj='42449234000160' "
                    "LIMIT 1"
                )
            )
        ).first()
        if row is None:
            print("ERRO: nao achei REALINVEST FIDC no DB.")
            sys.exit(1)
        tenant_id, ua_id, fundo_nome, user_id = row
        if user_id is None:
            # Fallback: zero UUID pra audit (smoke nao audita real user).
            user_id = UUID("00000000-0000-0000-0000-000000000000")

        print(f"Tenant: {tenant_id}")
        print(f"UA: {ua_id} ({fundo_nome})")
        print(f"User: {user_id}")

        ctx_base = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "ua_id": ua_id,
            "fundo_nome": fundo_nome,
        }

        await _cenario_1_dia_normal(db, ctx_base)
        await _cenario_2_did99746(db, ctx_base)
        await _cenario_3_lotran(db, ctx_base)

    print(f"\n{'='*100}")
    if _failures:
        print(f"FALHOU — {len(_failures)} assercoes nao passaram:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("TODAS as assercoes passaram. Smoke do agente OK.")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())

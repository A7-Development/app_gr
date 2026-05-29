"""Smoke do novo schema AnalysisVariacaoCotaResponse (v9, 2026-05-29).

Valida que a forma macro/ofensores/grupos/conclusao/alertas e emitivel e
coerente (Pydantic model_validate aceita um exemplo completo) e que o caminho
"stop" (residuo critico, ofensores/grupos vazios) tambem valida. Nao toca DB.
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from app.agentic.engine.output_schemas import AnalysisVariacaoCotaResponse  # noqa: E402

EXEMPLO = {
    "fundo_nome": "REALINVEST FIDC",
    "data": "2026-05-28",
    "data_anterior": "2026-05-27",
    "macro": {
        "pl_sub_d1": 11800000.00,
        "pl_sub_d0": 11820000.00,
        "pl_sub_delta": 20000.00,
        "total_ativo_delta": -50000.00,
        "total_passivo_delta": -70000.00,
        "leitura": "PL Sub +R$ 20k: passivos cairam R$ 70k (Contas a Pagar) mais que os ativos.",
        "sanity": {"severidade": "ok", "residuo_brl": 0.04, "deve_continuar": True},
    },
    "ofensores": [
        {
            "lado": "passivo", "key": "cpr_pagar", "label": "Contas a Pagar",
            "delta": -108554.53, "impacto_pl_sub": 108554.53, "atipico": True,
            "bullet": "Caiu R$ 108,5k: provisoes de Consultoria e Cobranca zeraram de uma vez.",
        },
    ],
    "grupos": [
        {
            "key": "cpr_pagar", "label": "Contas a Pagar", "lado": "passivo",
            "d1": 157311.18, "d0": 48756.65, "delta": -108554.53,
            "impacto_pl_sub": 108554.53, "atipico": True,
            "atipicidade": {"motivo": "Consultoria e Cobranca zeraram num so dia.", "severidade": "atencao"},
            "classificacao": None,
            "bullets": ["Despesa apropriada caiu R$ 109,9k.", "Consultoria e Cobranca foram o motor."],
            "explicacao": "Provisoes apropriadas aos poucos foram baixadas integralmente em D0.",
            "papeis": [],
        },
        {
            "key": "dc_bruto", "label": "Direitos Creditorios", "lado": "ativo",
            "d1": 24500000.0, "d0": 24450000.0, "delta": -50000.0,
            "impacto_pl_sub": -50000.0, "atipico": False, "atipicidade": None,
            "classificacao": "carrego_normal",
            "bullets": ["Carrego de juros +R$ 35k."],
            "explicacao": "Dia tipico no DC.",
            "papeis": [
                {
                    "seu_numero": "DID123", "numero_documento": "39805",
                    "cedente_nome": "ACME", "sacado_nome": "MEGA",
                    "delta_brl": 1266.0, "natureza": "multa_juros",
                },
            ],
        },
    ],
    "conclusao": "Dia dominado pela baixa de Contas a Pagar; atipico pela forma (zeraram de uma vez).",
    "alertas": [
        {
            "severidade": "atencao", "tipo": "outro", "entidade": "Contas a Pagar",
            "descricao": "Provisoes de Consultoria/Cobranca zeradas num so dia.",
            "evidencia": "CPR pagar 157.311 -> 48.756; despesa apropriada -R$ 109,9k.",
        },
    ],
}

STOP = {
    "fundo_nome": "REALINVEST FIDC",
    "data": "2026-05-22",
    "data_anterior": "2026-05-21",
    "macro": {
        "pl_sub_d1": 11800000.0, "pl_sub_d0": 11789000.0, "pl_sub_delta": -11000.0,
        "total_ativo_delta": -11000.0, "total_passivo_delta": 0.0,
        "leitura": "Identidade nao fecha — analise interrompida.",
        "sanity": {"severidade": "critico", "residuo_brl": -10705.19, "deve_continuar": False},
    },
    "ofensores": [],
    "grupos": [],
    "conclusao": "Pipeline com furo (residuo R$ -10.705). Reprocessar antes de analisar.",
    "alertas": [
        {
            "severidade": "critico", "tipo": "residuo_alto", "entidade": "REALINVEST FIDC",
            "descricao": "Identidade contabil quebrou (residuo R$ -10.705).",
            "evidencia": "PL deduzido vs PL fonte MEC divergem.",
        },
    ],
}

failures: list[str] = []
for nome, payload in (("exemplo completo", EXEMPLO), ("caminho stop", STOP)):
    try:
        r = AnalysisVariacaoCotaResponse.model_validate(payload)
        # round-trip serializa sem perda
        r.model_dump(mode="json")
        print(f"PASS  valida: {nome}")
    except Exception as exc:
        print(f"FAIL  {nome}: {exc}")
        failures.append(nome)

if failures:
    sys.exit(1)
print("OK — schema v9 emitivel e coerente.")

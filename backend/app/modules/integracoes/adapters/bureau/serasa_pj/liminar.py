"""Regra serasa_liminar_v1 -- deteccao de supressao judicial (liminar).

Descoberta 2026-06-10, validada contra as 2.793 consultas em prod com
correspondencia 100% com a flag `Liminar` do Bitfin (56/56 consultas,
32/32 CNPJs): quando o consultado obteve liminar judicial que proibe o
bureau de exibir apontamentos negativos, o payload
RELATORIO_AVANCADO_PJ_ANALITICO vem com `negativeSummary` carregando a
mensagem explicita "NADA CONSTA" — enquanto empresas genuinamente limpas
recebem `negativeSummary` SEM `message` (ou com string vazia).

O "NADA CONSTA" explicito e a forma juridicamente segura do bureau dizer
"fui proibido de mostrar o que tenho". Nos casos observados a supressao
e total: `negativeData` E `facts` (acoes judiciais, falencias) vem
zerados.

A regra e deterministica e VERSIONADA (espelha a disciplina de
`ai_prompt`): se a Serasa mudar o comportamento, nasce a
`serasa_liminar_v2` e o historico continua explicavel por qual versao
concluiu o que (CLAUDE.md secao 14.3). A versao vai gravada junto da
conclusao em `decision_log` e na proveniencia do silver.

A classificacao de mensagens (`classify_negative_summary_message`) e a
base da invariante de ingestao da sentinela (F2): valor fora do conjunto
conhecido = possivel mudanca de comportamento da Serasa -> quarentena da
regra + alerta.
"""

from __future__ import annotations

import re
from typing import Any

LIMINAR_RULE_VERSION = "serasa_liminar_v1"

# Mensagem exata observada nos payloads com supressao judicial.
NADA_CONSTA = "NADA CONSTA"

# Classificacoes canonicas de `negativeSummary.message` (universo
# conhecido em 2026-06-10, levantado sobre 2.793 payloads):
#   - ausente:               sem chave `message` (2.729) — limpo genuino
#   - vazia:                 message == "" (7)
#   - nada_consta:           message == "NADA CONSTA" (56) — suspeita de liminar
#   - recuperacao_judicial:  "EM RECUPERACAO JUDICIAL PROCESSO <n>" (1)
#   - desconhecida:          QUALQUER outro valor — dispara invariante (F2)
MSG_AUSENTE = "ausente"
MSG_VAZIA = "vazia"
MSG_NADA_CONSTA = "nada_consta"
MSG_RECUPERACAO_JUDICIAL = "recuperacao_judicial"
MSG_DESCONHECIDA = "desconhecida"

_RE_RECUPERACAO_JUDICIAL = re.compile(
    r"^EM RECUPERACAO JUDICIAL PROCESSO \d+$"
)


def extract_negative_summary_message(report: dict[str, Any]) -> str | None:
    """Le `negativeSummary.message` cru do report (reports[0] ja resolvido).

    Retorna None quando o bloco ou a chave nao existem. String vazia e
    preservada como "" (distinta de ausente — ver classificacao).
    """
    block = report.get("negativeSummary")
    if not isinstance(block, dict):
        return None
    message = block.get("message")
    if message is None:
        return None
    return str(message).strip().upper() if str(message).strip() else ""


def is_suspeita_liminar(message: str | None) -> bool:
    """Regra serasa_liminar_v1: mensagem explicita "NADA CONSTA".

    Empresa genuinamente limpa NAO recebe a mensagem (vem ausente/vazia).
    """
    return message == NADA_CONSTA


def classify_negative_summary_message(message: str | None) -> str:
    """Classifica a mensagem no universo conhecido (base da invariante F2).

    `MSG_DESCONHECIDA` = valor nunca visto -> sentinela trata como
    possivel mudanca de comportamento da Serasa.
    """
    if message is None:
        return MSG_AUSENTE
    if message == "":
        return MSG_VAZIA
    if message == NADA_CONSTA:
        return MSG_NADA_CONSTA
    if _RE_RECUPERACAO_JUDICIAL.match(message):
        return MSG_RECUPERACAO_JUDICIAL
    return MSG_DESCONHECIDA

"""Decoder de codigo de ocorrencia CNAB -> evento canonico da timeline.

O codigo de ocorrencia (retorno) / comando (remessa) e a SEMANTICA do evento.
Aqui mapeamos `(banco, codigo) -> (tipo_evento, efeito_estado)`:

  - `tipo_evento`   rotulo canonico legivel (TIPO_*), independente de banco.
  - `efeito_estado` como o evento move o estado vigente no fold (EFEITO_*).

A tabela Bradesco foi montada a partir da VARREDURA EMPIRICA dos arquivos reais
(servidor 16, 33,5k registros de retorno) cruzada com a norma CNAB400 Bradesco.
Codigos nao mapeados caem em (TIPO_OUTRO, EFEITO_INFO) -- neutros no fold, mas
preservados crus na timeline para auditoria.

Validacao: um fold ingenuo usando so abre/fecha reconstruiu a carteira
RealInvest a 99,91% do Saldo Atual do banco (R$ 9,04mi vs R$ 9,05mi). Os
codigos "info" (tarifa, confirmacao de protesto) nao afetam a posicao -- por
isso os ambiguos (27/29/32/33/34) entram como info sem risco.
"""

from __future__ import annotations

from app.warehouse.cnab_raw_arquivo import BANCO_BRADESCO, BANCO_GRAFENO

# Versao da taxonomia do decoder. Bumpar ao mudar o mapeamento codigo->evento
# (re-decode atualiza wh_boleto_evento.decoded_by_version). Rastreabilidade §14.
DECODER_VERSION = "cobranca_evento_decoder_v1.1.0"

# ── Tipos de evento canonicos ───────────────────────────────────────────────
TIPO_ENTRADA = "entrada"  # boleto registrado/confirmado no banco
TIPO_ENTRADA_REJEITADA = "entrada_rejeitada"
TIPO_LIQUIDACAO = "liquidacao"  # pago
TIPO_LIQUIDACAO_CARTORIO = "liquidacao_cartorio"
TIPO_BAIXA = "baixa"  # baixado/cancelado
TIPO_PRORROGACAO = "prorrogacao"  # vencimento alterado
TIPO_ABATIMENTO_CONCEDIDO = "abatimento_concedido"
TIPO_ABATIMENTO_CANCELADO = "abatimento_cancelado"
TIPO_PROTESTO_INSTRUIDO = "protesto_instruido"
TIPO_PROTESTO_SUSTADO = "protesto_sustado"
TIPO_ENCAMINHADO_CARTORIO = "encaminhado_cartorio"
TIPO_RETIRADO_CARTORIO = "retirado_cartorio"  # retirado de cartorio, mantido
TIPO_TARIFA = "tarifa"  # debito de tarifas/custas
TIPO_BAIXA_REJEITADA = "baixa_rejeitada"  # baixa tentada e rejeitada
TIPO_INSTRUCAO_REJEITADA = "instrucao_rejeitada"
TIPO_ALTERACAO_DADOS = "alteracao_dados"  # alteracao de outros dados confirmada
TIPO_OCORRENCIA_SACADO = "ocorrencia_sacado"
TIPO_OUTRO = "outro"

# ── Efeito no estado vigente (dirige o fold) ────────────────────────────────
EFEITO_ABRE = "abre"  # -> ativo
EFEITO_FECHA = "fecha"  # -> fora de ativo (liquidado/baixado)
EFEITO_MODIFICA = "modifica"  # mantem estado, muda atributo (venc/valor)
EFEITO_REJEITA = "rejeita"  # nunca ficou ativo
EFEITO_INFO = "info"  # neutro

# ── Bradesco CNAB400: codigo de ocorrencia (pos 109-110) -> evento ──────────
# Empirico (qtd no historico) + norma. `A_CONFIRMAR` nos comentarios marca os
# que ainda dependem do manual Bradesco -- todos sao info (neutros no fold).
_BRADESCO: dict[str, tuple[str, str]] = {
    "02": (TIPO_ENTRADA, EFEITO_ABRE),  # 15138 entrada confirmada
    "06": (TIPO_LIQUIDACAO, EFEITO_FECHA),  # 13232 liquidacao
    "09": (TIPO_BAIXA, EFEITO_FECHA),  # 2490 baixa
    "03": (TIPO_ENTRADA_REJEITADA, EFEITO_REJEITA),  # 1008 entrada rejeitada
    "10": (TIPO_BAIXA, EFEITO_FECHA),  # 423 baixado conforme instrucao
    "14": (TIPO_PRORROGACAO, EFEITO_MODIFICA),  # 134 vencimento alterado
    "28": (TIPO_TARIFA, EFEITO_INFO),  # 128 debito de tarifas/custas
    "23": (TIPO_ENCAMINHADO_CARTORIO, EFEITO_INFO),  # 102 encaminhado a cartorio
    "19": (TIPO_PROTESTO_INSTRUIDO, EFEITO_INFO),  # 101 conf. instrucao protesto
    "20": (TIPO_PROTESTO_SUSTADO, EFEITO_INFO),  # 37 conf. sustar protesto
    "12": (TIPO_ABATIMENTO_CONCEDIDO, EFEITO_MODIFICA),  # 21 abatimento concedido
    "13": (TIPO_ABATIMENTO_CANCELADO, EFEITO_MODIFICA),  # abatimento cancelado
    "15": (TIPO_LIQUIDACAO_CARTORIO, EFEITO_FECHA),  # 15 liquidacao em cartorio
    "17": (TIPO_LIQUIDACAO, EFEITO_FECHA),  # liquidacao apos baixa
    # Familia rejeicao/cartorio/alteracao — decodificada 2026-06-05 (norma
    # Bradesco + validacao empirica: NENHUM e terminal; boletos com esses
    # codigos fecham por outros eventos; os poucos ativos estao corretos).
    "27": (TIPO_BAIXA_REJEITADA, EFEITO_INFO),  # 439 baixa rejeitada (continua)
    "33": (TIPO_ALTERACAO_DADOS, EFEITO_MODIFICA),  # 99 conf. alteracao de dados
    "29": (TIPO_OCORRENCIA_SACADO, EFEITO_INFO),  # 92 ocorrencias do sacado
    "32": (TIPO_INSTRUCAO_REJEITADA, EFEITO_INFO),  # 43 instrucao rejeitada
    "34": (TIPO_RETIRADO_CARTORIO, EFEITO_INFO),  # 14 retirado de cartorio, mantido
}

# Grafeno (codigo 274/310): tabela a montar quando o parser Grafeno entrar.
_GRAFENO: dict[str, tuple[str, str]] = {}

_POR_BANCO: dict[str, dict[str, tuple[str, str]]] = {
    BANCO_BRADESCO: _BRADESCO,
    BANCO_GRAFENO: _GRAFENO,
}

_DEFAULT = (TIPO_OUTRO, EFEITO_INFO)


def decode_ocorrencia(banco: str, codigo: str | None) -> tuple[str, str]:
    """(tipo_evento, efeito_estado) para o codigo de ocorrencia do banco.

    Codigo nao mapeado -> (TIPO_OUTRO, EFEITO_INFO): preservado cru na timeline,
    neutro no fold. Nunca levanta -- decode e total por design.
    """
    if not codigo:
        return _DEFAULT
    return _POR_BANCO.get(banco, {}).get(codigo.strip(), _DEFAULT)

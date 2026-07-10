// Geradores DETERMINÍSTICOS da "leitura" de um cedente — reason codes,
// severidade e narrativa. Tudo derivado dos números da linha (nenhuma IA):
// o mesmo princípio dos reason codes de crédito — vocabulário fechado, um
// punhado de códigos padronizados por decisão, comparáveis linha a linha.
//
// Camadas por resolução:
//   - reason chips  -> na linha da tabela (escanear/comparar N cedentes)
//   - narrativa     -> no drawer (a história de UM cedente, com números reais)

import type { CedentePerfilRow } from "@/lib/api-client"

export type Severidade = "critico" | "atencao" | "neutro"
export type Tier = "alto" | "medio" | "contexto"

export type ReasonCode = {
  code: string // rótulo curto exibido no chip (ex.: "MULTI-CED")
  label: string // nome completo (tooltip)
  tier: Tier
}

const pct = (n: number, total: number) => (total > 0 ? n / total : 0)

// Severidade determinística (não há score de modelo aqui — isso é o outro
// painel): crítico = regra dura acionou; atenção = red flag forte sem regra.
export function severidade(r: CedentePerfilRow): Severidade {
  if (r.n_alerta > 0) return "critico"
  const s = r.sinais
  const forte =
    r.n_liq > 0 &&
    ((s.conta_cedente ?? 0) > 0 ||
      pct(s.fora_praca ?? 0, r.n_liq) >= 0.5 ||
      pct(s.multi_sacado ?? 0, r.n_liq) >= 0.5 ||
      pct(s.praca_cedente ?? 0, r.n_liq) >= 0.4)
  return forte ? "atencao" : "neutro"
}

// Vocabulário fechado de reason codes, rankeados. Regra: se a regra dura
// acionou, o driver dela é o chip #1 FIXO (o "porquê" do alerta aparece
// sempre); os demais entram por tier × intensidade (%), cap 3.
export function reasonCodes(r: CedentePerfilRow): ReasonCode[] {
  const total = r.n_liq || 1
  type Cand = ReasonCode & { w: number; pinned?: boolean }
  const cand: Cand[] = []
  const seen = new Set<string>()

  const add = (
    cond: boolean,
    code: string,
    label: string,
    tier: Tier,
    ratio: number,
    pinned = false,
  ) => {
    if (!cond || seen.has(code)) return
    seen.add(code)
    const tierW = tier === "alto" ? 3 : tier === "medio" ? 2 : 1
    // ratio (<1) mantém o tier como fator dominante do ranking.
    cand.push({ code, label, tier, w: pinned ? 100 : tierW + ratio, pinned })
  }

  // driver do alerta (pinned #1)
  if (r.n_alerta > 0) {
    if ((r.n_alerta_multicedente ?? 0) >= (r.n_alerta_conta ?? 0)) {
      add(true, "MULTI-CED", "Agência multi-cedente", "alto", 1, true)
    } else {
      add(true, "CONTA", "Conta do cedente", "alto", 1, true)
    }
  }

  const s = r.sinais
  // praca_cedente ⊆ fora_praca (ambas exigem ≠ cidade do sacado); o resíduo
  // "fora do sacado numa TERCEIRA praça" = fora_praca − praca_cedente.
  const capturaGeo = s.praca_cedente ?? 0 // fora do sacado E na praça do cedente
  const foraOutra = Math.max(0, (s.fora_praca ?? 0) - capturaGeo)

  // CONTA como chip precisa de piso (≥5%): 1 de 99 é ruído, não driver. A
  // contagem exata segue na narrativa; se a conta DISPAROU o alerta, já entrou
  // pinned acima (ignora o piso).
  add(pct(s.conta_cedente ?? 0, total) >= 0.05, "CONTA", "Conta do cedente", "alto", pct(s.conta_cedente ?? 0, total))
  // Assinatura geográfica de captura — tier ALTO (tão forte quanto conta).
  add(pct(capturaGeo, total) >= 0.15, "PRAÇA-CED", "Fora do sacado, na praça do cedente", "alto", pct(capturaGeo, total))
  add(pct(s.multi_sacado ?? 0, total) >= 0.15, "MULTI-SAC", "Agência multi-sacado", "medio", pct(s.multi_sacado ?? 0, total))
  // Resíduo: fora do sacado, mas NÃO na praça do cedente (terceira praça).
  add(pct(foraOutra, total) >= 0.15, "FORA-PRAÇA", "Fora do sacado (outra praça)", "medio", pct(foraOutra, total))
  add(pct(s.fora_padrao ?? 0, total) >= 0.15, "PADRÃO", "Fora do padrão do sacado", "medio", pct(s.fora_padrao ?? 0, total))

  // canal entra como chip SÓ quando o segmento concentra (>~40%)
  const canais: [string, string, string][] = [
    ["cooperativa", "COOP", "Canal concentrado em cooperativa"],
    ["ip", "IP", "Canal concentrado em instituição de pagamento"],
    ["banco_digital", "DIGITAL", "Canal concentrado em banco digital"],
    ["scd", "SCD", "Canal concentrado em SCD"],
    ["financeira", "FIN", "Canal concentrado em financeira"],
  ]
  for (const [k, code, label] of canais) {
    add(pct(r.segmentos[k] ?? 0, total) >= 0.4, code, label, "contexto", pct(r.segmentos[k] ?? 0, total))
  }

  const pinned = cand.filter((c) => c.pinned)
  const rest = cand.filter((c) => !c.pinned).sort((a, b) => b.w - a.w)
  return [...pinned, ...rest].slice(0, 3).map(({ code, label, tier }) => ({ code, label, tier }))
}

const freq = (p: number) => (p < 0.05 ? "quase nunca" : p < 0.3 ? "raramente" : "com frequência")

// Narrativa determinística ESPECÍFICA (números reais) — a "carta explicativa"
// do cedente. 2–4 frases pra caber no drawer sem rolagem.
export function narrativa(r: CedentePerfilRow): string {
  const total = r.n_liq || 1
  const frases: string[] = []

  if (r.n_alerta > 0) {
    const plural = r.n_alerta === 1 ? "alerta" : "alertas"
    if ((r.n_alerta_multicedente ?? 0) >= (r.n_alerta_conta ?? 0)) {
      const escopo = r.n_alerta_multicedente === r.n_alerta ? "todos" : `${r.n_alerta_multicedente}`
      frases.push(
        `${r.n_alerta} ${plural}, ${escopo} de agência multi-cedente: a mesma agência física recebe pagamentos de vários cedentes.`,
      )
    } else {
      frases.push(
        `${r.n_alerta} ${plural} de conta+cidade: sacado de outra praça pagando na agência/conta do cedente.`,
      )
    }
  }

  const c = r.sinais.conta_cedente ?? 0
  frases.push(
    `Conta do cedente = ${c} de ${r.n_liq} — ${freq(pct(c, total))} usa a conta cadastrada dela.`,
  )

  // Assinatura geográfica de captura: fora do sacado E na praça do cedente.
  const capturaGeo = r.sinais.praca_cedente ?? 0
  if (pct(capturaGeo, total) >= 0.15) {
    frases.push(
      `${capturaGeo} de ${r.n_liq} pagas fora da praça do sacado e na praça do cedente (${Math.round(pct(capturaGeo, total) * 100)}%) — a assinatura geográfica de captura.`,
    )
  }

  // outro sinal de rede/padrão dominante, se relevante
  const foraOutra = Math.max(0, (r.sinais.fora_praca ?? 0) - capturaGeo)
  const extras: [number, string][] = [
    [r.sinais.multi_sacado ?? 0, "concentrado em agência multi-sacado"],
    [r.sinais.fora_padrao ?? 0, "fora do padrão histórico do sacado"],
    [foraOutra, "pago fora do sacado, em outra praça"],
  ]
  const dom = extras.filter(([n]) => pct(n, total) >= 0.2).sort((a, b) => b[0] - a[0])[0]
  if (dom) frases.push(`Predomina também ${dom[1]} (${Math.round(pct(dom[0], total) * 100)}%).`)

  // canal, se concentra
  const seg: [number, string][] = [
    [r.segmentos.cooperativa ?? 0, "cooperativa"],
    [r.segmentos.ip ?? 0, "instituição de pagamento"],
    [r.segmentos.banco_digital ?? 0, "banco digital"],
  ]
  const canal = seg.filter(([n]) => pct(n, total) >= 0.4).sort((a, b) => b[0] - a[0])[0]
  if (canal) frases.push(`Canal concentrado em ${canal[1]} (${Math.round(pct(canal[0], total) * 100)}%).`)

  return frases.join(" ")
}

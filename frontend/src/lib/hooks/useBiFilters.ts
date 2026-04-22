"use client"

import { useSearchParams, usePathname, useRouter } from "next/navigation"
import { useCallback, useMemo } from "react"
import type { BIFilters } from "@/lib/api-client"

/**
 * Produtos inclusos por padrao no filtro quando nenhum valor esta na URL.
 * Regra de negocio: excluimos produtos de cobranca/confissao (volume
 * marginal e nao refletem originacao ativa):
 *   - CBV  Cobranca Vinculada
 *   - CBS  Cobranca Simples
 *   - CFD  Confissao de Divida
 *
 * Quando o usuario limpa o filtro, voltamos a este padrao. Para ver
 * todas as 10 siglas, o usuario marca os 3 extras manualmente no popover.
 */
const PRODUTO_DEFAULT: string[] = [
  "FAT",
  "CMS",
  "DMS",
  "NOT",
  "INT",
  "FOM",
  "CCB",
]

//
// Presets de periodo — atalhos que o usuario clica para aplicar ranges
// pre-definidos relativos a hoje (rolling). `12m` e o default quando
// a URL nao tem nem `preset` nem `periodo_inicio/fim` explicitos.
//

export const PRESET_KEYS = ["ytd", "3m", "6m", "12m", "24m", "36m", "all"] as const
export type PresetKey = (typeof PRESET_KEYS)[number]

const DEFAULT_PRESET: PresetKey = "12m"
const FALLBACK_ALL_START = "2000-01-01" // usado se data_minima nao veio

function toISO(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const dd = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${dd}`
}

function subMonths(d: Date, months: number): Date {
  const copy = new Date(d)
  copy.setMonth(copy.getMonth() - months)
  return copy
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

/**
 * Calcula o range ISO `{start, end}` do preset, relativo a `today`.
 * `dataMinima` (ISO) e usado quando o preset e `all` — se ausente,
 * cai no fallback `FALLBACK_ALL_START`.
 *
 * Presets rolling (3m/6m/12m/24m/36m) normalizam o inicio para o primeiro
 * dia do mes — caso contrario o bucket mensal mais antigo fica truncado
 * (ex.: "12m" em 2026-04-22 comecaria em 2025-04-22 e o bucket de Abr/25
 * mostraria so 9 dias de dados). O mes corrente continua parcial por
 * construcao (esperado: periodo estende ate hoje).
 */
export function computePresetRange(
  preset: PresetKey,
  today: Date,
  dataMinima?: string,
): { start: string; end: string } {
  const end = toISO(today)
  switch (preset) {
    case "ytd": {
      const y = today.getFullYear()
      return { start: `${y}-01-01`, end }
    }
    case "3m":
      return { start: toISO(startOfMonth(subMonths(today, 3))), end }
    case "6m":
      return { start: toISO(startOfMonth(subMonths(today, 6))), end }
    case "12m":
      return { start: toISO(startOfMonth(subMonths(today, 12))), end }
    case "24m":
      return { start: toISO(startOfMonth(subMonths(today, 24))), end }
    case "36m":
      return { start: toISO(startOfMonth(subMonths(today, 36))), end }
    case "all":
      return { start: dataMinima ?? FALLBACK_ALL_START, end }
  }
}

/**
 * Converte 'YYYY-MM' em range do mes completo:
 *   '2026-04' -> { start: '2026-04-01', end: '2026-04-30' }
 */
function monthRangeFromYm(ym: string): { start: string; end: string } {
  const [y, m] = ym.split("-").map(Number)
  const lastDay = new Date(y, m, 0).getDate()
  const mm = String(m).padStart(2, "0")
  return {
    start: `${y}-${mm}-01`,
    end: `${y}-${mm}-${String(lastDay).padStart(2, "0")}`,
  }
}

function isPresetKey(v: string | null): v is PresetKey {
  return v !== null && (PRESET_KEYS as readonly string[]).includes(v)
}

/**
 * Patch aceito por setFilter. Alem dos campos do backend, inclui:
 *  - `focusMes` (formato 'YYYY-MM'): cross-filter de mes sem sobrescrever
 *    range macro. O chart source (evolucao mensal) usa `filters` raw para
 *    manter todos os meses visiveis; destinos usam `filtersWithFocus`.
 *  - `focusProduto` (sigla, ex.: 'FAT'): cross-filter de produto. Lista
 *    da tab Produto usa `filters` raw (mostra todos os produtos);
 *    destinos (KPIs, chart principal) usam `filtersWithFocus` com essa
 *    sigla aplicada como `produtoSigla`.
 *  - `preset` (PresetKey | null): preset de periodo. Se setado, limpa
 *    periodoInicio/Fim. Se null, limpa o preset da URL.
 */
export type SetFilterPatch = Partial<BIFilters> & {
  focusMes?: string
  focusProduto?: string
  preset?: PresetKey | null
}

export type UseBiFiltersResult = {
  /**
   * Filtros "raw" (preset ja resolvido para periodoInicio/Fim). Campos de
   * focus (mes, produto) NAO entram aqui — eles sao virtuais e expandem em
   * variantes especificas abaixo.
   *
   * Use `filters` quando nao quer aplicar foco algum (ex.: queries que
   * precisam ver todos os periodos e todos os produtos).
   */
  filters: BIFilters
  /**
   * Raw + `focusMes` aplicado (quando presente).
   * Use em componentes que sao SOURCE de `focusProduto` mas DESTINO de
   * `focusMes` (ex.: lista de Produto — ela nao se auto-filtra por produto,
   * mas deve reagir a mudanca de foco mensal).
   */
  filtersWithFocusMes: BIFilters
  /**
   * Raw + `focusProduto` aplicado (quando presente).
   * Use em componentes que sao SOURCE de `focusMes` mas DESTINO de
   * `focusProduto` (ex.: chart de Evolucao mensal — nao se auto-filtra
   * por mes, mas deve reagir ao produto em foco).
   */
  filtersWithFocusProduto: BIFilters
  /**
   * Raw + ambos os focos aplicados.
   * Use em DESTINOS totais — componentes que reagem a qualquer foco mas
   * nao sao source de nenhum (ex.: KPIs, painel lateral de Empresa, MoM).
   */
  filtersWithFocus: BIFilters
  /** Mes em foco no formato 'YYYY-MM', ou undefined quando nao ha foco. */
  focusMes: string | undefined
  /** Produto em foco (sigla), ou undefined quando nao ha foco. */
  focusProduto: string | undefined
  /**
   * Preset de periodo ATIVO na URL. Se `null`, significa modo custom
   * (usuario mexeu no DateRangePicker e temos `periodo_inicio/fim`
   * explicitos na URL).
   */
  preset: PresetKey | null
  /**
   * Data minima de operacao do tenant (ISO). Recebida do componente que
   * usa o hook — o hook nao busca sozinho pra evitar acoplamento com
   * React Query; quem renderiza os presets passa. Afeta apenas o preset
   * 'all'.
   */
  setDataMinima: (dataMinima: string | undefined) => void
  setFilter: (patch: SetFilterPatch) => void
  resetFilters: () => void
}

/**
 * Filtros globais do modulo BI, sincronizados com a URL.
 * Regra dura: URL e a fonte da verdade (CLAUDE.md 11.6.3).
 *
 * Hierarquia de periodo na URL (precedencia):
 *   1. `?periodo_inicio` + `?periodo_fim` explicitos → modo custom, preset = null
 *   2. `?preset=xx` (sem periodo_inicio/fim) → computa range rolling
 *   3. Nenhum dos dois → default: preset `12m`
 *
 * Nunca coexistem `preset` e `periodo_inicio/fim` na mesma URL — setar um
 * apaga o outro automaticamente.
 *
 * Cross-filter:
 *  - `focusMes` (formato 'YYYY-MM') e campo virtual independente do range
 *    macro. Nao e afetado por troca de preset.
 *
 * `dataMinima`: quem usa o hook (tipicamente BiFiltersBar) passa o valor
 * recebido de `/bi/metadata/data-minima`. Sem isso, preset 'all' cai em
 * fallback `FALLBACK_ALL_START`.
 */
export function useBiFilters(
  dataMinima?: string,
): UseBiFiltersResult {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()

  // 1. Preset: resolvido a partir da URL ou do default (12m)
  const presetFromUrl = sp.get("preset")
  const hasExplicitPeriodo =
    sp.get("periodo_inicio") !== null || sp.get("periodo_fim") !== null

  const preset: PresetKey | null = hasExplicitPeriodo
    ? null
    : isPresetKey(presetFromUrl)
      ? presetFromUrl
      : DEFAULT_PRESET

  // 2. Periodo: se tem preset, calcula rolling; senao, usa o que tiver na URL
  const presetRange = useMemo(() => {
    if (!preset) return null
    return computePresetRange(preset, new Date(), dataMinima)
  }, [preset, dataMinima])

  const filters: BIFilters = useMemo(() => {
    const produtos = sp.getAll("produto_sigla")
    const uas = sp
      .getAll("ua_id")
      .map((v) => Number(v))
      .filter((n) => Number.isFinite(n))

    // Period: preset wins if present; else use explicit URL params.
    const periodoInicio = presetRange
      ? presetRange.start
      : (sp.get("periodo_inicio") ?? undefined)
    const periodoFim = presetRange
      ? presetRange.end
      : (sp.get("periodo_fim") ?? undefined)

    return {
      periodoInicio,
      periodoFim,
      produtoSigla: produtos.length > 0 ? produtos : PRODUTO_DEFAULT,
      uaId: uas.length > 0 ? uas : undefined,
      cedenteId: sp.get("cedente_id") ? Number(sp.get("cedente_id")) : undefined,
      sacadoId: sp.get("sacado_id") ? Number(sp.get("sacado_id")) : undefined,
      gerenteDocumento: sp.get("gerente_documento") ?? undefined,
    }
  }, [sp, presetRange])

  const focusMes = sp.get("focus_mes") ?? undefined
  const focusProduto = sp.get("focus_produto") ?? undefined

  // Variantes do `filters` com focus aplicado seletivamente. Cada componente
  // que consome o hook escolhe qual variante usar conforme seu papel:
  //  - SOURCE de uma dimensao: usa a variante que NAO aplica o focus daquela
  //    dimensao (para nao se auto-filtrar)
  //  - DESTINO total: usa `filtersWithFocus` (aplica ambos)
  const filtersWithFocusMes: BIFilters = useMemo(() => {
    if (!focusMes) return filters
    const { start, end } = monthRangeFromYm(focusMes)
    return { ...filters, periodoInicio: start, periodoFim: end }
  }, [filters, focusMes])

  const filtersWithFocusProduto: BIFilters = useMemo(() => {
    if (!focusProduto) return filters
    return { ...filters, produtoSigla: [focusProduto] }
  }, [filters, focusProduto])

  const filtersWithFocus: BIFilters = useMemo(() => {
    let f = filters
    if (focusMes) {
      const { start, end } = monthRangeFromYm(focusMes)
      f = { ...f, periodoInicio: start, periodoFim: end }
    }
    if (focusProduto) {
      f = { ...f, produtoSigla: [focusProduto] }
    }
    return f
  }, [filters, focusMes, focusProduto])

  const setFilter = useCallback(
    (patch: SetFilterPatch) => {
      const next = new URLSearchParams(sp.toString())
      const applyScalar = (
        k: string,
        v: string | number | undefined | null,
      ) => {
        if (v === undefined || v === "" || v === null) next.delete(k)
        else next.set(k, String(v))
      }
      const applyArray = (k: string, v: (string | number)[] | undefined) => {
        next.delete(k)
        if (v && v.length > 0) for (const x of v) next.append(k, String(x))
      }

      // ── Coerencia preset ↔ periodo: mutuamente exclusivos. ─────────────
      // Setar preset apaga periodoInicio/Fim; setar periodoInicio/Fim apaga preset.
      if ("preset" in patch) {
        if (patch.preset) {
          next.set("preset", patch.preset)
          next.delete("periodo_inicio")
          next.delete("periodo_fim")
        } else {
          next.delete("preset")
        }
      }
      if ("periodoInicio" in patch || "periodoFim" in patch) {
        if (!("preset" in patch)) next.delete("preset")
        if ("periodoInicio" in patch) applyScalar("periodo_inicio", patch.periodoInicio)
        if ("periodoFim" in patch) applyScalar("periodo_fim", patch.periodoFim)
      }

      if ("produtoSigla" in patch) applyArray("produto_sigla", patch.produtoSigla)
      if ("uaId" in patch) applyArray("ua_id", patch.uaId)
      if ("cedenteId" in patch) applyScalar("cedente_id", patch.cedenteId)
      if ("sacadoId" in patch) applyScalar("sacado_id", patch.sacadoId)
      if ("gerenteDocumento" in patch)
        applyScalar("gerente_documento", patch.gerenteDocumento)
      if ("focusMes" in patch) applyScalar("focus_mes", patch.focusMes)
      if ("focusProduto" in patch)
        applyScalar("focus_produto", patch.focusProduto)

      // Mudar range macro limpa o focus de mes — evita recorte fantasma.
      if (
        ("periodoInicio" in patch ||
          "periodoFim" in patch ||
          "preset" in patch) &&
        !("focusMes" in patch)
      ) {
        next.delete("focus_mes")
      }
      // Mudar o filtro hard de produto limpa o focus de produto — se o
      // usuario restringe produtos pelo FilterPill, a selecao "em foco"
      // anterior nao faz mais sentido.
      if ("produtoSigla" in patch && !("focusProduto" in patch)) {
        next.delete("focus_produto")
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false })
    },
    [router, pathname, sp],
  )

  const resetFilters = useCallback(() => {
    router.replace(pathname, { scroll: false })
  }, [router, pathname])

  // `setDataMinima` fica como no-op aqui: a dataMinima e recebida como
  // parametro do hook (quem chama passa o valor vindo da query do endpoint).
  // O setter fica no contrato pra possibilitar uma evolucao futura onde o
  // hook mesmo busca via React Query — mantendo API estavel.
  const setDataMinima = useCallback(() => {}, [])

  return {
    filters,
    filtersWithFocusMes,
    filtersWithFocusProduto,
    filtersWithFocus,
    focusMes,
    focusProduto,
    preset,
    setDataMinima,
    setFilter,
    resetFilters,
  }
}

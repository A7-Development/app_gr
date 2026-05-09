# Tokens

Espelho TypeScript dos CSS vars em `globals.css`. CSS vars sao a fonte de verdade visual; estes arquivos existem porque alguns contextos (ECharts, calculo dinamico) precisam dos valores em TS.

## Arquivos

| Arquivo | O que tem |
|---|---|
| `index.ts` | Objeto `tokens` com `brand`, `status`, `chart`, `delta`, `fonts`, `spacing`, `radius`, `motion`. Tipos `StatusKey` e `ChartColor`. |
| `echarts-theme.ts` | `getEChartsTheme(mode)` -- retorna tema completo p/ ReactECharts. `useEChartsTheme()` hook que escuta next-themes. Tooltip sempre dark (Stripe/Vercel pattern). `animationDurationUpdate: 0` enforced. |
| `typography.ts` | `fmt.{currency, currencyWhole, currencyCompact, percent, number, decimal1}` (Intl.NumberFormat pt-BR). `fmtDate(iso)`, `fmtCPF(raw)`, `fmtCNPJ(raw)`. Classes utilitarias: `tabular`, `monoId`, `caption`, `kpiHero`. |
| `spacing.ts` | `sidebar.{widthExpanded, widthCollapsed}`, `layout.{headerH, filterBarH}`, `drawer.{sm, md, lg}`, `rowHeight.{compact, default, comfortable}`. `rowHeightClass(density)` helper. `radius.{sm, base, md, lg, full}`. |
| `motion.ts` | `duration.{instant, fast, base, slow, slower}` (ms). `easing.{standard, decelerate, accelerate}`. `transition(prop, speed, ease)` helper. `motionClasses` (sheetIn/sheetOut/tooltipIn/dialogIn/fadeIn). `echartsMotion` (animationDurationUpdate=0). |

## Quando usar TS token vs CSS var vs Tailwind

| Cenario | Acesso |
|---|---|
| Cor de serie em chart ECharts | `tokens.colors.chart[0]` |
| Tema completo do ECharts (light/dark auto) | `useEChartsTheme()` hook |
| Cor em componente JSX | classes Tailwind (`text-gray-900`, `bg-blue-500`, `dark:bg-gray-925`) |
| Format numerico pt-BR | `fmt.currency.format(123)`, `fmt.percent.format(0.12)` |
| Format CPF/CNPJ/data | `fmtCPF()`, `fmtCNPJ()`, `fmtDate()` |
| Layout (sidebar w, header h) | `tokens.spacing.*` ou CSS var (`var(--sidebar-w)`) |
| Animacao | classes ja registradas em `globals.css` |

## Imports

```ts
import { tokens, type StatusKey, type ChartColor } from "@/design-system/tokens"
import { fmt, fmtDate, fmtCPF, fmtCNPJ, tabular, monoId } from "@/design-system/tokens/typography"
import { rowHeightClass, type DensityMode } from "@/design-system/tokens/spacing"
import { duration, easing, transition, echartsMotion } from "@/design-system/tokens/motion"
import { useEChartsTheme, getEChartsTheme } from "@/design-system/tokens/echarts-theme"
```

## Proibido

- Valores de cor ad-hoc (`text-[#abc]`) -- CLAUDE.md §4
- Tamanhos magicos (`text-[13px]`, `p-[7px]`) -- use spacing scale Tailwind
- Adicionar novo token sem discutir -- estes arquivos espelham `colors_and_type.css` upstream

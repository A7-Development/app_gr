"use client"

/**
 * HeroSplitAuth — surface template para paginas nao-autenticadas com layout
 * 60/40: hero zone (gradiente navy + glow laranja + pattern de linhas + logo +
 * headline + trust signals) a esquerda, form panel a direita.
 *
 * USE PARA: /login, /recover-password, /onboarding/welcome.
 *
 * HOW TO ADAPT:
 * 1. Copie a montagem de `HeroSplitAuthExample` (no fim do arquivo) ou veja
 *    `app/(auth)/login/page.tsx` como referencia.
 * 2. Troque a copy (headline, lede, trust signals, formTitle, formDescription).
 * 3. Substitua o `<form>` filho de `<HeroSplitAuth.FormPanel>` pelo seu form
 *    com `react-hook-form` + Tremor primitives.
 * 4. Footer do form e opcional (link "Sem acesso? Contate seu administrador").
 *
 * REGRAS:
 * - Esta superficie e a UNICA camada onde `tokens.colors.brand` e
 *   `tokens.typography.hero` sao permitidos. Nao copie esses estilos para
 *   componentes de dashboard.
 * - Animacoes respeitam `prefers-reduced-motion: reduce` (definidas em globals.css).
 */

import * as React from "react"
import { useTheme } from "next-themes"
import {
  RiDatabase2Line,
  RiLockLine,
  RiMoonLine,
  RiShieldCheckLine,
  RiSunLine,
} from "@remixicon/react"

type RemixIcon = typeof RiShieldCheckLine

import { StrataIcon } from "@/design-system/components/StrataIcon"
import { tokens } from "@/design-system/tokens"

// ── Hero typography helpers (inline styles using tokens.typography.hero) ──────

const hero = tokens.typography.hero
const brand = tokens.colors.brand

// ── Root container ────────────────────────────────────────────────────────────

type HeroSplitAuthProps = {
  children: React.ReactNode
}

function HeroSplitAuthRoot({ children }: HeroSplitAuthProps) {
  return (
    <div className="flex min-h-svh w-full overflow-hidden bg-gray-50 dark:bg-gray-950">
      {children}
    </div>
  )
}

// ── Hero zone (left, 60%) ─────────────────────────────────────────────────────

type HeroProps = {
  children: React.ReactNode
}

function Hero({ children }: HeroProps) {
  return (
    <div
      data-hero-anim
      className="relative hidden flex-col justify-between overflow-hidden lg:flex"
      style={{
        flex: "0 0 60%",
        // Layered background — only expressable as inline because it composes
        // a linear gradient + radial overlay + SVG pattern, all using brand tokens.
        background: `linear-gradient(135deg, ${brand.navy} 0%, ${brand.navyDark} 100%)`,
        animation: "heroFadeSlideLeft 0.65s cubic-bezier(0.16, 1, 0.3, 1) both",
      }}
    >
      {/* Layer: orange glow top-left */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `radial-gradient(ellipse at top left, ${brand.orangeGlow} 0%, ${brand.orangeGlowMid} 30%, transparent 60%)`,
        }}
      />

      {/* Layer: strata pattern — uniform horizontal lines */}
      <svg
        className="pointer-events-none absolute inset-0 size-full"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        <defs>
          <pattern id="hero-strata-lines" x="0" y="0" width="1" height="60" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0"  x2="3000" y2="0"  stroke="white" strokeWidth="0.75" strokeOpacity="0.04" />
            <line x1="0" y1="20" x2="3000" y2="20" stroke="white" strokeWidth="0.75" strokeOpacity="0.055" />
            <line x1="0" y1="40" x2="3000" y2="40" stroke="white" strokeWidth="0.75" strokeOpacity="0.04" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#hero-strata-lines)" />
      </svg>

      {children}
    </div>
  )
}

// ── Brand lockup (logo + wordmark + eyebrow) ──────────────────────────────────

type BrandProps = {
  wordmark: string
  eyebrow: string
}

function Brand({ wordmark, eyebrow }: BrandProps) {
  return (
    <div className="relative z-10 flex items-center gap-[14px] px-20 pt-[72px]">
      <StrataIcon height={44} tone="onDark" />
      <div>
        <div className="text-white" style={{ ...hero.wordmark }}>
          {wordmark}
        </div>
        <div
          className="mt-[5px]"
          style={{
            ...hero.eyebrow,
            color: brand.heroEyebrow,
          }}
        >
          {eyebrow}
        </div>
      </div>
    </div>
  )
}

// ── Headline + lede block ─────────────────────────────────────────────────────

type CopyProps = {
  children: React.ReactNode
}

function Headline({ children }: CopyProps) {
  return (
    <h1
      className="relative z-10 mb-6 px-20 text-white"
      style={{ ...hero.display, maxWidth: 720 }}
    >
      {children}
    </h1>
  )
}

function Lede({ children }: CopyProps) {
  return (
    <p
      className="relative z-10 px-20"
      style={{
        ...hero.lede,
        color: brand.heroBodyText,
        maxWidth: 440,
      }}
    >
      {children}
    </p>
  )
}

/** Spacer between brand lockup and headline; keeps copy vertically centered. */
function HeroSpacer() {
  return <div className="relative z-10 flex-1" />
}

// ── Trust signals (compliance badges at bottom of hero) ───────────────────────

type TrustItem = {
  icon: RemixIcon
  label: string
}

type TrustSignalsProps = {
  items: TrustItem[]
}

function TrustSignals({ items }: TrustSignalsProps) {
  return (
    <div className="relative z-10 flex items-center gap-5 px-20 pb-14 pt-8">
      {items.map(({ icon: Icon, label }, i) => (
        <React.Fragment key={label}>
          {i > 0 && (
            <div
              aria-hidden="true"
              style={{ width: 1, height: 12, background: brand.heroDivider }}
            />
          )}
          <div
            className="flex items-center gap-1.5"
            style={{ ...hero.trust, color: brand.heroTrust }}
          >
            <Icon className="size-3" aria-hidden="true" />
            {label}
          </div>
        </React.Fragment>
      ))}
    </div>
  )
}

// ── Form panel (right, 40%) ───────────────────────────────────────────────────

type FormPanelProps = {
  title: string
  description?: string
  children: React.ReactNode
  footer?: React.ReactNode
}

function FormPanel({ title, description, children, footer }: FormPanelProps) {
  return (
    <div
      data-hero-anim
      className="relative flex w-full flex-col items-center justify-center border-l border-gray-200 bg-white px-10 py-12 dark:border-gray-800 dark:bg-gray-900 lg:w-2/5"
      style={{
        flex: "1 1 40%",
        animation: "heroFadeSlideRight 0.65s cubic-bezier(0.16, 1, 0.3, 1) 0.08s both",
      }}
    >
      <DarkModeToggle />

      <div className="w-full max-w-[360px]">
        <div
          data-hero-anim
          className="mb-9"
          style={{ animation: "heroFadeUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both" }}
        >
          <h2
            className="mb-2 text-gray-900 dark:text-gray-50"
            style={{ ...hero.formTitle }}
          >
            {title}
          </h2>
          {description && (
            <p className="text-sm leading-relaxed text-gray-500 dark:text-gray-400">
              {description}
            </p>
          )}
        </div>

        <div
          data-hero-anim
          style={{ animation: "heroFadeUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) 0.05s both" }}
        >
          {children}
        </div>

        {footer && (
          <div
            data-hero-anim
            className="mt-9 text-center text-sm text-gray-500 dark:text-gray-400"
            style={{ animation: "heroFadeUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both" }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Dark mode toggle (top-right of form panel) ────────────────────────────────

function DarkModeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const isDark = mounted && (resolvedTheme === "dark" || theme === "dark")
  const Icon = isDark ? RiSunLine : RiMoonLine
  const ariaLabel = isDark ? "Modo claro" : "Modo escuro"

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={ariaLabel}
      className="absolute right-5 top-5 flex size-[34px] items-center justify-center rounded-md border border-gray-200 text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
    >
      {/* Render only after mount to avoid hydration mismatch */}
      {mounted && <Icon className="size-[15px]" aria-hidden="true" />}
    </button>
  )
}

// ── Compound API ──────────────────────────────────────────────────────────────

export const HeroSplitAuth = Object.assign(HeroSplitAuthRoot, {
  Hero,
  HeroSpacer,
  Brand,
  Headline,
  Lede,
  TrustSignals,
  FormPanel,
})

export type { TrustItem }

// ── Default trust signals for Strata FIDC Analytics ───────────────────────────

export const STRATA_TRUST_SIGNALS: TrustItem[] = [
  { icon: RiShieldCheckLine, label: "CVM compliant" },
  { icon: RiLockLine, label: "ISO 27001" },
  { icon: RiDatabase2Line, label: "SOC 2 Type II" },
]

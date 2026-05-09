// src/design-system/surfaces/index.ts
// Barrel export for branded surfaces (login, splash, error pages).
// Surfaces are the ONLY layer permitted to use `tokens.colors.brand` and
// `tokens.typography.hero`. See CLAUDE.md §3 / §4.1 / §4.2.

export {
  HeroSplitAuth,
  STRATA_TRUST_SIGNALS,
  type TrustItem,
} from "./HeroSplitAuth"

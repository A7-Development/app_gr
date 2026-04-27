/**
 * Auth route group layout.
 *
 * Surfaces in `src/design-system/surfaces/*` (e.g. HeroSplitAuth) own their
 * own full-bleed layout, so this wrapper stays minimal — no padding, no
 * max-width, no background. The page itself fills the viewport.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <main className="min-h-svh w-full">{children}</main>
}

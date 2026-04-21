export default function BILayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Modulo BI (bounded context). O shell de filtros antes vivia aqui como
  // barra sticky; apos a convergencia ao Tremor Template Planner os filtros
  // passaram a ser renderizados inline dentro de cada aba/pagina.
  // Layout permanece como marcador explicito do modulo e ponto de extensao
  // futuro (ex.: atalhos cross-L2, breadcrumb root, etc).
  return <>{children}</>
}

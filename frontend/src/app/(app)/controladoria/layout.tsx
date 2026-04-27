export default function ControladoriaLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Modulo Controladoria (bounded context). Mantem o mesmo padrao do BI:
  // wrapper minimo como marcador explicito do modulo e ponto de extensao
  // futuro (ex.: atalhos cross-L2, breadcrumb root). Filtros sao renderizados
  // inline dentro de cada pagina.
  return <>{children}</>
}

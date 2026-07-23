import { redirect } from "next/navigation"

// LANDING = Strata AI (decisao fechada, spec copiloto-mcp §8.1 / Fase 5).
// Um unico ponto de configuracao: trocar a landing no futuro (ou reverter,
// rollback documentado) e editar APENAS esta linha. A antiga home de
// atalhos vive em /inicio.
export default function Home() {
  redirect("/copiloto")
}

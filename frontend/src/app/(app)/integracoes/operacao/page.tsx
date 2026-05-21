import { redirect } from "next/navigation"

// Parent /integracoes/operacao e expand-only na sidebar (CLAUDE.md §11.6 regra 2 —
// o `href: "#operacao"` em modules.ts e identificador semantico, nao destino).
// Quando alguem entra direto em /integracoes/operacao (deep link, refresh),
// cai aqui e e roteado pro primeiro filho.
export default function OperacaoIndexRedirect() {
  redirect("/integracoes/operacao/status")
}

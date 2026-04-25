import { redirect } from "next/navigation"

// Modulo Cadastros — landing redireciona pra L2 inicial.
// Quando outras L2s entrarem (cedentes, sacados, pessoas), virar uma
// pagina-indice com cards. Por agora UA e a unica L2 ativa.
export default function CadastrosLanding() {
  redirect("/cadastros/unidades-administrativas")
}

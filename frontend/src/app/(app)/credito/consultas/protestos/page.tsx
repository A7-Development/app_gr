// src/app/(app)/credito/consultas/protestos/page.tsx
//
// Crédito › Consultas › Protestos — fonte CENPROT-SP (protestosp.com.br).
// Robusta (sem login gov.br), traz cartório + valor + cancelamento/quitação por
// título. NÃO identifica o credor; só SP; retorna só a 1ª página do site.

"use client"

import { ProtestoConsole } from "../_components/ProtestoConsole"

export default function ConsultaProtestosPage() {
  return (
    <ProtestoConsole
      fonte="cenprot_sp"
      title="Protestos"
      subtitle="Crédito · Consultas"
      info="Consulta protestos de um CNPJ/CPF na Central de Protesto de SP (CENPROT-SP). Traz cartório, valor e o status de cancelamento/quitação por título. Não identifica o credor (use 'Protestos · Credor SP' para isso), cobre só SP e retorna apenas a 1ª página do site."
    />
  )
}

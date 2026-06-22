// src/app/(app)/credito/consultas/protestos-credor/page.tsx
//
// Crédito › Consultas › Protestos · Credor (SP) — fonte IEPTB/CENPROT (gov.br).
// Traz o CREDOR (cedente/apresentante) no detalhe de cartórios de SP. Precisa do
// login gov.br (conta pesquisaprotesto.com.br) configurado na credencial
// Infosimples — gated: "acessos em breve".

"use client"

import { ProtestoConsole } from "../_components/ProtestoConsole"

export default function ConsultaProtestosCredorPage() {
  return (
    <ProtestoConsole
      fonte="ieptb_credor"
      title="Protestos · Credor (SP)"
      subtitle="Crédito · Consultas"
      info="Consulta protestos no IEPTB/CENPROT (gov.br) e traz o CREDOR (cedente/apresentante) no detalhe de cartórios de SP. Cobertura nacional para existência; o credor só aparece nos títulos de SP."
      hint="Esta consulta exige acesso gov.br (conta pesquisaprotesto.com.br) configurado na credencial Infosimples — em configuração. Até lá, ela pode retornar erro de credencial."
    />
  )
}

// src/app/(app)/credito/page.tsx
//
// /credito — redireciona para a listagem de dossies (entrada padrao do modulo).

import { redirect } from "next/navigation"

export default function CreditoIndex() {
  redirect("/credito/dossies")
}

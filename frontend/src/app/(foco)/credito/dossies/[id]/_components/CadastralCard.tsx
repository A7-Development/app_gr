// CadastralCard — "Dados cadastrais coletados" (produtor consulta/silver).
//
// MIGRADO pro padrão de blocos (2026-06-19): este componente agora é só um
// wrapper fino que faz o fetch e delega o render ao `<SectionRenderer>` via o
// mapper `cadastralCardToSection` — cada categoria do Contrato vira uma `ficha`.
// Antes era hand-built (fora do vocabulário de blocos, sem rótulo no overlay).
// Lê GET /dossies/{id}/cadastral (projeção dirigida pelo Contrato, white-label).

"use client"

import { useQuery } from "@tanstack/react-query"

import { SectionRenderer } from "@/design-system/components/SectionRenderer"
import { tableTokens } from "@/design-system/tokens/table"
import { credito } from "@/lib/credito-client"

import { cadastralCardToSection } from "../_lib/section-mappers"

export function CadastralCard({ dossierId }: { dossierId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["credito", "cadastral", dossierId],
    queryFn: () => credito.dossies.cadastral(dossierId),
    retry: false,
  })

  if (isLoading) {
    return <p className={tableTokens.cellSecondary}>Carregando dados cadastrais…</p>
  }
  if (isError || !data) {
    return (
      <p className={tableTokens.cellSecondary}>
        Dados cadastrais ainda não coletados para este dossie.
      </p>
    )
  }

  return <SectionRenderer section={cadastralCardToSection(data)} mode="work" />
}

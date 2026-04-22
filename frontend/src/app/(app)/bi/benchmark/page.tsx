"use client"

//
// BI · Benchmark — dados publicos CVM FIDC via postgres_fdw.
//
// Fonte: cvm_remote.* (foreign tables). NAO escopa por tenant (dado publico).
// Proveniencia: source_type='public:cvm_fidc', trust_level='high'.
// Detalhes em docs/integracao-cvm-fidc.md.
//
// Hierarquia de navegacao (CLAUDE.md 11.6):
//   L1 (dropdown): BI
//     L2 (sidebar): Benchmark → /bi/benchmark
//       L3 (TabNavigation): Mercado | Lista de fundos | Ficha do fundo | Comparativo
//
// Estado da URL (deep-linkavel, CLAUDE.md §11.6 regra 3):
//   ?tab=<mercado|lista|ficha|comparativo>
//   ?q=<busca> — usado pela tab Lista
//   ?cnpj=<unico> — usado pela tab Ficha
//   ?cnpjs=<A>&cnpjs=<B>... — usado pela tab Comparativo (max 5)
//

import Link from "next/link"
import * as React from "react"
import { useSearchParams } from "next/navigation"

import { PageHeader } from "@/components/app/PageHeader"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"

import { ComparativoTab } from "./_components/ComparativoTab"
import { FichaFiltersBar } from "./_components/FichaFiltersBar"
import { FichaFundoTab } from "./_components/FichaFundoTab"
import { ListaFundosTab } from "./_components/ListaFundosTab"
import { MercadoTab } from "./_components/MercadoTab"
import { SelecaoStickyBar } from "./_components/SelecaoStickyBar"
import { useBuildTabHref } from "./_hooks/useBenchmarkUrl"

const TABS = [
  { key: "mercado", label: "Mercado" },
  { key: "lista", label: "Lista de fundos" },
  { key: "ficha", label: "Ficha do fundo" },
  { key: "comparativo", label: "Comparativo" },
] as const
type TabKey = (typeof TABS)[number]["key"]

function useActiveTab(): TabKey {
  const sp = useSearchParams()
  const t = sp.get("tab")
  if (t && TABS.some((x) => x.key === t)) return t as TabKey
  return "mercado"
}

const PAGE_INFO =
  "Benchmark do setor FIDC a partir dos Informes Mensais publicados pela CVM. Dado publico, trust_level=high, atualizacao mensal."

// Proveniencia mockada para as tabs que ainda nao consomem endpoint proprio
// (mercado/lista/comparativo). A tab "ficha" renderiza seu proprio rodape a
// partir do endpoint /bi/benchmark/fundo/{cnpj}.
const PROVENANCE_MOCK = {
  source_type: "public:cvm_fidc",
  source_ids: ["cvm_remote.tab_i", "cvm_remote.tab_ii", "cvm_remote.tab_iii"],
  last_sync_at: "2026-04-15T02:15:00Z",
  last_source_updated_at: "2026-04-10T00:00:00Z",
  trust_level: "high" as const,
  ingested_by_version: "cvm_fidc_adapter_v1.0.0",
  row_count: 2_872,
}

export default function BenchmarkPage() {
  const activeTab = useActiveTab()
  const buildTabHref = useBuildTabHref()

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader title="BI · Benchmark" info={PAGE_INFO} />

      <TabNavigation>
        {TABS.map((t) => (
          <TabNavigationLink
            key={t.key}
            asChild
            active={activeTab === t.key}
          >
            <Link href={buildTabHref(t.key)}>{t.label}</Link>
          </TabNavigationLink>
        ))}
      </TabNavigation>

      {activeTab === "ficha" && <FichaFiltersBar />}

      <TabContent tab={activeTab} />

      {activeTab !== "ficha" && (
        <ProvenanceFooter provenance={PROVENANCE_MOCK} />
      )}

      <SelecaoStickyBar />
    </div>
  )
}

function TabContent({ tab }: { tab: TabKey }) {
  switch (tab) {
    case "mercado":
      return <MercadoTab />
    case "lista":
      return <ListaFundosTab />
    case "ficha":
      return <FichaFundoTab />
    case "comparativo":
      return <ComparativoTab />
  }
}

// src/app/(app)/controladoria/relatorios/_components/ReportDetailPage.tsx
//
// Pagina de detalhe compartilhada por:
//   - /controladoria/relatorios/padronizados/[slug]
//   - /controladoria/relatorios/espelho/[admin]/[slug]
//
// Diferenca entre as duas (Opcao A — lente operacional): apenas visual.
// Mesma fonte de dados (silver canonical), mesmo schema, mesma tabela.
// O modo `espelho` mostra a admin no subtitle + (Phase 4) lentes operacionais
// (frescor, reprocessar, logs do sync).
//
// Slugs nao implementados no registry caem em EmptyState "Colunas em breve".

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { RiArrowLeftLine, RiFileChart2Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  DataTableShell,
  EmptyState,
  PageHeader,
} from "@/design-system/components"
import type {
  Provenance,
  ProvenanceSourceType,
  TrustLevel,
} from "@/design-system/types/provenance"

import { getReportEntry } from "@/lib/reports/registry"
import {
  relatorios,
  type ProvenanceMetadata,
  type ReportCard,
} from "../_lib/api"

const ADMIN_LABEL: Record<string, string> = {
  qitech: "QiTech",
}

type Mode = "padronizado" | "espelho"

type Props = {
  slug: string
  mode: Mode
  /** Subdomain do admin no path /espelho/<admin>/<slug>. Apenas quando mode=espelho. */
  admin?: string
}

function adminLabelFor(admin: string | undefined): string {
  if (!admin) return ""
  return ADMIN_LABEL[admin] ?? admin
}

function mapProvenance(meta: ProvenanceMetadata): Provenance | null {
  if (!meta.last_ingested_at) return null
  // Backend devolve `source_type` como "admin:qitech" (ja no formato canonico)
  // e `adapter_version` como string concatenada (ex.: "qitech_adapter_v1.0.0").
  // Quebramos em adapterName + adapterVersion.
  const fullVersion = meta.adapter_version ?? ""
  const splitIdx = fullVersion.lastIndexOf("_v")
  const adapterName =
    splitIdx > 0
      ? fullVersion.slice(0, splitIdx).replace(/_adapter$/, "")
      : meta.source_type.split(":")[1] || meta.source_type
  const adapterVersion = splitIdx > 0 ? fullVersion.slice(splitIdx + 2) : "1.0.0"
  const trust: TrustLevel =
    meta.trust_level === "medium" || meta.trust_level === "low"
      ? meta.trust_level
      : "high"
  return {
    sourceType: meta.source_type as ProvenanceSourceType,
    adapterName,
    adapterVersion,
    ingestedAt: meta.last_ingested_at,
    trustLevel: trust,
  }
}

export function ReportDetailPage({ slug, mode, admin }: Props) {
  const router = useRouter()
  const [search, setSearch] = React.useState("")

  const catalogQuery = useQuery({
    queryKey: ["controladoria", "relatorios", "catalog"],
    queryFn: () => relatorios.catalog(),
    staleTime: 60_000,
  })

  const spec: ReportCard | undefined = catalogQuery.data?.reports.find(
    (r) => r.slug === slug,
  )

  const rowsQuery = useQuery({
    queryKey: ["controladoria", "relatorios", "rows", slug],
    queryFn: () => relatorios.rows(slug, { page_size: 500 }),
    enabled: !!spec,
  })

  const entry = getReportEntry(slug)

  const goBack = React.useCallback(() => {
    const tab = mode === "espelho" ? "espelho" : "padronizados"
    router.push(`/controladoria/relatorios?tab=${tab}`)
  }, [router, mode])

  const subtitle =
    mode === "espelho"
      ? `Controladoria · Espelho ${adminLabelFor(admin)}`.trim()
      : "Controladoria · Relatorio padronizado"

  // Slug nao registrado -> em breve
  if (!entry) {
    return (
      <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
        <PageHeader
          title={spec?.name ?? "Relatorio"}
          subtitle={subtitle}
          actions={
            <Button variant="ghost" onClick={goBack}>
              <RiArrowLeftLine className="mr-1 size-4" aria-hidden />
              Voltar ao catalogo
            </Button>
          }
        />
        <EmptyState
          icon={RiFileChart2Line}
          title="Colunas em breve"
          description={
            spec
              ? `As colunas de "${spec.name}" ainda nao foram tipadas no frontend. ` +
                `Quando demanda surgir, definir em src/lib/reports/${slug}.ts e registrar em registry.ts.`
              : `Slug "${slug}" nao foi encontrado.`
          }
          action={
            <Button variant="primary" onClick={goBack}>
              Voltar ao catalogo
            </Button>
          }
        />
      </div>
    )
  }

  const provenance = rowsQuery.data?.provenance
    ? mapProvenance(rowsQuery.data.provenance)
    : null

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title={spec?.name ?? slug}
        info={spec?.description}
        subtitle={subtitle}
        actions={
          <Button variant="ghost" onClick={goBack}>
            <RiArrowLeftLine className="mr-1 size-4" aria-hidden />
            Voltar ao catalogo
          </Button>
        }
      />

      <DataTableShell
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        data={(rowsQuery.data?.rows ?? []) as any[]}
        columns={entry.columns}
        loading={rowsQuery.isLoading || catalogQuery.isLoading}
        error={(rowsQuery.error ?? null) as Error | null}
        onRetry={() => rowsQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: `Buscar em ${entry.itemNoun.plural}...`,
        }}
        itemNoun={entry.itemNoun}
        provenance={provenance}
        emptyState={{
          icon: RiFileChart2Line,
          title: "Sem dados",
          description: "Nao ha registros para os filtros atuais.",
        }}
      />
    </div>
  )
}

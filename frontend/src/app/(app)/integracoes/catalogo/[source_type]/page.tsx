"use client"

//
// Integracoes · Catalogo · Detalhe — configuracao de uma fonte para o tenant atual.
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 Integracoes > L2 Catalogo > (pagina detalhe)
//     L3 (TabNavigation): Credenciais | Testar | Historico
//
// Deep-link: /integracoes/catalogo/[source_type]?tab=<aba>&environment=<env>

import Link from "next/link"
import * as React from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { RiArrowLeftLine } from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import { AdapterStatusBadge, statusFrom } from "@/design-system/components/AdapterStatusBadge"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import { useSource } from "@/lib/hooks/integracoes"
import type { Environment, SourceTypeId } from "@/lib/api-client"

import { CredenciaisTab } from "./_components/CredenciaisTab"
import { ContasBancariasTab } from "./_components/ContasBancariasTab"
import { CoberturaTab } from "./_components/CoberturaTab"
import { EndpointsTab } from "./_components/EndpointsTab"
import { TestarTab } from "./_components/TestarTab"
import { HistoricoTab } from "./_components/HistoricoTab"

// Source types que tem familia de "Contas bancarias" (admin:qitech usa
// /v2/bank-account/* — saldo + extrato por agencia+conta da UA dona da
// credencial). Bitfin nao tem analogo (extrato vem por SQL direto da DB
// do tenant, sem conta separada).
const SOURCES_WITH_BANK_ACCOUNTS = new Set<SourceTypeId>(["admin:qitech"])

// Source types que tem catalogo de endpoints (cadencia por endpoint —
// CLAUDE.md §13). Sources sem catalogo (bureaus, etc) nao mostram a aba.
// Manter sincronizado com `_CATALOG_BY_SOURCE` em backend public.py.
const SOURCES_WITH_ENDPOINT_CATALOG = new Set<SourceTypeId>([
  "admin:qitech",
  "erp:bitfin",
])

const TABS_BASE = [
  { key: "credenciais", label: "Credenciais" },
  { key: "endpoints", label: "Endpoints" },
  { key: "cobertura", label: "Cobertura" },
  { key: "testar", label: "Testar" },
  { key: "historico", label: "Historico" },
] as const
const TABS_WITH_BANK_ACCOUNTS = [
  { key: "credenciais", label: "Credenciais" },
  { key: "endpoints", label: "Endpoints" },
  { key: "cobertura", label: "Cobertura" },
  { key: "contas-bancarias", label: "Contas bancarias" },
  { key: "testar", label: "Testar" },
  { key: "historico", label: "Historico" },
] as const
const TABS_NO_ENDPOINTS = [
  { key: "credenciais", label: "Credenciais" },
  { key: "testar", label: "Testar" },
  { key: "historico", label: "Historico" },
] as const
type TabKey =
  | (typeof TABS_BASE)[number]["key"]
  | (typeof TABS_WITH_BANK_ACCOUNTS)[number]["key"]
  | (typeof TABS_NO_ENDPOINTS)[number]["key"]

function useActiveTab(tabs: ReadonlyArray<{ key: string }>): TabKey {
  const sp = useSearchParams()
  const t = sp.get("tab")
  if (t && tabs.some((x) => x.key === t)) return t as TabKey
  return "credenciais"
}

function buildHref(
  sourceType: string,
  tab: TabKey,
  environment: Environment,
  uaId?: string | null,
): string {
  const qs = new URLSearchParams()
  qs.set("tab", tab)
  qs.set("environment", environment)
  if (uaId) qs.set("ua", uaId)
  return `/integracoes/catalogo/${encodeURIComponent(sourceType)}?${qs.toString()}`
}

export default function SourceDetailPage() {
  const params = useParams<{ source_type: string }>()
  const sourceType = decodeURIComponent(params.source_type) as SourceTypeId
  const sp = useSearchParams()
  const router = useRouter()
  const hasEndpoints = SOURCES_WITH_ENDPOINT_CATALOG.has(sourceType)
  const tabs = hasEndpoints
    ? SOURCES_WITH_BANK_ACCOUNTS.has(sourceType)
      ? TABS_WITH_BANK_ACCOUNTS
      : TABS_BASE
    : TABS_NO_ENDPOINTS
  const activeTab = useActiveTab(tabs)
  const environment: Environment =
    sp.get("environment") === "sandbox" ? "sandbox" : "production"
  const uaIdParam = sp.get("ua")

  const { data, isLoading, isError, refetch } = useSource(
    sourceType,
    environment,
    uaIdParam,
  )

  function setEnvironment(e: Environment) {
    router.replace(buildHref(sourceType, activeTab, e, uaIdParam))
  }

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title={data?.label ?? sourceType}
        info={data?.description ?? undefined}
        breadcrumbs={[
          { label: "Integracoes", href: "/integracoes/catalogo" },
          { label: "Catalogo", href: "/integracoes/catalogo" },
          { label: data?.label ?? sourceType },
        ]}
        actions={
          <div className="flex items-center gap-3">
            {data && (
              <AdapterStatusBadge
                status={statusFrom(data.configured, data.enabled)}
              />
            )}
            <Select
              value={environment}
              onValueChange={(v) => setEnvironment(v as Environment)}
            >
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="production">Producao</SelectItem>
                <SelectItem value="sandbox">Sandbox</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="secondary" asChild>
              <Link href="/integracoes/catalogo">
                <RiArrowLeftLine className="mr-1.5 size-4" aria-hidden />
                Voltar
              </Link>
            </Button>
          </div>
        }
      />

      {isError && (
        <ErrorState
          title="Nao foi possivel carregar a fonte"
          description="Verifique se o source_type existe no catalogo."
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && (
        <>
          <TabNavigation>
            {tabs.map((t) => (
              <TabNavigationLink
                key={t.key}
                asChild
                active={activeTab === t.key}
              >
                <Link href={buildHref(sourceType, t.key, environment, uaIdParam)}>
                  {t.label}
                </Link>
              </TabNavigationLink>
            ))}
          </TabNavigation>

          {isLoading && (
            <div className="h-40 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          )}

          {!isLoading && data && activeTab === "credenciais" && (
            <CredenciaisTab detail={data} sourceType={sourceType} />
          )}
          {!isLoading && data && activeTab === "endpoints" && (
            <EndpointsTab
              sourceType={sourceType}
              environment={environment}
              uaId={uaIdParam}
            />
          )}
          {!isLoading && data && activeTab === "cobertura" && (
            <CoberturaTab sourceType={sourceType} uaId={uaIdParam} />
          )}
          {!isLoading && data && activeTab === "contas-bancarias" && (
            <ContasBancariasTab detail={data} sourceType={sourceType} />
          )}
          {!isLoading && data && activeTab === "testar" && (
            <TestarTab detail={data} sourceType={sourceType} />
          )}
          {!isLoading && data && activeTab === "historico" && (
            <HistoricoTab sourceType={sourceType} />
          )}
        </>
      )}
    </div>
  )
}

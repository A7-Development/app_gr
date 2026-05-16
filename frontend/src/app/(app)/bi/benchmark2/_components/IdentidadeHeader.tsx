"use client"

import { Badge } from "@/components/tremor/Badge"
import type { FichaFundo } from "@/lib/api-client"

// Cabecalho identificacao do fundo no layout Lamina (Austin Rating style).
// Esse cabecalho fica abaixo do PageHeader da pagina e antes das secoes.

function formatCNPJ(v: string | null): string {
  if (!v) return "—"
  const s = v.replace(/\D/g, "").padStart(14, "0")
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(
    8,
    12,
  )}-${s.slice(12, 14)}`
}

export function IdentidadeHeader({ ficha }: { ficha: FichaFundo }) {
  const id = ficha.identificacao
  const condomRaw = id.condom?.toLowerCase() ?? null
  const condomVariant: "success" | "warning" | "neutral" =
    condomRaw === "aberto"
      ? "success"
      : condomRaw === "fechado"
        ? "warning"
        : "neutral"

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold leading-tight text-gray-900 dark:text-gray-50">
          {id.denom_social ?? "Fundo sem denominacao"}
        </h2>
        <Badge variant={condomVariant}>
          Condominio: {condomRaw ?? "n/d"}
        </Badge>
        {id.classe ? (
          <Badge variant="neutral">{id.classe}</Badge>
        ) : null}
      </div>

      <div className="font-mono text-xs text-gray-500 dark:text-gray-400">
        {formatCNPJ(id.cnpj)}
      </div>

      <div className="mt-1 grid grid-cols-1 gap-x-6 gap-y-0.5 text-xs text-gray-600 dark:text-gray-400 md:grid-cols-2">
        <div>
          <span className="font-medium">Administrador: </span>
          <span>{id.admin ?? "n/d"}</span>
          {id.cnpj_admin ? (
            <>
              <span className="mx-1.5 text-gray-400">·</span>
              <span className="font-mono">{formatCNPJ(id.cnpj_admin)}</span>
            </>
          ) : null}
        </div>
        <div>
          <span className="font-medium">Competencia atual: </span>
          <span>{id.competencia_atual}</span>
          <span className="mx-1.5 text-gray-400">·</span>
          <span className="font-medium">Primeira: </span>
          <span>{id.competencia_primeira}</span>
        </div>
      </div>
    </div>
  )
}

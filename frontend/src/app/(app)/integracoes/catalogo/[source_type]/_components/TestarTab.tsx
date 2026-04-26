"use client"

//
// Tab "Testar" — dispara ping sincronico via adapter e dispara sync manual.
//

import * as React from "react"
import {
  RiCheckLine,
  RiCloseCircleLine,
  RiLoader4Line,
  RiPlayCircleLine,
  RiRefreshLine,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Divider } from "@/components/tremor/Divider"
import { JsonPreview } from "@/design-system/components/JsonPreview"
import { useSyncSource, useTestSource } from "@/lib/hooks/integracoes"
import type { SourceDetail, SourceTypeId } from "@/lib/api-client"

export function TestarTab({
  detail,
  sourceType,
}: {
  detail: SourceDetail
  sourceType: SourceTypeId
}) {
  const testMut = useTestSource(sourceType)
  const syncMut = useSyncSource(sourceType)

  const notConfigured = !detail.configured

  return (
    <div className="flex flex-col gap-6">
      {/* --- Ping --- */}
      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Testar conexao
            </h2>
            {testMut.data && (
              <PingBadge ok={testMut.data.ok} latency={testMut.data.latency_ms} />
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Dispara um ping sincronico via adapter. Seguro — nao altera dado,
            apenas valida credenciais e rede.
          </p>
        </div>

        <Divider />

        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="primary"
            disabled={notConfigured || testMut.isPending}
            onClick={() =>
              testMut.mutate({
                environment: detail.environment,
                uaId: detail.unidade_administrativa_id,
              })
            }
          >
            {testMut.isPending ? (
              <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
            ) : (
              <RiPlayCircleLine className="mr-1.5 size-4" aria-hidden />
            )}
            Testar conexao
          </Button>
        </div>

        {testMut.error && !testMut.data && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            {testMut.error instanceof Error
              ? testMut.error.message
              : "Falha ao executar ping."}
          </div>
        )}

        {testMut.data && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <span>
                Versao: <span className="font-mono">{testMut.data.adapter_version ?? "—"}</span>
              </span>
              {testMut.data.latency_ms !== null && (
                <>
                  <span>·</span>
                  <span>{testMut.data.latency_ms.toFixed(0)} ms</span>
                </>
              )}
            </div>
            <JsonPreview value={testMut.data.detail} maxHeight={240} />
          </div>
        )}

        {notConfigured && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Configure as credenciais antes de testar.
          </p>
        )}
      </Card>

      {/* --- Sync manual --- */}
      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Executar sincronizacao manual
            </h2>
            {syncMut.data && (
              <Badge
                variant={syncMut.data.errors.length ? "warning" : "success"}
              >
                {syncMut.data.errors.length
                  ? `Concluiu com ${syncMut.data.errors.length} erro(s)`
                  : "Sync concluido"}
              </Badge>
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Dispara um ciclo completo em primeiro plano. Pode demorar alguns
            minutos. A execucao e registrada no historico.
          </p>
        </div>

        <Divider />

        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={notConfigured || syncMut.isPending}
            onClick={() =>
              syncMut.mutate({
                environment: detail.environment,
                uaId: detail.unidade_administrativa_id,
              })
            }
          >
            {syncMut.isPending ? (
              <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
            ) : (
              <RiRefreshLine className="mr-1.5 size-4" aria-hidden />
            )}
            Executar sync agora
          </Button>
        </div>

        {syncMut.error && !syncMut.data && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            {syncMut.error instanceof Error
              ? syncMut.error.message
              : "Falha ao executar sync."}
          </div>
        )}

        {syncMut.data && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
              <span>
                Versao: <span className="font-mono">{syncMut.data.adapter_version ?? "—"}</span>
              </span>
              {syncMut.data.elapsed_seconds !== null && (
                <>
                  <span>·</span>
                  <span>{syncMut.data.elapsed_seconds.toFixed(1)}s</span>
                </>
              )}
              {syncMut.data.since && (
                <>
                  <span>·</span>
                  <span>since {syncMut.data.since}</span>
                </>
              )}
            </div>
            <JsonPreview value={syncMut.data} maxHeight={320} />
          </div>
        )}
      </Card>
    </div>
  )
}

function PingBadge({
  ok,
  latency,
}: {
  ok: boolean
  latency: number | null
}) {
  return (
    <Badge variant={ok ? "success" : "error"}>
      {ok ? (
        <RiCheckLine className="mr-1 size-3.5" aria-hidden />
      ) : (
        <RiCloseCircleLine className="mr-1 size-3.5" aria-hidden />
      )}
      {ok ? `OK${latency !== null ? ` · ${latency.toFixed(0)} ms` : ""}` : "Falhou"}
    </Badge>
  )
}

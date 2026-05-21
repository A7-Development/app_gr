"use client"

//
// Tab "Contas bancarias" da pagina de detalhe da QiTech.
//
// Cadastro das contas-corrente da UA acessiveis via familia /v2/bank-account/*
// (saldo + extrato). Cada item vira uma chamada GET para a Singulare quando o
// ETL rodar. CNPJ titular vem da UA dona da credencial — nao se cadastra aqui
// (ver CLAUDE.md §11 — UA e dona do CNPJ).
//
// Persistencia: cada operacao manda PUT /sources/admin:qitech/config com o
// array bank_accounts atualizado. Backend faz merge parcial — preserva
// client_id, client_secret, base_url, etc.
//

import * as React from "react"
import { useSearchParams } from "next/navigation"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { toast } from "sonner"
import {
  RiAddLine,
  RiBankLine,
  RiDeleteBinLine,
  RiInformationLine,
  RiMoreLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { z } from "zod"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { Divider } from "@/components/tremor/Divider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import {
  DataTableShell,
  DrillDownSheet,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import { useUpdateSourceConfig } from "@/lib/hooks/integracoes"
import type { SourceDetail, SourceTypeId } from "@/lib/api-client"
import { cx } from "@/lib/utils"

// ─── Tipos locais ────────────────────────────────────────────────────────────

// Espelha o backend (QiTechBankAccount em backend/.../qitech/config.py).
// Mantido aqui (em vez de api-client.ts global) porque so e usado por esta
// tab — quando o ETL passar a expor /qitech/bank-account/* o tipo migra.
type BankAccount = {
  agencia: string
  conta: string
  label: string
  enabled: boolean
}

const formSchema = z.object({
  agencia: z
    .string()
    .min(1, "Informe a agencia.")
    .regex(/^[0-9]+$/, "Agencia deve conter apenas digitos."),
  conta: z
    .string()
    .min(1, "Informe a conta.")
    .regex(/^[0-9]+$/, "Conta deve conter apenas digitos."),
  label: z.string().max(80, "Maximo 80 caracteres."),
  enabled: z.boolean(),
})

type FormValues = z.infer<typeof formSchema>

const EMPTY_FORM: FormValues = {
  agencia: "",
  conta: "",
  label: "",
  enabled: true,
}

// ─── Util ────────────────────────────────────────────────────────────────────

function accountKey(a: { agencia: string; conta: string }): string {
  return `${a.agencia}-${a.conta}`
}

function readBankAccounts(detail: SourceDetail): BankAccount[] {
  const raw = detail.config["bank_accounts"]
  if (!Array.isArray(raw)) return []
  const out: BankAccount[] = []
  for (const item of raw) {
    if (typeof item !== "object" || item === null) continue
    const r = item as Record<string, unknown>
    if (typeof r.agencia !== "string" || !r.agencia) continue
    if (typeof r.conta !== "string" || !r.conta) continue
    out.push({
      agencia: r.agencia,
      conta: r.conta,
      label: typeof r.label === "string" ? r.label : "",
      enabled: typeof r.enabled === "boolean" ? r.enabled : true,
    })
  }
  return out
}

// ─── Componente raiz ─────────────────────────────────────────────────────────

export function ContasBancariasTab({
  detail,
  sourceType,
}: {
  detail: SourceDetail
  sourceType: SourceTypeId
}) {
  const sp = useSearchParams()
  const uaId = sp.get("ua")

  const accounts = React.useMemo(() => readBankAccounts(detail), [detail])

  const updateMut = useUpdateSourceConfig(sourceType)

  // Mode local (nao deep-linkavel ainda — pode promover a query string depois).
  const [mode, setMode] = React.useState<
    | { kind: "closed" }
    | { kind: "new" }
    | { kind: "edit"; original: BankAccount }
  >({ kind: "closed" })
  const [pendingDelete, setPendingDelete] = React.useState<BankAccount | null>(
    null,
  )

  // ── Persistencia ────────────────────────────────────────────────────────
  const persist = React.useCallback(
    async (next: BankAccount[]) => {
      await updateMut.mutateAsync({
        config: { bank_accounts: next },
        environment: detail.environment,
        unidade_administrativa_id: uaId,
      })
    },
    [updateMut, detail.environment, uaId],
  )

  const handleCreate = React.useCallback(
    async (values: FormValues) => {
      // UQ: nao permitir (agencia, conta) duplicado.
      const exists = accounts.some(
        (a) => a.agencia === values.agencia && a.conta === values.conta,
      )
      if (exists) {
        toast.error(
          `Ja existe conta cadastrada para agencia ${values.agencia} / conta ${values.conta}.`,
        )
        return
      }
      const next: BankAccount[] = [...accounts, values]
      try {
        await persist(next)
        toast.success("Conta cadastrada.")
        setMode({ kind: "closed" })
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao cadastrar conta.",
        )
      }
    },
    [accounts, persist],
  )

  const handleEdit = React.useCallback(
    async (original: BankAccount, values: FormValues) => {
      // UQ: se trocou agencia/conta, nao pode colidir com outra existente.
      const collides = accounts.some(
        (a) =>
          accountKey(a) !== accountKey(original) &&
          a.agencia === values.agencia &&
          a.conta === values.conta,
      )
      if (collides) {
        toast.error(
          `Ja existe outra conta com agencia ${values.agencia} / conta ${values.conta}.`,
        )
        return
      }
      const next = accounts.map((a) =>
        accountKey(a) === accountKey(original) ? values : a,
      )
      try {
        await persist(next)
        toast.success("Conta atualizada.")
        setMode({ kind: "closed" })
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao atualizar conta.",
        )
      }
    },
    [accounts, persist],
  )

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    const next = accounts.filter(
      (a) => accountKey(a) !== accountKey(pendingDelete),
    )
    try {
      await persist(next)
      toast.success("Conta excluida.")
      setPendingDelete(null)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao excluir conta.",
      )
    }
  }, [pendingDelete, accounts, persist])

  // ── Estados de orientacao ───────────────────────────────────────────────
  // Tab so faz sentido com UA selecionada e credenciais salvas. Aviso quando
  // qualquer das pre-condicoes faltar — usuario nao deveria conseguir
  // cadastrar conta antes de a UA + creds estarem amarradas.
  if (!uaId) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <RiInformationLine
            className="mt-0.5 size-5 text-gray-500 dark:text-gray-400"
            aria-hidden
          />
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              Selecione a Unidade Administrativa
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Contas bancarias sao vinculadas ao CNPJ da UA dona da credencial.
              Volte para a aba <span className="font-medium">Credenciais</span> e
              escolha a UA antes de cadastrar contas.
            </p>
          </div>
        </div>
      </Card>
    )
  }

  if (!detail.configured) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <RiInformationLine
            className="mt-0.5 size-5 text-gray-500 dark:text-gray-400"
            aria-hidden
          />
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              Cadastre as credenciais primeiro
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Sem <span className="font-mono">client_id</span> +{" "}
              <span className="font-mono">client_secret</span> validos para esta
              UA, nao e possivel chamar a API QiTech. Volte para a aba{" "}
              <span className="font-medium">Credenciais</span>, salve as creds e
              retorne.
            </p>
          </div>
        </div>
      </Card>
    )
  }

  // ── Tabela ──────────────────────────────────────────────────────────────
  const col = createColumnHelper<BankAccount>()
  const columns: ColumnDef<BankAccount, unknown>[] = [
    col.accessor("label", {
      header: "Apelido",
      size: 220,
      cell: (info) => {
        const v = info.getValue()
        return v ? (
          <span className={tableTokens.cellText}>{v}</span>
        ) : (
          <span className={tableTokens.cellMuted}>—</span>
        )
      },
    }) as ColumnDef<BankAccount, unknown>,
    col.accessor("agencia", {
      header: "Agencia",
      size: 100,
      cell: (info) => (
        <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
      ),
    }) as ColumnDef<BankAccount, unknown>,
    col.accessor("conta", {
      header: "Conta",
      size: 140,
      cell: (info) => (
        <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
      ),
    }) as ColumnDef<BankAccount, unknown>,
    col.accessor("enabled", {
      header: "Status",
      size: 110,
      cell: (info) => <StatusBadge enabled={info.getValue()} />,
    }) as ColumnDef<BankAccount, unknown>,
    col.display({
      id: "actions",
      header: "",
      size: 56,
      cell: ({ row }) => (
        <div className="flex justify-end">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="size-7 p-0"
                aria-label={`Acoes da conta ${row.original.agencia}/${row.original.conta}`}
                onClick={(e) => e.stopPropagation()}
              >
                <RiMoreLine className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={4}>
              <DropdownMenuItem
                onSelect={() =>
                  setMode({ kind: "edit", original: row.original })
                }
              >
                Editar
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => setPendingDelete(row.original)}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                Excluir
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      ),
    }) as ColumnDef<BankAccount, unknown>,
  ]

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Contas bancarias da UA
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Contas usadas pelas APIs{" "}
              <span className="font-mono">/v2/bank-account/balance</span> e{" "}
              <span className="font-mono">/v2/bank-account/statement</span> da
              QiTech. O CNPJ titular vem implicitamente da UA dona desta
              credencial — nao precisa cadastrar aqui.
            </p>
          </div>
          <Button
            variant="primary"
            onClick={() => setMode({ kind: "new" })}
            disabled={updateMut.isPending}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova conta
          </Button>
        </div>
      </Card>

      <DataTableShell<BankAccount>
        data={accounts}
        columns={columns}
        loading={false}
        onRowClick={(a) => setMode({ kind: "edit", original: a })}
        itemNoun={{ singular: "conta", plural: "contas" }}
        emptyState={{
          icon: RiBankLine,
          title: "Nenhuma conta cadastrada",
          description:
            "Cadastre a primeira conta-corrente para sincronizar saldo e extrato dessa UA.",
          action: (
            <Button
              variant="primary"
              onClick={() => setMode({ kind: "new" })}
              disabled={updateMut.isPending}
            >
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Nova conta
            </Button>
          ),
        }}
      />

      {/* Drawer: Nova conta */}
      <DrillDownSheet
        open={mode.kind === "new"}
        onClose={() => setMode({ kind: "closed" })}
        title="Nova conta bancaria"
        size="md"
      >
        <div className="p-6">
          <BankAccountForm
            initial={EMPTY_FORM}
            submitting={updateMut.isPending}
            onSubmit={handleCreate}
            onCancel={() => setMode({ kind: "closed" })}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar conta */}
      <DrillDownSheet
        open={mode.kind === "edit"}
        onClose={() => setMode({ kind: "closed" })}
        title={
          mode.kind === "edit"
            ? `Editar · ${mode.original.label || `${mode.original.agencia}/${mode.original.conta}`}`
            : ""
        }
        size="md"
      >
        {mode.kind === "edit" && (
          <div className="p-6">
            <BankAccountForm
              initial={mode.original}
              submitting={updateMut.isPending}
              onSubmit={(v) => handleEdit(mode.original, v)}
              onCancel={() => setMode({ kind: "closed" })}
            />
          </div>
        )}
      </DrillDownSheet>

      {/* Confirmacao destrutiva */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir conta bancaria</DialogTitle>
            <DialogDescription>
              Esta acao remove o cadastro da conta{" "}
              <span className="font-mono text-gray-900 dark:text-gray-50">
                {pendingDelete?.agencia}/{pendingDelete?.conta}
              </span>{" "}
              {pendingDelete?.label && (
                <>
                  ({pendingDelete.label}){" "}
                </>
              )}
              desta UA. Dados ja sincronizados de saldo/extrato no warehouse
              sao preservados — apenas as proximas chamadas pararao de incluir
              esta conta.
            </DialogDescription>
          </DialogHeader>

          <Divider />

          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={updateMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={updateMut.isPending}
            >
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Excluir conta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── Cells ──────────────────────────────────────────────────────────────────

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cx(
        tableTokens.badgeWithDot,
        enabled
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
          : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "size-1.5 rounded-full",
          enabled ? "bg-emerald-500" : "bg-gray-400",
        )}
      />
      {enabled ? "Ativa" : "Inativa"}
    </span>
  )
}

// ─── Form ───────────────────────────────────────────────────────────────────

function BankAccountForm({
  initial,
  submitting,
  onSubmit,
  onCancel,
}: {
  initial: FormValues
  submitting: boolean
  onSubmit: (values: FormValues) => void
  onCancel: () => void
}) {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: initial,
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="ba-label">Apelido</Label>
        <Input
          id="ba-label"
          placeholder="Conta principal, Cobranca, Garantia..."
          hasError={Boolean(errors.label)}
          {...register("label")}
        />
        {errors.label ? (
          <span className="text-xs text-red-600 dark:text-red-500">
            {errors.label.message}
          </span>
        ) : (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Opcional. Usado so na UI — nao viaja para a QiTech.
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ba-agencia">
            Agencia
            <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>
              *
            </span>
          </Label>
          <Input
            id="ba-agencia"
            placeholder="0001"
            hasError={Boolean(errors.agencia)}
            {...register("agencia")}
          />
          {errors.agencia ? (
            <span className="text-xs text-red-600 dark:text-red-500">
              {errors.agencia.message}
            </span>
          ) : (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Informe como aparece no portal Singulare — geralmente 4 digitos
              com zero a esquerda (ex.: 0001).
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ba-conta">
            Conta
            <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>
              *
            </span>
          </Label>
          <Input
            id="ba-conta"
            placeholder="4532551"
            hasError={Boolean(errors.conta)}
            {...register("conta")}
          />
          {errors.conta ? (
            <span className="text-xs text-red-600 dark:text-red-500">
              {errors.conta.message}
            </span>
          ) : (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Sem digito verificador, como aparece no path da QiTech.
            </span>
          )}
        </div>
      </div>

      <Divider />

      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="ba-enabled" className="text-sm font-medium">
            Conta ativa
          </Label>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Quando desligada, e ignorada nas sincronizacoes de saldo e extrato.
          </span>
        </div>
        <Controller
          control={control}
          name="enabled"
          render={({ field }) => (
            <Switch
              id="ba-enabled"
              checked={field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
      </div>

      <Divider />

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting}>
          Salvar conta
        </Button>
      </div>
    </form>
  )
}

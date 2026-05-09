import { cx } from "@/lib/utils"

type Variant = "bars" | "area" | "line" | "table"

type Props = {
  variant: Variant
  className?: string
}

// Alturas estaveis (seed fixo) — evita layout shift entre re-renders
// e mantem o skeleton determinstico durante SSR/hydrate.
const BAR_HEIGHTS = [0.42, 0.68, 0.55, 0.81, 0.47, 0.73, 0.38, 0.90, 0.62, 0.51, 0.77, 0.58]

// Larguras variadas para skeleton de tabela — 6 rows x 4 cols.
const TABLE_CELL_WIDTHS = [
  ["w-24", "w-16", "w-20", "w-12"],
  ["w-32", "w-14", "w-16", "w-14"],
  ["w-20", "w-20", "w-24", "w-10"],
  ["w-28", "w-12", "w-20", "w-12"],
  ["w-24", "w-16", "w-16", "w-14"],
  ["w-32", "w-14", "w-24", "w-10"],
]

export function ChartSkeleton({ variant, className }: Props) {
  return (
    <div
      role="status"
      aria-label="Carregando dados"
      className={cx("w-full", className)}
    >
      {variant === "bars" && <BarsSkeleton />}
      {variant === "area" && <AreaSkeleton fill />}
      {variant === "line" && <AreaSkeleton fill={false} />}
      {variant === "table" && <TableSkeleton />}
    </div>
  )
}

function BarsSkeleton() {
  return (
    <div className="flex size-full items-end gap-2 px-2 pb-6 pt-2">
      {BAR_HEIGHTS.map((h, i) => (
        <div
          key={i}
          className="flex-1 animate-pulse rounded-t-sm bg-gray-100 dark:bg-gray-900"
          style={{ height: `${h * 100}%` }}
        />
      ))}
    </div>
  )
}

function AreaSkeleton({ fill }: { fill: boolean }) {
  return (
    <svg
      viewBox="0 0 400 200"
      preserveAspectRatio="none"
      className="size-full animate-pulse"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="chart-skeleton-gradient" x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0%"
            className="text-gray-200 dark:text-gray-800"
            stopColor="currentColor"
            stopOpacity="0.6"
          />
          <stop
            offset="100%"
            className="text-gray-200 dark:text-gray-800"
            stopColor="currentColor"
            stopOpacity="0"
          />
        </linearGradient>
      </defs>
      {fill && (
        <path
          d="M 0 150 C 40 120, 80 180, 120 140 S 200 80, 240 110 S 320 160, 400 90 L 400 200 L 0 200 Z"
          fill="url(#chart-skeleton-gradient)"
        />
      )}
      <path
        d="M 0 150 C 40 120, 80 180, 120 140 S 200 80, 240 110 S 320 160, 400 90"
        fill="none"
        className="stroke-gray-200 dark:stroke-gray-800"
        strokeWidth="2"
      />
    </svg>
  )
}

function TableSkeleton() {
  return (
    <div className="flex size-full flex-col gap-3 p-2">
      {TABLE_CELL_WIDTHS.map((row, i) => (
        <div key={i} className="flex items-center gap-4">
          {row.map((w, j) => (
            <div
              key={j}
              className={cx(
                "h-3 animate-pulse rounded bg-gray-100 dark:bg-gray-900",
                w,
              )}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

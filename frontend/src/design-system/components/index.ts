// src/design-system/components/index.ts
// Barrel export for all FIDC domain components.

// ── Strata canonical components ───────────────────────────────────────────────
export { StatusPill, STATUS_CONFIG, type StatusPillProps, type StatusKey } from "./StatusPill"
export { ApprovalQueueBadge, type ApprovalQueueBadgeProps } from "./ApprovalQueueBadge"
export {
  KpiCard, KpiStrip, KpiIntensity, Sparkline,
  FIDC_KPI_META,
  type KpiCardProps, type KpiDelta, type SparklineProps,
  type IntensityTone, type IntensityLevel,
} from "./KpiStrip"
export {
  FilterBar, FilterSearch, FilterChip, RemovableChip,
  MoreFiltersButton, SavedViewsDropdown,
  type SavedView,
} from "./FilterBar"
export {
  DataTable,
  CurrencyCell, PercentageCell, DateCell, StatusCell,
  IdCell, CpfCnpjCell, RelationshipCell, SparklineCell, ProgressCell,
  type DataTableProps,
} from "./DataTable"
export {
  AppSidebar, useSidebarCollapsed,
  type AppSidebarProps, type BadgeCounts,
} from "./Sidebar"
export {
  DrillDownSheet,
  DrillDownHeader, DrillDownHero, DrillDownTabs, DrillDownBody,
  DrillDownTimeline, DrillDownFooter,
  PropertyList,
  type DrillDownSheetProps, type SheetSize,
  type TabDef, type PropertyRowDef, type LinkedObject,
  type TimelineEventDef, type FIDCEventType,
} from "./DrillDownSheet"
export {
  CommandPaletteProvider, CommandPaletteModal, useCommandPalette,
  type CommandItem, type CommandPaletteProviderProps,
} from "./CommandPalette"
export {
  EChartsCard, SparkChart, useEChartsTheme,
  type EChartsCardProps, type SparkChartProps,
} from "./EChartsCard"
export {
  AIPanel, AIToggleButton, useAIPanel, AI_PANEL_STORAGE_KEY,
  type AIPanelProps, type AIContext, type AIInsight, type AIMessage, type SendMessageFn,
} from "./AIPanel"

// ── A7 Credit domain composites (migrated from components/app/) ──────────────
export { AdapterStatusBadge } from "./AdapterStatusBadge"
export { AuthGuard } from "./AuthGuard"
export { HeaderBreadcrumbs } from "./Breadcrumbs"
export { CardMenu, type MenuSection } from "./CardMenu"
export { ChartSkeleton } from "./ChartSkeleton"
export { CompactSeriesTable } from "./CompactSeriesTable"
export { DropdownUserProfile } from "./DropdownUserProfile"
export { EmptyState } from "./EmptyState"
export { ErrorState } from "./ErrorState"
export { FilterPill, type FilterPillOption } from "./FilterPill"
export { InfoTooltip } from "./InfoTooltip"
export { Insight, InsightBar, type InsightTone } from "./Insight"
export { JsonPreview } from "./JsonPreview"
export { LastSyncCell } from "./LastSyncCell"
export { Logo } from "./Logo"
export { ModuleSwitcher } from "./ModuleSwitcher"
export { StrataIcon } from "./StrataIcon"
export { MonthRangePicker, type MonthRange } from "./MonthRangePicker"
export { OriginDot } from "./OriginDot"
export { OverrideChip } from "./OverrideChip"
export { PageHeader } from "./PageHeader"
export { PeriodoPresets } from "./PeriodoPresets"
export { SecretInput } from "./SecretInput"
export { Stepper } from "./Stepper"
export { UserProfile } from "./UserProfile"
export { VizCard } from "./VizCard"

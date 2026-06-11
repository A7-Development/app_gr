// src/design-system/components/index.ts
// Barrel export for all FIDC domain components.

// ── Tipos compartilhados ─────────────────────────────────────────────────────
export {
  type Provenance,
  type ProvenanceSourceType,
  type TrustLevel,
  TRUST_DOT_COLOR,
  formatAdapterId,
  formatSourceLabel,
  formatProvenanceTooltip,
  dedupeProvenances,
} from "@/design-system/types/provenance"

// ── Strata canonical components ───────────────────────────────────────────────
export { StatusPill, STATUS_CONFIG, type StatusPillProps, type StatusKey } from "./StatusPill"
export { ApprovalQueueBadge, type ApprovalQueueBadgeProps } from "./ApprovalQueueBadge"
export {
  KpiCard, KpiStrip, KpiIntensity, Sparkline,
  FIDC_KPI_META,
  type KpiCardProps, type KpiDelta, type SparklineProps,
  type IntensityTone, type IntensityLevel,
} from "./KpiStrip"
export { KpiTile, type KpiTileProps, type KpiTileDelta } from "./KpiTile"
export {
  KpiHeadline,
  type KpiHeadlineProps, type KpiHeadlinePrimary,
  type KpiHeadlineDiagnostic, type KpiHeadlineTone, type DiagnosticTone,
} from "./KpiHeadline"
export {
  KpiBand,
  type KpiBandProps, type KpiBandItem, type KpiBandTone,
} from "./KpiBand"
export {
  FilterBar, FilterSearch, FilterChip, RemovableChip,
  MoreFiltersButton, SavedViewsDropdown,
  type SavedView,
} from "./FilterBar"
export {
  DataTable,
  CurrencyCell, PercentageCell, DateCell, StatusCell,
  IdCell, CpfCnpjCell, RelationshipCell, SparklineCell, ProgressCell,
  StepProgressCell, NextActionCell,
  type DataTableProps,
  type NextActionKind as NextActionCellKind,
} from "./DataTable"
export {
  DataTableShell,
  type DataTableShellProps,
  type ShellSearchConfig,
  type ShellSegmentOption,
  type ShellSegmentsConfig,
  type ShellEmptyState,
} from "./DataTableShell"
export {
  AppSidebar, useSidebarCollapsed, setSidebarCollapsed, toggleSidebarCollapsed,
  SidebarTrigger, BrandCard, UserProfileDropdown,
  type AppSidebarProps, type BadgeCounts,
  type SidebarTriggerProps, type BrandCardProps,
  type UserProfileDropdownProps, type UserCommand,
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
  EditorialChartCard,
  buildEditorialAreaOption,
  editorialChartColors,
  type EditorialChartCardProps,
  type EditorialAreaOptions,
  type EditorialAreaSeries,
} from "./EditorialChartCard"
export {
  EvolucaoMensalCard, EvolucaoMensalDestaquesView,
  type EvolucaoMensalCardProps,
  type EvolucaoMensalPonto,
  type EvolucaoMensalVariant,
  type EvolucaoMensalDimensionConfig,
  type EvolucaoMensalDimensionOption,
  type EvolucaoMensalMesDestaque,
  type EvolucaoMensalVsMesAnterior,
  type EvolucaoMensalDestaques,
} from "./EvolucaoMensalCard"
export {
  EvolucaoDiariaCard,
  type EvolucaoDiariaCardProps,
  type EvolucaoDiariaPonto,
  type EvolucaoDiariaSerie,
  type EvolucaoDiariaOverlay,
} from "./EvolucaoDiariaCard"
export {
  AIPanel, AIToggleButton, useAIPanel, AI_PANEL_STORAGE_KEY,
  type AIPanelProps, type AIContext, type AIInsight, type AIMessage, type SendMessageFn,
} from "./AIPanel"
export {
  SaveIndicator,
  type SaveIndicatorProps, type SaveIndicatorState,
} from "./SaveIndicator"
export {
  WizardTopRail,
  type WizardTopRailProps, type WizardTopRailMeta, type WizardStepLite,
} from "./WizardTopRail"
export {
  WizardSideMicro,
  type WizardSideMicroProps, type WizardSideMicroStep, type WizardSideMicroStepState,
} from "./WizardSideMicro"
export {
  WizardWorkspace,
  WaitingInputView, AgentRunningView, AgentCompletedView, FailedView, BlockedView,
  type WizardWorkspaceProps, type WizardWorkspaceStep, type WizardWorkspaceStepState,
} from "./WizardWorkspace"
export {
  AgentLiveStatus,
  type AgentLiveStatusProps, type AgentToolLogEntry,
} from "./AgentLiveStatus"
export {
  AgentOutputRenderer,
  OpinionView, IndebtednessView, FinancialView, LegalView, PartnerView,
  CrossReferenceView, DocumentExtractorView, JsonView, DeterministicCheckView,
  type AgentOutputRendererProps, type Recommendation, type RedFlag,
  type OpinionDraft, type IndebtednessAnalysis, type DeterministicFlag,
} from "./AgentOutputRenderer"
export {
  FileUploadZone,
  type FileUploadZoneProps, type FileUploadStatus,
} from "./FileUploadZone"
export {
  FileList,
  type FileListProps, type FileListItem,
} from "./FileList"
export {
  StepNoteEditor, StepNoteList,
  type StepNoteEditorProps, type StepNoteEditorMode,
  type StepNoteListProps, type StepNoteListItem,
} from "./StepNoteEditor"
export {
  LinkInput, LinkList,
  type LinkInputProps, type LinkInputValues,
  type LinkListProps, type LinkListItem,
} from "./LinkInput"
export {
  InconsistencyList,
  type InconsistencyListProps, type InconsistencyItem, type InconsistencySeverity,
} from "./InconsistencyList"
export {
  EvidencePanel,
  type EvidencePanelProps, type EvidenceFilterScope,
} from "./EvidencePanel"

// ── A7 Credit domain composites (migrated from components/app/) ──────────────
export { AdapterStatusBadge } from "./AdapterStatusBadge"
export { AuthGuard } from "./AuthGuard"
export { HeaderBreadcrumbs } from "./Breadcrumbs"
export { CardMenu, type MenuSection } from "./CardMenu"
export { ChartSkeleton } from "./ChartSkeleton"
export { CompactSeriesTable } from "./CompactSeriesTable"
export {
  DashboardHeaderActions,
  type DashboardHeaderActionsProps,
  type DashboardHeaderMoreItem,
} from "./DashboardHeaderActions"
export { DropdownUserProfile } from "./DropdownUserProfile"
export { EmptyState } from "./EmptyState"
export { EntidadeLink } from "./EntidadeLink"
export { EntidadePeek } from "./EntidadePeek"
export { ErrorState } from "./ErrorState"
export {
  CoverageHeatmap,
  deriveHealth,
  HEALTH_STYLES,
  type DataHealth,
} from "./CoverageHeatmap"
export {
  QiTechCoverageStrip,
  buildEntry as buildCoverageStripEntry,
  isEntryHealthy as isCoverageStripEntryHealthy,
  type CoverageStripEntry,
  type QiTechCoverageStripProps,
} from "./QiTechCoverageStrip"
export { FilterPill, type FilterPillOption } from "./FilterPill"
export { InfoTooltip } from "./InfoTooltip"
export {
  Insight, InsightBar,
  type InsightTone, type InsightBarVariant, type InsightBarItem,
} from "./Insight"
export { InsightStrip, type InsightStripItem } from "./InsightStrip"
export { JsonPreview } from "./JsonPreview"
export { LastSyncCell } from "./LastSyncCell"
export { SyncHealthBadge } from "./SyncHealthBadge"
export { Logo } from "./Logo"
export { DynamicForm } from "./DynamicForm"
export { ModuleSwitcher } from "./ModuleSwitcher"
export { StrataIcon } from "./StrataIcon"
export { StrataConclusaoBadge } from "./StrataConclusaoBadge"
export { MonthRangePicker, type MonthRange } from "./MonthRangePicker"
export { OriginDot } from "./OriginDot"
export { OverrideChip } from "./OverrideChip"
export { PageHeader } from "./PageHeader"
export { PeriodoPresets } from "./PeriodoPresets"
export { ProvenanceFooter, type ProvenanceSource } from "./ProvenanceFooter"
export { SecretInput } from "./SecretInput"
export { SegmentSwitch, type SegmentDef, type SegmentSwitchProps } from "./SegmentSwitch"
export { Stepper } from "./Stepper"
export { UserProfile } from "./UserProfile"
export { VizCard } from "./VizCard"
export { VizParam } from "./VizParam"

// ── Aba Mes Corrente (variance decomposition, BI · Operacoes2) ───────────────
export {
  VarianceBridgeCard,
  type VarianceBridgeCardProps,
} from "./VarianceBridgeCard"
export { PvmBridgeCard, type PvmBridgeCardProps } from "./PvmBridgeCard"
export { DumbbellCard, type DumbbellCardProps } from "./DumbbellCard"
export { MixDeltaBarCard, type MixDeltaBarCardProps } from "./MixDeltaBarCard"
export {
  ConcentracaoDeltaCard,
  type ConcentracaoDeltaCardProps,
} from "./ConcentracaoDeltaCard"

// ── Esteira de crédito — Conceito D (handoff 2026-06-10) ────────────────────
// Linguagem de proveniência (4 assinaturas) + chassi de estação.
export {
  ProvenanceChip,
  ProvenanceTile,
  ProvenanceSup,
  ProvenanceValue,
  PROVENANCE_ICON,
  type ProvenanceChipProps,
  type ProvenanceOrigin,
} from "./Provenance"
export { AgentConclusion, type AgentConclusionProps } from "./AgentConclusion"
export { DiffRemoved, DiffInserted, PreviousValue } from "./DiffText"
export { AgentLiveChip, AgentPulseDot, type AgentLiveChipProps } from "./AgentLiveChip"
export {
  StationStateChip,
  type StationStateChipProps,
  type StationStateChipVariant,
} from "./StationStateChip"
export { ClosureBar, type ClosureBarProps, type ClosureBarState } from "./ClosureBar"
export {
  KpiChartCard,
  type KpiChartCardProps,
  type KpiChartDatum,
} from "./KpiChartCard"
export { FocusRail, type FocusRailItem, type FocusRailProps } from "./FocusRail"
export {
  StationsSidebar,
  type StationItem,
  type StationState,
  type StationsSidebarProps,
} from "./StationsSidebar"
export {
  StationHeader,
  type StationHeaderProps,
  type StationSubstep,
} from "./StationHeader"

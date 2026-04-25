# Auditabilidade — decision_log e premise_set

Referência detalhada para §14 do CLAUDE.md.

## Tabela `decision_log` (append-only)

Toda decisão/cálculo/sync do sistema é registrado aqui. Particionada por tenant + data.

**Append-only:** sem UPDATE, sem DELETE. Correção se dá por NOVA entrada que referencia a anterior.

**Campos:**

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK, NOT NULL |
| `occurred_at` | timestamptz | quando ocorreu |
| `decision_type` | enum | "sync", "calculation", "alert", "recommendation", "score", "reconciliation_check", ... |
| `inputs_ref` | JSON / FK | referência aos inputs usados |
| `rule_or_model` | text | nome da regra ou modelo |
| `rule_or_model_version` | text | versão da regra (imutável após decisão) |
| `output` | JSON | resultado produzido |
| `explanation` | text | top-N fatores que geraram o output (obrigatório para scores/alertas) |
| `triggered_by` | uuid / text | user_id ou "system:scheduler" |

## Tabela `premise_set`

Premissas de cálculos/projeções (taxa CDI, curva, tolerâncias, cortes) — cada edição cria nova versão. Projeção referencia o `premise_set_id` usado; histórico preservado para replay.

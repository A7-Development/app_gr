// app/(foco)/credito/dossies/[id]/_lib/section-mappers.ts
//
// INTERIM (Fase 1 / Etapa 2): mappers que convertem o output tipado de cada
// agente -> SectionDescriptor (camada de JULGAMENTO). Provam que o vocabulário
// de blocos cobre as 3 análises com a MESMA gramática.
//
// Por que frontend e por que interim: a decisão A1 é que o BACKEND constrói o
// descritor (derivado do output_schema + ui-hints). Na Etapa 4 estes mappers
// migram pro backend (descriptor-builder dirigido pelo grafo + Contratos de
// Dados). Aqui ficam só pra destravar a tela sem esperar o pipeline backend.
// Ver docs/esteira-credito-interface-camadas.md §5 (Etapas 1.2 vs 1.3).

import type { ProvenanceRef } from "@/design-system/tokens/provenance"
import type {
  Apontamento,
  Block,
  SectionDescriptor,
} from "@/design-system/types/section"
import type {
  CadastralAnalysis,
  CadastralCampo,
  CadastralCard as CadastralCardData,
  RevenueAnalysis,
  SocialContractAnalysis,
} from "@/lib/credito-client"

// ─── Assinaturas de proveniência (F4 — regra estrutural, 2026-06-18) ──────────
//
// A origem de cada valor é DETERMINÍSTICA pelo fluxo do dado, não subjetiva:
//   • agente    → leitura / julgamento / cálculo do agente (tendência, aderência,
//                 "soma confere", credibilidade, pontos de atenção). Pontilhada
//                 enquanto pendente; assenta em contínua ao homologar (E3).
//   • fonte     → fato echoado de bureau/silver (situação cadastral). Contínua.
//   • documento → valor levantado verbatim do doc enviado (poderes de assinatura,
//                 cláusulas estatutárias). Tracejada.
//   • analista  → o que o humano edita (campo "Sua análise"). Dupla.
//
// INTERIM: o mapper roda no front sobre o output do agente, que NÃO carrega o
// localizador (página/bbox do doc, tabela/campo silver, runId). Por isso aqui só
// a ASSINATURA visível (cor + ícone + forma de linha) — sem `locator`, pra não
// fabricar drill (§14: localizador inventado = sistema mentindo sobre origem). O
// "ver evidência" liga quando o backend emitir o ponteiro real (Etapa 4).
const P_AGENTE: ProvenanceRef = { origin: "agente", homologado: false }
const P_FONTE: ProvenanceRef = { origin: "fonte" }
const P_DOC: ProvenanceRef = { origin: "documento" }

// "alta/media/baixa" (revenue, cadastral) -> severidade canônica do bloco.
function sevFromPt(s: string): Apontamento["severidade"] {
  return s === "alta" ? "critico" : s === "media" ? "atencao" : "info"
}

// status do checklist (social) -> severidade canônica do bloco.
function sevFromChecklist(s: string): Apontamento["severidade"] {
  return s === "critical" ? "critico" : s === "alert" ? "atencao" : "info"
}

// ─── Faturamento (revenue_analyst) ───────────────────────────────────────────

export function revenueToSection(output: RevenueAnalysis): SectionDescriptor {
  const blocks: Block[] = [
    {
      id: "rev-conclusao",
      type: "conclusao_agente",
      agente: "Faturamento",
      resumo: output.resumo_executivo,
      homologado: false,
    },
    {
      id: "rev-leituras",
      type: "ficha",
      campos: [
        {
          label: "Tendência",
          valor: `${output.tendencia.direcao} · ${output.tendencia.intensidade}`,
          nota: output.tendencia.leitura,
          provenance: P_AGENTE,
        },
        {
          label: "Sazonalidade",
          valor: output.sazonalidade.detectada ? "Detectada" : "Sem padrão claro",
          nota: output.sazonalidade.padrao ?? undefined,
          badge: output.sazonalidade.confiavel
            ? undefined
            : { texto: "leitura fraca", tom: "neutro" },
          provenance: P_AGENTE,
        },
        {
          label: "Qualidade do dado",
          valor: `${output.qualidade_do_dado.n_meses} mês(es)${
            output.qualidade_do_dado.meses_faltantes.length > 0
              ? ` · faltam ${output.qualidade_do_dado.meses_faltantes.length}`
              : ""
          }`,
          nota: output.qualidade_do_dado.observacao,
          badge: output.qualidade_do_dado.soma_confere
            ? { texto: "soma confere", tom: "ok" }
            : { texto: "soma ≠", tom: "atencao" },
          provenance: P_AGENTE,
        },
        {
          label: "Credibilidade do documento",
          valor: output.credibilidade_documento.nivel,
          nota: output.credibilidade_documento.leitura,
          badge:
            output.credibilidade_documento.nivel === "alto"
              ? { texto: "alto", tom: "ok" }
              : output.credibilidade_documento.nivel === "baixo"
                ? { texto: "baixo", tom: "critico" }
                : { texto: "médio", tom: "atencao" },
          provenance: P_AGENTE,
        },
      ],
    },
  ]

  if (output.pontos_de_atencao.length > 0) {
    blocks.push({
      id: "rev-pontos",
      type: "apontamentos",
      itens: output.pontos_de_atencao.map((p) => ({
        severidade: sevFromPt(p.severidade),
        titulo: `${p.mes ? `${p.mes} · ` : ""}${p.tipo} (${p.esperado_ou_anomalo})`,
        descricao: p.observacao,
        provenance: P_AGENTE,
      })),
    })
  }

  if (output.credibilidade_documento.ressalvas.length > 0) {
    blocks.push({
      id: "rev-ressalvas",
      type: "apontamentos",
      titulo: "Ressalvas do documento",
      itens: output.credibilidade_documento.ressalvas.map((r) => ({
        severidade: "atencao" as const,
        titulo: r,
        provenance: P_AGENTE,
      })),
    })
  }

  blocks.push({
    id: "rev-leitura-credito",
    type: "texto",
    titulo: "Leitura para crédito",
    markdown: output.leitura_para_credito,
  })

  return {
    id: "section-revenue",
    stationId: "faturamento",
    titulo: "Faturamento",
    blocks,
    generatesDossierSection: true,
  }
}

// ─── Cadastral (cadastral_analyst) ────────────────────────────────────────────

export function cadastralToSection(output: CadastralAnalysis): SectionDescriptor {
  const sitTom =
    output.situacao_cadastral === "ativa"
      ? ("ok" as const)
      : output.situacao_cadastral === "irregular"
        ? ("critico" as const)
        : ("neutro" as const)

  const blocks: Block[] = [
    {
      id: "cad-conclusao",
      type: "conclusao_agente",
      agente: "Cadastral",
      resumo: output.resumo_executivo,
      homologado: false,
    },
    {
      id: "cad-leituras",
      type: "ficha",
      campos: [
        {
          label: "Situação cadastral",
          valor: output.situacao_cadastral,
          badge: { texto: output.situacao_cadastral, tom: sitTom },
          provenance: P_FONTE,
        },
        {
          label: "Tempo de atividade",
          valor: output.tempo_atividade_leitura,
          provenance: P_AGENTE,
        },
        {
          label: "Aderência da atividade (CNAE)",
          valor: output.aderencia_atividade,
          provenance: P_AGENTE,
        },
        {
          label: "Capital vs porte",
          valor: output.porte_capital_leitura,
          provenance: P_AGENTE,
        },
      ],
    },
  ]

  if (output.pontos_de_atencao.length > 0) {
    blocks.push({
      id: "cad-pontos",
      type: "apontamentos",
      itens: output.pontos_de_atencao.map((p) => ({
        severidade: sevFromPt(p.severidade),
        titulo: p.tipo,
        descricao: p.observacao,
        provenance: P_AGENTE,
      })),
    })
  }

  blocks.push({
    id: "cad-leitura-credito",
    type: "texto",
    titulo: "Leitura para crédito",
    markdown: output.leitura_para_credito,
  })

  return {
    id: "section-cadastral",
    stationId: "cadastral",
    titulo: "Cadastral",
    blocks,
    generatesDossierSection: true,
  }
}

// ─── Contrato social (social_contract_analyst) ────────────────────────────────

export function socialContractToSection(output: SocialContractAnalysis): SectionDescriptor {
  const signing = Object.entries(output.signing_powers ?? {})

  const blocks: Block[] = [
    {
      id: "soc-conclusao",
      type: "conclusao_agente",
      agente: "Contrato social",
      resumo: output.summary,
      homologado: false,
    },
    {
      id: "soc-leituras",
      type: "ficha",
      campos: [
        {
          label: "Alterações recentes de QSA (24m)",
          valor: output.qsa_changes_recent ? "Sim — atenção" : "Não identificadas",
          nota: output.qsa_changes_detail ?? undefined,
          badge: output.qsa_changes_recent ? { texto: "atenção", tom: "atencao" } : undefined,
          provenance: P_AGENTE,
        },
        {
          label: "Objeto social x operação",
          valor: output.object_compatible_with_operation ? "Compatível" : "Incompatível",
          nota: output.object_compatibility_rationale,
          badge: output.object_compatible_with_operation
            ? { texto: "compatível", tom: "ok" }
            : { texto: "incompatível", tom: "critico" },
          provenance: P_AGENTE,
        },
      ],
    },
  ]

  if (signing.length > 0) {
    blocks.push({
      id: "soc-poderes",
      type: "ficha",
      titulo: "Poderes de assinatura",
      campos: signing.map(([nome, forma]) => ({
        label: nome,
        valor: String(forma),
        provenance: P_DOC,
      })),
    })
  }

  if (output.statutory_restrictions.length > 0) {
    blocks.push({
      id: "soc-restricoes",
      type: "texto",
      titulo: "Restrições estatutárias",
      markdown: output.statutory_restrictions.map((r) => `- ${r}`).join("\n"),
      // Cláusulas transcritas do contrato — voz do documento, não do agente.
      provenance: P_DOC,
    })
  }

  if (output.checklist_results.length > 0) {
    blocks.push({
      id: "soc-checklist",
      type: "apontamentos",
      titulo: "Checklist",
      itens: output.checklist_results.map((c) => ({
        severidade: sevFromChecklist(c.status),
        titulo: `${c.code} — ${c.description}`,
        descricao: c.rationale,
        provenance: P_AGENTE,
      })),
    })
  }

  return {
    id: "section-social",
    stationId: "contrato-social",
    titulo: "Contrato social",
    blocks,
    generatesDossierSection: true,
  }
}

// ─── Card cadastral coletado (produtor consulta/silver) → blocos ──────────────
// Migração do hand-built `CadastralCard` pro padrão de blocos: cada CATEGORIA do
// contrato (identidade/situação/atividade/capital/histórico) vira uma `ficha`.
// Dado da fonte oficial → assinatura `fonte`. Campos `novo` ganham badge.

function _fmtCardDate(s: string | null): string {
  if (!s) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s
}

function _fmtCardBRL(n: number | null): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—"
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

function _fmtCardValor(v: CadastralCampo["valor"]): string {
  const scalar = (x: string | number | boolean) =>
    typeof x === "boolean" ? (x ? "Sim" : "Não") : String(x)
  if (v === null || v === "") return "—"
  if (Array.isArray(v)) return v.map(scalar).join(", ") || "—"
  return scalar(v)
}

export function cadastralCardToSection(data: CadastralCardData): SectionDescriptor {
  const blocks: Block[] = []

  // Resumo da empresa (identidade + chaves validadas no silver).
  blocks.push({
    id: "cadcard-empresa",
    type: "ficha",
    titulo: "Empresa",
    campos: [
      { label: "Razão social", valor: data.razao_social ?? "—", provenance: P_FONTE },
      { label: "CNPJ", valor: data.cnpj, provenance: P_FONTE },
      {
        label: "Situação cadastral",
        valor: data.situacao_cadastral ?? "—",
        badge: data.situacao_cadastral
          ? {
              texto: data.situacao_cadastral,
              tom: data.situacao_cadastral.toLowerCase() === "ativa" ? "ok" : "neutro",
            }
          : undefined,
        provenance: P_FONTE,
      },
      { label: "Data de fundação", valor: _fmtCardDate(data.data_fundacao), provenance: P_FONTE },
      { label: "Capital social", valor: _fmtCardBRL(data.capital_social), provenance: P_FONTE },
      ...(data.enriquecido
        ? []
        : [
            {
              label: "Enriquecimento",
              valor: "não enriquecido",
              badge: { texto: "pendente", tom: "atencao" as const },
            },
          ]),
    ],
  })

  // Banner "campos novos não classificados no contrato" → apontamento info.
  if (data.campos_novos_count > 0) {
    blocks.push({
      id: "cadcard-novos",
      type: "apontamentos",
      itens: [
        {
          severidade: "info",
          titulo: `${data.campos_novos_count} campo(s) novo(s) ainda não classificado(s) no contrato.`,
        },
      ],
    })
  }

  // Campos do contrato agrupados por categoria → uma `ficha` por categoria.
  const grupos = new Map<string, CadastralCampo[]>()
  for (const c of data.campos ?? []) {
    const arr = grupos.get(c.categoria) ?? []
    arr.push(c)
    grupos.set(c.categoria, arr)
  }
  const ordenados = Array.from(grupos.entries())
    .map(([cat, campos]) => ({
      cat,
      campos: [...campos].sort((a, b) => a.ordem - b.ordem),
      minOrdem: Math.min(...campos.map((c) => c.ordem)),
    }))
    .sort((a, b) => a.minOrdem - b.minOrdem)

  for (const { cat, campos } of ordenados) {
    blocks.push({
      id: `cadcard-${cat}`,
      type: "ficha",
      titulo: cat,
      campos: campos.map((c) => ({
        label: c.label,
        valor: _fmtCardValor(c.valor),
        badge: c.novo ? { texto: "novo", tom: "atencao" as const } : undefined,
        provenance: P_FONTE,
      })),
    })
  }

  return {
    id: "section-cadastral-card",
    stationId: "cadastral",
    titulo: "Dados cadastrais coletados",
    blocks,
    generatesDossierSection: false,
  }
}

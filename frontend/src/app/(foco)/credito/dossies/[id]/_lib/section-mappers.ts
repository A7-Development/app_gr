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

import type {
  Apontamento,
  Block,
  SectionDescriptor,
} from "@/design-system/types/section"
import type {
  CadastralAnalysis,
  RevenueAnalysis,
  SocialContractAnalysis,
} from "@/lib/credito-client"

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
        },
        {
          label: "Sazonalidade",
          valor: output.sazonalidade.detectada ? "Detectada" : "Sem padrão claro",
          nota: output.sazonalidade.padrao ?? undefined,
          badge: output.sazonalidade.confiavel
            ? undefined
            : { texto: "leitura fraca", tom: "neutro" },
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
        },
        { label: "Tempo de atividade", valor: output.tempo_atividade_leitura },
        { label: "Aderência da atividade (CNAE)", valor: output.aderencia_atividade },
        { label: "Capital vs porte", valor: output.porte_capital_leitura },
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
        },
        {
          label: "Objeto social x operação",
          valor: output.object_compatible_with_operation ? "Compatível" : "Incompatível",
          nota: output.object_compatibility_rationale,
          badge: output.object_compatible_with_operation
            ? { texto: "compatível", tom: "ok" }
            : { texto: "incompatível", tom: "critico" },
        },
      ],
    },
  ]

  if (signing.length > 0) {
    blocks.push({
      id: "soc-poderes",
      type: "ficha",
      titulo: "Poderes de assinatura",
      campos: signing.map(([nome, forma]) => ({ label: nome, valor: String(forma) })),
    })
  }

  if (output.statutory_restrictions.length > 0) {
    blocks.push({
      id: "soc-restricoes",
      type: "texto",
      titulo: "Restrições estatutárias",
      markdown: output.statutory_restrictions.map((r) => `- ${r}`).join("\n"),
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

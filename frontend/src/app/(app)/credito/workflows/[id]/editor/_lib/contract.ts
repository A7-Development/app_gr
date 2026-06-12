// src/app/(app)/credito/workflows/[id]/editor/_lib/contract.ts
//
// Contrato visivel de cada etapa — "RECEBE → FAZ → PUBLICA" (F1 do programa
// de clareza do builder, 2026-06-12).
//
// O builder mostrava a MECANICA (nodes, configs) e escondia o CONTRATO: o que
// entra, o que acontece, o que sai. Este modulo deriva, por nodeType +
// config, as tres linhas em pt-BR que todo node exibe no hover do canvas e
// no topo do inspector. O "PUBLICA" (outputs tipados) NAO vive aqui — vem do
// `produced_by_node` da validacao semantica (fonte: backend produces()).
//
// Funcao pura — testavel, sem React.

import type { AgentMeta } from "@/lib/credito-client"

import { AGENT_FRIENDLY_LABEL } from "./glossary"
import { OFFICIAL_DOCUMENT_PALETTE } from "./etapas"

export type InternalStep = {
  label: string
  /** O que esta perna entrega pra proxima. */
  produz: string
}

export type NodeContract = {
  /** O que a etapa CONSOME e de onde vem (pt-BR, 1 linha). */
  recebe: string
  /** O que a etapa FAZ (pt-BR, 1 frase). */
  faz: string
  /** Cadeia interna de etapas compostas (receitas) — abre a caixa-preta. */
  internalSteps?: InternalStep[]
}

function fmtDocTypes(raw: unknown): string {
  if (!Array.isArray(raw) || raw.length === 0) return "documentos"
  return raw
    .map((t) => String(t).toLowerCase().replace(/_/g, " "))
    .join(", ")
}

/** Resume um template `{{node.X.output.Y}}` como "Y (da etapa X)". */
export function describeRef(template: unknown): string | null {
  const m = /\{\{\s*node\.([^.}]+)\.output\.([^}\s]+)\s*\}\}/.exec(
    String(template ?? ""),
  )
  if (!m) return null
  return `${m[2]} (da etapa ${m[1]})`
}

export function nodeContract(
  nodeType: string,
  config: Record<string, unknown>,
  agentCatalog: AgentMeta[] = [],
): NodeContract {
  switch (nodeType) {
    case "trigger":
      return {
        recebe: "Nada — é o ponto zero",
        faz: "Abre a análise e publica a identidade do dossiê. O CNPJ da empresa NÃO nasce aqui: entra no formulário de Identificação, confirmado pelo analista.",
      }

    case "human_input": {
      const fields = Array.isArray(config.fields) ? config.fields.length : 0
      return {
        recebe: "Nada do fluxo — espera o analista",
        faz: fields
          ? `Pausa até o analista preencher o formulário (${fields} campo${fields === 1 ? "" : "s"}).`
          : "Pausa até o analista preencher o formulário configurado.",
      }
    }

    case "human_review":
      return {
        recebe: "As análises produzidas pelas etapas anteriores",
        faz: "Pausa para o analista revisar e aprovar antes de seguir.",
      }

    case "document_request":
      return {
        recebe: "Nada do fluxo — espera o analista (ou a busca em fonte oficial)",
        faz: `Pausa até existirem no dossiê: ${fmtDocTypes(config.required)}.`,
      }

    case "document_extractor":
      return {
        recebe: "Os documentos enviados na etapa de coleta (PDF/imagem)",
        faz: "IA lê cada documento e extrai os dados estruturados (com citações) para a conferência do analista.",
      }

    case "bureau_query": {
      const ref = describeRef(config.entity_ref)
      return {
        recebe: ref
          ? `CNPJ/CPF a consultar: ${ref}`
          : "CNPJ/CPF a consultar (ligue no campo 'a consultar' do inspector)",
        faz: `Consulta o bureau (${String(config.adapter ?? "—")}) e grava o resultado no dossiê com proveniência.`,
      }
    }

    case "cadastral_enrichment":
      return {
        recebe:
          "CNPJ da empresa-alvo do dossiê — preenchido pelo formulário de Identificação (posicione esta etapa DEPOIS dele). Origem fixa: opera sempre sobre quem está sendo analisado.",
        faz: `Consulta o dataset ${String(config.public_code ?? "CAD-PJ")} e grava situação, CNAEs, capital e fundação na empresa-alvo — alimenta os checks de elegibilidade.`,
      }

    case "official_document_fetch": {
      const recipe = OFFICIAL_DOCUMENT_PALETTE.find(
        (r) => r.key === String(config.document ?? ""),
      )
      return {
        recebe:
          "CNPJ da empresa-alvo do dossiê — preenchido pelo formulário de Identificação (posicione esta etapa DEPOIS dele). Origem fixa: opera sempre sobre quem está sendo analisado.",
        faz: recipe
          ? `Busca "${recipe.label}" direto na fonte oficial — 3 etapas internas, sem clique do analista.`
          : "Busca um documento oficial direto na fonte pública.",
        internalSteps: [
          { label: "Buscar na fonte oficial", produz: "ficha + documento mais recente localizado" },
          { label: "Anexar ao dossiê", produz: "documento (PDF) no dossiê" },
          { label: "Ler com IA", produz: "campos extraídos p/ conferência do analista" },
        ],
      }
    }

    case "specialist_agent": {
      const agentName = String(config.agent ?? "")
      const meta = agentCatalog.find((a) => a.name === agentName)
      const label = AGENT_FRIENDLY_LABEL[agentName] ?? agentName
      const inputs = meta?.inputs ?? []
      return {
        recebe: inputs.length
          ? `Slots ligados a etapas anteriores: ${inputs.map((i) => i.name).join(", ")}`
          : "Contexto completo do fluxo (etapas anteriores)",
        faz: `Agente IA "${label}" julga os fatos e produz a análise da sua seção.`,
      }
    }

    case "deterministic_check":
      return {
        recebe: "Os fatos já materializados no dossiê (silver/extrações homologadas)",
        faz: `Roda o check determinístico "${String(config.check ?? "—")}" (Python puro, sem IA) — aprova/reprova e materializa red flags com proveniência.`,
      }

    case "conditional_branch":
      return {
        recebe: "Variáveis publicadas pelas etapas anteriores",
        faz: "Avalia a condição e publica sim/não — os conectores de saída roteiam o fluxo.",
      }

    case "consolidator":
      return {
        recebe: "Variáveis de várias etapas anteriores",
        faz: "Combina os valores em um conjunto único de saída — regra fixa, sem IA.",
      }

    case "http_request":
      return {
        recebe: "Variáveis do fluxo interpoladas em URL/corpo",
        faz: `Chama o serviço externo (${String(config.method ?? "GET")} ${String(config.url ?? "")}).`.trim(),
      }

    case "notification":
      return {
        recebe: "Variáveis do fluxo interpoladas na mensagem",
        faz: "Registra/envia a notificação configurada.",
      }

    case "output_generator":
      return {
        recebe: "Tudo que o fluxo produziu (análises, parecer, flags)",
        faz: "Gera o artefato final do dossiê (PDF/JSON).",
      }

    default:
      return {
        recebe: "Variáveis das etapas anteriores",
        faz: "Etapa do fluxo.",
      }
  }
}

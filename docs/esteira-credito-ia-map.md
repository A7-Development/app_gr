# Esteira de Crédito — Mapa IA / Check / Agente (RASCUNHO)

> **Status:** direção geral aprovada por Ricardo (2026-06-01). Etapas serão
> refinadas conforme a construção avança — tratar como referência viva, não
> especificação fechada.

## Princípio-chave (reconcilia apelo de IA + auditabilidade)

> **Os agentes não calculam os números. Eles chamam tools/checks
> determinísticos, recebem o fato verificável, e raciocinam em cima.**
> O número é auditável (CVM-ready); a investigação, a narrativa e a decisão
> são agênticas (o que encanta cliente e investidor).

O determinístico **não é o produto** — é o trilho de segurança embaixo dos
agentes. O produto são os agentes.

## Legenda

- 🟦 **Check** — determinístico, Python puro, sem LLM
- 🟩 **Tool de agente** — função que o agente chama no loop de raciocínio
- 🟪 **Agente** — raciocínio LLM
- ⬜ **Humano** — input / checkpoint
- Status: ✅ pronto (em prod) · 🟡 parcial · ❌ a construir

## Mapa

| Etapa / Capacidade | Executor | Papel da IA / agente | Status |
|---|---|---|---|
| Grafo societário (empresas+sócios+%) | ⬜ Humano + persistência | — (entrada) | ✅ |
| Perímetro (quais CNPJs) | ⬜ Humano | — | ✅ |
| Gate elegibilidade (idade, CNAE proibido, capital, RJ) | 🟦 Check (política versionada) | trava barata antes de pagar | idade ✅ · resto ❌ |
| Coletar Kit Banco (anexar docs) | ⬜ Humano (upload) | — | 🟡 |
| Ler documentos (DRE/Balanço/Faturamento/Contrato) | 🟪 Agente Vision | lê o PDF e estrutura; número re-checado por 🟦 | 🟡 |
| Consultar Serasa/Receita/Processos/Protestos/SCR | 🟩 Tool (chama adapter) | agente decide quando e interpreta | Serasa adapter ✅ · tools ❌ · resto ❌ |
| Capacidade teórica de recebíveis | 🟦 Check → 🟩 tool | agente raciocina: "ofertado 2,5× acima → duplicata fria" | ❌ |
| Concentração por sacado (curva ABC) | 🟦 Check → 🟩 tool | agente alerta concentração | ❌ |
| Proporcionalidade de capital social | 🟦 Check → 🟩 tool | agente sinaliza subcapitalização/fachada | ❌ |
| Soma de participações ≠ 100% | 🟦 Check | sócio oculto / erro cadastral | ✅ |
| Bate de mercado (credores declarados ∪ Serasa) | 🟦 Check → 🟩 tool | agente monta lista e aponta a omissão | ❌ |
| Família 1 — declarado × oficial (endivid.×SCR, fatur.×NFe/capacidade) | 🟪 Agente detetive + 🟩 tools | o coração: raciocina sobre o desvio, flag narrada | ❌ |
| Família 2 — cross-fonte (endereço/datas/QSA/capital) | 🟪 Agente cross-reference | cruza N fontes, aponta o campo exato divergente | 🟡 (depende de Receita) |
| Família 3 — materialidade (satélite/fachada/site/WHOIS) | 🟪 Agente multimodal | descreve se a empresa é real; humano conclui | ❌ |
| Parecer (recomendação + justificativa) | 🟪 Agente (opinion_writer) | redige o parecer das flags; humano homologa | 🟡 (rascunho hoje) |
| Conferência / homologação | ⬜ Humano (checkpoint) | edita o que a IA propôs | ✅ |
| Parecer jurídico / bate de mercado | ⬜ Humano assíncrono (nó durável) | agente pré-prepara a peça | ❌ |
| Decisão + outcome (decision ledger) | 🟦 persistência | mede acerto das recomendações no tempo | 🟡 |
| Investigador conversacional ("pergunte ao dossiê") | 🟪 Agente + tools | o wow: investiga sob demanda, ao vivo | ❌ (padrão existe no cota-sub) |
| Teatro agêntico (ver agentes trabalhando) | infra `AgentLiveStatus` | mostra cada tool call em tempo real | ✅ infra |

## As 5 superfícies agênticas (a mágica)

1. Leitor de documentos (Vision)
2. Detetive de cruzamento (família 1 — coração da fraude)
3. Materialidade multimodal
4. Sintetizador do parecer
5. Investigador conversacional (o demo que fecha investidor)

## Sequência de construção (agentic-first)

1. Extração agêntica de documentos — o agente lê (destrava dado pros demais)
2. Tools determinísticas expostas a agentes — capacidade, concentração, capital, bate-mercado
3. Agente detetive de cruzamento — raciocina sobre docs + Serasa → flags narradas
4. Investigador conversacional — o wow
5. Materialidade multimodal + integrações externas (Receita primeiro)

## Já entregue (Fatia 1, em prod)

Política `credit_policy` · node `deterministic_check` + checks
(`company_founding_age`, `ownership_sum`) na paleta do builder · persistência
do grafo societário · proveniência estruturada da flag · playbook
`credit.onboarding_minimo` · cockpit com flags visíveis + checkpoint c/ parecer
+ reprocessar.

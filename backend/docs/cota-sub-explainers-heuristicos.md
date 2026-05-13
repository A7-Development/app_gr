# Explainers heuristicos das variacoes da Cota Sub

> Plano de implementacao dos heuristicos que respondem **por que** o PL da Cota Sub mexeu de um dia D-1 para D0 na pagina `/controladoria/cota-sub`.
>
> Discutido e batido com Ricardo em 2026-05-12. Complementar a [`atribuicao-cota-sub-cosif.md`](./atribuicao-cota-sub-cosif.md) (calculo do PL Sub) — esta a **decomposicao da variacao** desse PL.
>
> Shell ja entregue no front: [`AnaliseVariacaoCard.tsx`](../../frontend/src/app/(app)/controladoria/cota-sub/_components/AnaliseVariacaoCard.tsx). Listando as 4 categorias canonicas com status "em construcao".

## Por que heuristica antes de Specialist Agent

Controller olha o waterfall, ve a variacao, e quer saber **por que** o PL Sub mexeu. Heuristica deterministica resolve ~80% dos casos sem custo/risco/latencia de LLM, com auditabilidade total (linhas exatas do silver citadas como evidencia). Specialist Agent (CLAUDE.md §19) entra como fallback quando heuristica devolver "indeterminado".

Tasks #37/#38 do board ja preveem a peca de agente, dependentes da defesa C2 (#26-#30). Esse documento cobre **apenas** a camada heuristica — o agente reusa o mesmo endpoint como tool depois.

## Arquitetura

**Endpoint:** `POST /controladoria/cota-sub/balancete-diario/explicar`

Lazy / on-demand — **NAO** embutido no payload do balancete. Controller dispara explicacao quando abre o card; nao infla o request principal. Permite que cada explainer faca queries adicionais (Singulare, estoque PDD) sem custo na rota canonica.

Request:

```json
{
  "ua_id": "...",
  "data_d0": "2026-05-12",
  "data_d1": "2026-05-09",
  "threshold_pct": 0.10,
  "threshold_brl": 1000.00
}
```

Response:

```json
{
  "delta_pl_sub": -45230.10,
  "explanations": [
    {
      "categoria": "pdd",
      "subcategoria": "3.2",
      "narrative": "PDD aumentou em 12 papeis explicando -R$ 28.450,33 (63% da variacao). Maior impacto: ACME LTDA / DEVEDOR S.A. (titulo 4521).",
      "delta_brl": -28450.33,
      "evidencias_total": 12,
      "evidencias_mostradas": 12,
      "evidencias": [
        {
          "tipo": "pdd_papel",
          "cedente_doc": "12345678000190",
          "cedente_nome": "ACME LTDA",
          "sacado_doc": "98765432000110",
          "sacado_nome": "DEVEDOR S.A.",
          "seu_numero": "4521",
          "numero_documento": "NF-4521",
          "tipo_recebivel": "Duplicata",
          "data_vencimento_ajustada": "2026-04-30",
          "valor_pdd_d1": 1500.00,
          "valor_pdd_d0": 12000.00,
          "delta_valor_pdd": 10500.00,
          "faixa_pdd_d1": "C",
          "faixa_pdd_d0": "H",
          "delta_pl_sub": -10500.00
        }
      ]
    }
  ],
  "indeterminado_brl": -6809.99
}
```

**Granularidade da evidencia (decisao 2026-05-13):** evidencias **sempre granulares** — para PDD, 1 evidencia = 1 papel (cedente_nome + sacado_nome + numero_documento + faixa antes/depois). Narrativa agrega ("12 papeis") mas o drill-down embaixo do card lista cada um. Cap em `top_n` evidencias mostradas (default 20), ordenadas por `|delta|` DESC; resto vira "+N outros" + total agregado.

**Frontend:**

Cada explainer e funcao pura `(balancete_d0, balancete_d1) -> Explanation | null` em `_lib/explainers/<categoria>.ts`. Card renderiza:
- Narrative + Δ em R$ e % do delta total
- Tabela de evidencias com tooltip de auditoria (link pra linha do silver)
- Cor neutra se delta positivo, cor de alerta se negativo (mesma logica do waterfall)

Categorias sao chamadas em ordem fixa; cada uma reporta seu Δ; o que sobrar fica no balde "indeterminado" no rodape do card.

## 4 Categorias canonicas

> Atualizado 2026-05-13 apos investigacao de schema (B2) e amostragem de CPR / MEC (B3) em REALINVEST.

| # | Categoria | Trigger | Fonte | Status |
|---|---|---|---|---|
| **1.1** | Aporte Cota Sub | `wh_cpr_movimento.descricao = 'Aporte'` (valor negativo = saida de CPR = aporte recebido) | CPR silver (REALINVEST 08, 11, 12/05/2026 confirmado: -124.500,00 cada) | pronto pra codar |
| **1.2** | Movimento de cotas Sr/Mez (aporte ou resgate em outra classe) | `wh_cpr_movimento.descricao = 'Ajuste para Compensação de Cotas'` **+** cruzar com `wh_mec_evolucao_cotas` no mesmo dia: classe nao-Sub com `Δquantidade != 0` | CPR + MEC silver. Caso ancora REALINVEST 26/03/2026: Ajuste -R$ 1.576.001,48 no CPR; MEC mostra Mez subindo 1120.99 → 1550.94 cotas com entradas R$ 501.907,24 = aporte Mez | pronto pra codar |
| **2.1** | Liquidacao papel (agregada) | `wh_cpr_movimento.descricao = 'LIQUIDADOS TOTAL - PROV'` (valor positivo = entrada de caixa) | CPR silver — aparece 48 dias em REALINVEST. Sem granularidade por papel ainda. | pronto agregado; falta granular |
| **2.1b** | Liquidacao papel (granular, opcional) | Σ valor_bruto(papeis removidos do `wh_estoque_recebivel`) | comparar D-1 vs D0 no estoque | quick-win sem adapter Singulare |
| **2.2** | Aquisicao papel | papeis novos no `wh_estoque_recebivel` D0 que nao estavam em D-1 | estoque silver | quick-win sem adapter Singulare |
| **3.2** | PDD (constituicao/reversao) | Δ `valor_pdd` no estoque por papel | `wh_estoque_recebivel.valor_pdd` + `faixa_pdd` (A-H Bacen 2682) — historico diario confirmado | pronto pra codar |
| **3.3** | Diferimento / amortizacao | `wh_cpr_movimento.descricao` LIKE 'Diferimento de despesa%' | CPR silver — 34-41 ocorrencias por padrao | pronto, regex refinavel |
| **4.1** | Marcacao a mercado | Papel com `Δqtde = 0` E `Δvalor != 0` em `wh_posicao_renda_fixa` D-1 vs D0 | silver pronto | pronto (mais facil) |
| ~~3.1~~ | ~~Apropriacao diaria~~ | — | — | skip MVP |
| ~~4.2~~ | ~~Transferencia interna~~ | — | — | skip (nao ocorre) |

## Ordem de implementacao (menor → maior atrito)

1. **MTM (4.1)** — so cruza `rows_por_cosif` ja exposto no balancete. ~50 linhas. Quick-win + serve de proof-of-pattern para o resto.
2. **Aporte Sub (1.1)** — MEC ja populado. Comparacao 1:1 D-1 vs D0.
3. **Diferimento (3.3)** — regex em CPR. Confiavel mas testar variantes da descricao.
4. **PDD (3.2)** — depende de confirmar silver de estoque. Pode virar quick-win se silver ja tem o campo.
5. **Resgate (1.2)** — depende de regex confirmada do CPR (caso 22/02).
6. **Liquidacao (2.1) / Aquisicao (2.2)** — bloqueado por adapter Singulare novo. Maior trabalho — fora do MVP.

## Bloqueios em aberto

| # | Bloqueio | Como destravar | Owner |
|---|---|---|---|
| ~~B1~~ | ~~Adapter Singulare nao existe~~ | **Defer**: liquidacao/aquisicao podem ser feitas via diff de `wh_estoque_recebivel` D-1 vs D0 (granular) e via CPR `LIQUIDADOS TOTAL - PROV` (agregado). Adapter Singulare fica para Fase 2 quando precisarmos do detalhe (CETIP, codigo IF). | Backend (deferido) |
| ~~B2~~ | ~~Silver de PDD~~ | **Resolvido 2026-05-13**: `wh_estoque_recebivel` tem `valor_pdd` (NUMERIC) + `faixa_pdd` (A-H Bacen 2682), granularidade diaria por papel, REALINVEST com 19 dias de historico (jan/2025 + abril/maio/2026 quase diario). | ✓ |
| B3 | **Vocabulario do CPR mapeado** | **Resolvido 2026-05-13**: dicionario abaixo (Aporte, Ajuste para Compensação de Cotas, LIQUIDADOS TOTAL - PROV, Diferimento). **Falta confirmar com voce** se "Ajuste para Compensação de Cotas" e equivalente a resgate (caso 26/03 com -R$ 1.576.001,48). | Confirmacao (Ricardo) |
| ~~B4~~ | **Threshold de gatilho** | **Resolvido 2026-05-13**: Opcao A em **nivel** (granular por evidencia/papel — Ricardo: "preciso saber nome do cedente e titulos"). Parametrizavel via query param (default `|Δ R$| > R$ 1.000`). Para evitar poluicao quando muitos papeis mudam no mesmo dia, evidencias ordenadas por `\|Δ\|` DESC + cap em `top_n` (default 20) + linha "+N outros". | ✓ |

## Dicionario do CPR (REALINVEST, ja mapeado em 2026-05-13)

| `descricao` no CPR | Sinal | Sinal de variacao de PL Sub | Notas |
|---|---|---|---|
| `Aporte` | Cotista aportou caixa no fundo | `+` Δ Sub (cotas Sub aumentam) | Valor sempre negativo no CPR (saida do CPR = entrada de caixa). 4 ocorrencias REALINVEST. |
| `Ajuste para Compensação de Cotas` | **Movimento de cotas Sr/Mez** (aporte ou resgate em classe nao-Sub) — NAO e resgate da Sub | `-` Δ Sub quando Sr/Mez **aporta** (mais passivo prioritario); `+` Δ Sub quando Sr/Mez **resgata** | 5 ocorrencias REALINVEST. Range -R$ 1.576.001 / +R$ 1.597. **Validado 2026-05-13**: caso 26/03 (Ajuste -1,576MM no CPR) bateu com Mez subindo 1120.99→1550.94 cotas e entrando R$ 501.907,24 no MEC. **Sempre cruzar com MEC pra identificar qual classe se mexeu**. |
| `LIQUIDADOS TOTAL - PROV` | Liquidacao de titulos do dia (agregado) | `+` caixa, mas neutro pro PL Sub (papel saiu pelo valor_presente, caixa entrou pelo mesmo valor) | 48 ocorrencias REALINVEST. **So muda PL Sub indiretamente** via PDD revertida quando papel liquida. |
| `Diferimento de despesa de %` | Apropriacao mensal de despesa diferida (CVM, ANBIMA, Rating, etc) | `-` pequeno e constante | Padrao consistente, valores R$ 8-1.300 por linha. |
| `Despesa de %` / `Taxa % a Pagar em %` | Provisao mensal de taxas (admin, custodia, gestao) | `-` Sub absorve | Inclui auditoria, consultoria, cobranca, custodia, SELIC, banco liquidante. |
| `Taxa % Apropriada` | Apropriacao diaria das taxas mensais | `-` Sub absorve | "Taxa de Custodia Apropriada", "Taxa de Gestao Apropriada", "Taxa de Administracao Apropriada" — 47 dias cada. |
| `IOF a Recolher em %` | IOF mensal sobre resgates/eventos | `-` Sub absorve | Aparece pontualmente. |
| `IR a Recolher em %` | IRRF mensal | `-` Sub absorve | Aparece pontualmente. |

**Achado importante**: `wh_mec_evolucao_cotas` tem campos `aporte` e `retirada` dedicados, **mas estao TODOS zerados** em REALINVEST (verificado em 2026-05-13). Significa que o admin (QiTech) **nao popula esses campos** — o sinal real de aporte/resgate esta no CPR via `descricao`. **Nao usar `wh_mec_evolucao_cotas.aporte` / `.retirada` como fonte.**

## Vocabulario alternativo a investigar pra outros admins

Quando expandirmos para fundo administrado por **BRL Trust** ou **Singulare**, o dicionario do CPR pode mudar. Plano:

1. Mapear o vocabulario por administrador (`carteira_cliente_doc` → admin).
2. Manter dicionario versionado por admin em `_lib/explainers/cpr_dictionary.ts`.
3. Cada explainer recebe o admin no input e busca o termo correto.

## Decisoes arquiteturais ja batidas

- **Endpoint separado** (nao embutido no balancete) — lazy, on-demand.
- **Heuristica primeiro, agente Specialist como fallback** — quando heuristica devolver "indeterminado" significativo (> threshold), LLM com tools (`query_silver`, `query_mec`, `query_cpr`) entra. Tasks #37/#38 ja preveem.
- **UI** — cada categoria que matcha vira card com narrative + evidencias citadas (linhas exatas do silver com link/tooltip de auditoria), nao apenas texto solto.
- **Funcoes puras no front** — explainers ficam em `_lib/explainers/<categoria>.ts`, recebem `(balancete_d0, balancete_d1)` e devolvem `Explanation | null`. Backend faz a parte que precisa de fonte externa (PDD, Singulare); front faz a parte que ja sai no balancete (MTM, Aporte, Diferimento).

## Relacionado

- [`atribuicao-cota-sub-cosif.md`](./atribuicao-cota-sub-cosif.md) — calculo do PL Sub via balancete COSIF
- CLAUDE.md §19 — Specialist Agent runtime (peca futura — fallback)
- CLAUDE.md §13 — adapter pattern (necessario pra Singulare)
- CLAUDE.md §14 — DNA de auditabilidade (proveniencia + `decision_log`)

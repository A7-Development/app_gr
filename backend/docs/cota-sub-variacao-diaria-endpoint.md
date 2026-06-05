# Endpoint pendente — `GET /controladoria/cota-sub/variacao-diaria`

> **Status:** dependência de backend sinalizada em **2026-06-05** pelo handoff de design
> "Cota Sub · master-detail" (Strata). O **frontend já está implementado** (branch `cota-sub`)
> e consome este contrato; até o endpoint existir, o client cai num **mock dev-only**
> (`_mockVariacaoDiaria` em `frontend/src/lib/api-client.ts`). Em produção o card mostra
> estado vazio/erro até o endpoint publicar.

## Por que o endpoint novo (e não reusar `/variacao/resumo`)

A aba "Resumo do dia" virou um **master-detail**: um gráfico de colunas (variação diária da
cota dentro da competência) é o *master*; clicar num dia re-chaveia o waterfall + detalhamento
(que já existem via `/variacao/resumo`, **um dia por request**).

Montar o gráfico do mês reusando só o que existe exigiria **~21 chamadas** a `/variacao/resumo`
(uma por dia útil) a cada abertura da página. Cada chamada roda `compute_variacao_resumo`, que
internamente dispara **7+ sub-cálculos pesados** por dia (`balanco_estrutural`, `drill_dc`,
`drill_pdd`, `aplicacoes`, `nota_comercial`, `contas_a_pagar`, `cotas`). Total: ~150 sub-cálculos
só para desenhar 21 barras. Inviável.

## Contrato

```
GET /controladoria/cota-sub/variacao-diaria?fundo_id={uuid}&competencia=YYYY-MM
```

| Query param   | Tipo            | Obrigatório | Descrição                                   |
|---------------|-----------------|-------------|---------------------------------------------|
| `fundo_id`    | UUID            | sim         | UA (FIDC). Mesma semântica dos outros endpoints cota-sub. |
| `competencia` | string `YYYY-MM`| sim         | Mês a materializar (todos os dias úteis).   |

**Resposta:** `VariacaoDiariaSeriePonto[]` — uma entrada por **dia do mês** (não só dias úteis;
o eixo X do gráfico reserva o slot de fins de semana/feriados/futuro).

```jsonc
[
  { "data": "2026-06-01", "variacao_cota": null,     "variacao_pct": null,  "eh_dia_util": false, "eh_futuro": false },
  { "data": "2026-06-02", "variacao_cota": 12400.0,  "variacao_pct": 0.26,  "eh_dia_util": true,  "eh_futuro": false },
  { "data": "2026-06-10", "variacao_cota": 35900.75, "variacao_pct": 0.74,  "eh_dia_util": true,  "eh_futuro": false },
  { "data": "2026-06-27", "variacao_cota": null,     "variacao_pct": null,  "eh_dia_util": true,  "eh_futuro": true  }
]
```

| Campo           | Tipo            | Semântica                                                              |
|-----------------|-----------------|------------------------------------------------------------------------|
| `data`          | `YYYY-MM-DD`    | Dia.                                                                    |
| `variacao_cota` | `number \| null`| **Δ R$ do PL Sub no dia** = `cota_delta` (PL Sub calc D0 − D1, método gestor). `null` = sem apuração (fim de semana, feriado, futuro, ou dia sem snapshot QiTech). |
| `variacao_pct`  | `number \| null`| `variacao_cota / pl_sub_calc_d1 * 100`. `null` quando não há D-1.        |
| `eh_dia_util`   | `boolean`       | Liga o dim do label do eixo X.                                          |
| `eh_futuro`     | `boolean`       | Dia > hoje (sem barra).                                                 |

> `variacao_cota` mapeia **1:1** ao campo `cota_delta` que `compute_variacao_resumo` já calcula.

## Implementação sugerida (barata)

O gráfico só precisa de `cota_delta` + `%` por dia — **não** do waterfall completo. Isso é a
**diferença consecutiva do PL Sub calculado** entre dias úteis disponíveis na competência:

1. Carregar o **PL Sub (calculado, método gestor)** por data disponível na competência — **uma
   query** sobre as posições (mesma base que `compute_balanco_estrutural` usa para `pl_sub_d0`),
   não 21 waterfalls.
2. Para cada dia útil com snapshot: `variacao_cota[d] = pl_sub[d] − pl_sub[d-1]` (D-1 = dia útil
   anterior com snapshot); `variacao_pct = variacao_cota / pl_sub[d-1] * 100`.
3. Dias sem snapshot / fim de semana / feriado / futuro → `variacao_cota = null` com os flags
   `eh_dia_util` / `eh_futuro` corretos.

## Checklist backend (CLAUDE.md §18)

- [ ] `require_module(Module.CONTROLADORIA, Permission.READ)` no endpoint.
- [ ] Query escopada por `tenant_id` (via principal) + `ua_id`.
- [ ] Lê **apenas** silver (`wh_*`), nunca raw.
- [ ] **§14.6 — zero ocultação:** retornar **todos** os dias do mês (sem top-N / corte por valor).
      O gráfico é seletor, não "total + detalhe", mas a série não pode esconder dias úteis apurados.
- [ ] Teste de isolamento de tenant.

## Consumo no frontend (já pronto)

- `frontend/src/lib/api-client.ts` — tipo `VariacaoDiariaSeriePonto` + método `controladoria.cotaSubVariacaoDiaria(fundoId, competencia)` (+ mock dev-only `_mockVariacaoDiaria`, **remover** quando o endpoint subir).
- `frontend/src/lib/hooks/controladoria.ts` — `useVariacaoDiariaSerie(fundoId, competencia)`.
- `frontend/src/app/(app)/controladoria/cota-sub/_components/VariacaoDiariaCard.tsx` — o card master.
- `page.tsx` — `?dia=YYYY-MM-DD` URL-synced (§11.6); competência derivada do dia selecionado.

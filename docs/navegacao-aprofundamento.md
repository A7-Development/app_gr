# Navegacao e Aprofundamento de Dados (Strata)

> Fonte de verdade para escolher **como o usuario desce no detalhe** dos dados: inline / drawer / rota / modal. Densidade numa tela ja e problema resolvido; o que decide a qualidade do produto e a navegacao e o aprofundamento. Use este documento ao criar qualquer tela nova e nas skills de criacao de pagina (`create-list-page`, `create-detail-page`, `create-dashboard-page`).
>
> Le em ~10 min. Pareado com CLAUDE.md §7 (patterns canonicos) e §11.6 (hierarquia de navegacao).

---

## 1. Principio unico

> **O detalhe nunca vem antes do contexto.** O usuario sempre sabe "onde esta" antes de mergulhar.
> (Mantra de Shneiderman: overview first → zoom & filter → details-on-demand.)

Regra de bolso que resolve a maioria dos casos: **escolha sempre o mecanismo de menor custo de contexto que ainda comporta o conteudo.**

- Quanto mais o salto e **exploracao** → mecanismos que preservam contexto (inline, drawer).
- Quanto mais o objeto **vira um novo lugar de trabalho** → tela nova (rota).
- Quanto mais e uma **decisao atomica e irreversivel** → modal (e so ai).

---

## 2. Procedimento de decisao (rode para qualquer detalhe novo)

1. **E o mesmo objeto e o detalhe e pequeno?** (parcelas de uma operacao, eventos de um titulo)
   → **Inline.** Custo de contexto: zero.
2. **Inspecionar UM item sem perder a lista/o painel atras?**
   → **Drawer** (side sheet). Custo: baixo.
3. **O objeto tem profundidade propria e vira foco de trabalho** (sub-navegacao, abas, varias secoes)?
   → **Rota dedicada** com breadcrumb. Custo: medio.
4. **Decisao atomica que confirma/cancela algo irreversivel?**
   → **Modal** (AlertDialog). Bloquear a tela aqui e intencional.

Se nada encaixar, volte ao **principio (§1)** e escolha o menor custo de contexto.

---

## 3. Mapa: hierarquia do Strata → mecanismo

| Objeto | Mecanismo | Custo de contexto |
|---|---|---|
| **Cedente / Sacado / Dossie** | **Rota cheia** (`/.../[id]`) — objeto com abas/sub-navegacao propria, vira local de trabalho | medio |
| **Cessao / Titulo / Operacao / Evento** | **Drawer** (`?selected=<id>`) — inspecao de 1 item, lista segue atras | baixo |
| **Parcela / Evento / Linha do agente** ("por que esse score") | **Inline** — expansivel dentro da lista ou do drawer | zero |
| **Aprovacao de credito / acao destrutiva** | **Modal** (AlertDialog) — bloqueia de proposito | alto |

**Fronteira pratica:** objeto com sub-navegacao propria vira rota; inspecao de um item e drawer; detalhe pequeno do mesmo objeto e inline; decisao irreversivel e modal.

A explicacao do agente de risco ("por que esse score?") e o caso canonico de **details-on-demand**: **inline** dentro do drawer da operacao — disponivel sempre, intrusivo nunca.

---

## 4. Mecanismo do drawer

Drawer = `?selected=<id>` na URL via **nuqs** (`useQueryState`) + `<DrillDownSheet>` (Radix Dialog como side-sheet). Estado na URL → deep-linkable e sobrevive a refresh: um colega cola o link e cai na mesma operacao aberta.

**History mode (regra dura):**

- **Abrir/fechar drawer = `push`.** O botao voltar (e swipe-back no mobile) fecha o drawer.

  ```ts
  const [selected, setSelected] = useQueryState("selected", { history: "push" })
  // abrir a partir da tabela:
  onRowClick={(row) => setSelected(row.id)}  // herda history: "push"
  ```

- **Navegar prev/next dentro do drawer = `replace`.** Nao acumula uma entrada de historico por item espiado.

  ```ts
  onNext={() => setSelected(filtered[i + 1].id, { history: "replace" })}
  onPrevious={() => setSelected(filtered[i - 1].id, { history: "replace" })}
  ```

**Regra geral:** abrir/fechar uma camada = `push`; navegar lateralmente dentro da mesma camada = `replace`.

Pattern de referencia: [`ListagemComDrilldown`](../frontend/src/design-system/patterns/ListagemComDrilldown.tsx).

---

## 5. Estado e URL

| Vai pra URL (deep-linkable) | Fica local (efemero) |
|---|---|
| `?selected=<id>` (drawer aberto) | Filtros da listagem |
| Tab da pagina (L3) | Linha expandida (inline) |
| | Hover-highlight |
| | Aba *dentro* do drawer |
| | Estado do modal |

- **Tela nova = rota real.** Nunca simule navegacao trocando estado local; o back button **tem** que funcionar.
- **Modal NUNCA vai pra URL.** Decisao transitoria nao e deep-linkavel nem reaberta por refresh.
- **Preserve scroll e selecao ao fechar um drawer** — o usuario volta exatamente onde estava.

---

## 6. Configuracao / parametrizacao (escrita)

As secoes acima tratam de **leitura** (explorar dado). Configuracao e **escrita** — eixo diferente, mas a **mesma regua de custo de contexto** (§2) escolhe o recipiente.

| Tipo de config | Mecanismo |
|---|---|
| **Parametro atomico** (1 toggle/valor) | **Inline / edit-in-place** (`PropertyList` ja tem `editable`) |
| **Editar uma entidade de config** (credencial, usuario, etiqueta, regra) | **Drawer com form** (`?selected=` / `?action=new`) — patterns `ListagemCrudInline` / `ListagemCrudCards` |
| **Config com profundidade propria** (abas, canvas, varias secoes) | **Rota dedicada** (ex.: `/credito/workflows/[id]/editor`) |
| **Confirmar mudanca irreversivel** (excluir credencial, rotacionar chave, resetar) | **Modal** (AlertDialog) |

**Escopo da config:**

- **Config DE UM OBJETO** (premissas de *uma* projecao, limite de *um* cedente) mora junto do objeto — no drawer ou rota dele, com botao "editar".
- **Config DE SISTEMA / GLOBAL** (providers, tenant, feature flags, `premise_set`) mora no Admin como rota CRUD propria.

**Amarracao ao DNA do sistema (CLAUDE.md §14.3):** parametros e premissas sao **versionados em tabela**, nunca constantes, com trilha de auditoria. A UI de parametrizacao e sempre CRUD sobre tabela versionada — nunca um "modal de settings solto".

**Regra dura:** **form de config nunca vai em modal.** Modal e so decisao atomica/irreversivel. Form = drawer ou rota.

---

## 7. Anti-padroes (NAOs duros)

- Modal para **explorar/navegar** dado. Modal bloqueia comparacao lado a lado e quebra o fluxo.
- **Modal abrindo modal.** Proibido.
- **Drawer com mais de 2 camadas.** Se precisa de mais profundidade, **promova para rota.**
- **Drawer aninhado** como default. Default do detalhe pequeno e **inline dentro do drawer**; 2o sheet empilhado so quando o objeto aninhado e ele mesmo uma lista navegavel.
- **Form de config em modal** (ver §6).
- **Spinner de tela inteira** quando so o drawer esta carregando. Cada camada tem seu loading/empty/error.
- **Quebrar o back button** com navegacao fake.
- **Perder estado no refresh** (drawer/selecao que some).
- **Breadcrumb hardcoded** — derive da rota (o [`Breadcrumbs.tsx`](../frontend/src/design-system/components/Breadcrumbs.tsx) ja faz isso a partir do `pathname`).

---

## 8. Invariantes de interacao e acessibilidade

Use **primitivas Radix** (`Dialog`, `AlertDialog`) em vez de rolar a mao — focus trap, retorno de foco, `Esc`, roles ARIA e scrim vem de graca.

- **`Esc`** fecha a camada mais alta (modal > drawer). Uma camada por vez.
- **Foco retorna ao elemento que abriu** a camada, ao fechar.
- **Drawer:** clique no scrim fecha; botao de fechar visivel alem do scrim/Esc.
- **AlertDialog (aprovacao):** **nao** fecha por clique-fora nem por `Esc` sem escolha — exige confirmar ou cancelar.
- **Foco inicial** numa camada vai para o primeiro controle relevante (ou o titulo), nunca "perdido".

---

## 9. Compatibilidade com a hierarquia de 3 niveis (§11.6)

Drawer e modal **nao contam como nivel de navegacao** — sao ortogonais a hierarquia L1 (modulo) / L2 (sidebar) / L3 (TabNavigation). Coerente com a §11.6: se surgir um L4, ele vira filtro/modal/drawer, **nunca** um 4o nivel de navegacao. Um drawer aberto sobre uma pagina L3 nao e violacao de hierarquia.

---

## 10. Checklist por tela nova (rode antes de implementar)

- [ ] Qual o nivel na hierarquia (§3)? Qual mecanismo o procedimento (§2) indica?
- [ ] O contexto do pai precisa continuar vivo? (sim → drawer; nao e tem profundidade → rota)
- [ ] O estado precisa ser deep-linkable / sobreviver a refresh? (`?selected` + tab → URL; efemero → local)
- [ ] Drawer usa `nuqs` com `history: "push"` ao abrir e `"replace"` no prev/next?
- [ ] Ha decisao irreversivel? (sim → `AlertDialog`, e so ela bloqueia)
- [ ] E config/parametrizacao? Form esta em drawer ou rota (nunca modal)?
- [ ] Back button e breadcrumb corretos? (rotas reais, breadcrumb derivado do pathname)
- [ ] Loading/empty/error **por camada**, sem bloquear a tela toda?
- [ ] `Esc` / foco / fechar conferem com §8?
- [ ] Nao viola nenhum anti-padrao de §7?

---

### Resumo em uma linha

**Exploracao → inline/drawer (preserva contexto). Novo foco de trabalho → rota. Decisao irreversivel → modal. Form de config nunca em modal. Cedente/sacado/dossie viram rota; cessao/titulo/operacao sao drawer (`?selected` via nuqs, abrir=push); parcela/evento/linha do agente sao inline.**

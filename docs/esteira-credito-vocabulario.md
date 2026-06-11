# Esteira de Crédito — Vocabulário e Modelo Mental

> Referência canônica para explicar a esteira a qualquer pessoa (analista,
> gestor, cliente, dev novo). Nasceu da conversa com o Ricardo em 2026-06-12.
> Complementa o mapa técnico em [`esteira-credito-ia-map.md`](./esteira-credito-ia-map.md).

## A metáfora: um departamento de crédito digital

Cada elemento da esteira é um funcionário com um crachá diferente — e **nenhum
faz o trabalho do outro**. Essa separação não é estética: é o que faz a
esteira passar em auditoria (CVM/Bacen). Número nunca nasce de opinião, e
opinião nunca vira verdade sem homologação humana.

```
DOCUMENTO (PDF)
   │
   ▼
📋 O DIGITADOR ─────── lê o documento e preenche a FICHA
   (prompt de extração)      "extraia CNPJ, sócios, cláusulas de alçada..."
   │
   ▼
👤 O ANALISTA HUMANO ── confere a ficha campo a campo e HOMOLOGA
   (tela de conferência)     ficha homologada = verdade do dossiê
   │
   ▼
🗄️ O ARQUIVO ────────── junta ficha homologada + dados oficiais e calcula
   (serviço)                 os números frios: somas, idades, contrato × Receita
   │
   ├──▶ 🔍 O CONFERENTE ── aplica regras fixas e carimba
   │    (check)              "CNPJ bate? participações somam 100%?" → ✓ ou 🚩
   │
   └──▶ 🪟 O BALCÃO ────── janela onde o especialista pede a pasta
        (tool)               entrega o que o Arquivo montou (CPF tarjado — LGPD)
            │
            ▼
        🧠 O ESPECIALISTA ── pega a pasta e escreve o JULGAMENTO
           (agente)              "a alçada de 20% é governança adequada porque..."
```

Por cima de tudo: o **playbook** (montado no builder, `/credito/workflows`) é
o organograma — define quais funcionários trabalham, em que ordem, em qual
esteira. Na UI do analista, os nodes do playbook viram **estações** de
trabalho, e o resultado homologado de cada estação compila o **dossiê**.

## A frase de uma linha

> **"O digitador lê, o humano homologa, o arquivo organiza, o conferente
> carimba, o especialista opina — e nenhum deles faz o trabalho do outro."**

## Tabela de edição — quem mexe onde

| Funcionário | Nome técnico | O que se muda nele | Onde | Quem |
|---|---|---|---|---|
| 📋 Digitador | prompt `extract.<doc_type>` | O QUE e COMO ler do documento | `/admin/ia/prompts` | Mantenedor, sem deploy |
| 🧠 Especialista (julgamento) | prompt `agent.<aspecto>` | COMO julgar, o que pesa, tom | `/admin/ia/prompts` | Mantenedor, sem deploy |
| 🏭 Organograma | playbook (workflow) | etapas, ordem, qual check/agente em cada node | Builder (`/credito/workflows`) | Usuário, sem deploy |
| 🔍 Conferente | check (`@register_check`) | criar/alterar regra determinística | Código (`app/agentic/tools/credito/checks/`) | Dev |
| 🪟 Balcão | tool (`@register_tool`) | o que o especialista pode pedir | Código (`app/agentic/tools/credito/`) | Dev |
| 🗄️ Arquivo | serviço | cálculos frios + o que passa ao balcão (com redação de PII) | Código (`app/modules/credito/services/`) | Dev |

**O padrão:** texto, julgamento e fluxo são do usuário/mantenedor, na UI, sem
deploy. Cálculo, regra e encanamento são código — porque é o que o auditor
testa.

## Regras de ouro (por que é assim)

1. **Tool entrega DADO, check dá VEREDITO, agente JULGA.** O agente nunca
   recalcula (auditabilidade: o número é da tool); o check nunca opina; a
   tool nunca julga.
2. **O especialista só vê o que está na pasta.** Agente não relê documentos —
   recebe a ficha homologada via tool. Se algo do documento precisa chegar ao
   agente, o caminho é o digitador capturar (prompt de extração), nunca
   "deixar o agente ler tudo".
3. **O campo extraído é a unidade de auditabilidade.** Ficha estruturada
   permite conferência humana campo a campo, checks determinísticos e
   redação cirúrgica de PII. Texto corrido não permite nenhum dos três.
4. **O envelope do balcão é fixo; o conteúdo é aberto.** O serviço repassa
   chaves conhecidas (proteção de PII), mas campos-saco como
   `restricoes_estatutarias` (lista de {tema, resumo, referência}) deixam o
   mantenedor ampliar o alcance da extração sem código. Campo estrutural
   novo no balcão = 1 linha de dev (futuro: roteado por Contrato de Dados,
   Fase 3).
5. **Versão em tudo, deploy em quase nada.** Prompts e playbooks são
   imutáveis com ponteiro ativo: editar cria versão nova; ativar/reverter é
   1 clique; cada documento/análise registra a versão que o processou.

## Caso traçador: a cláusula dos 20% (SYSTEMPACK, DC-2026-0037)

Contrato com cláusula: "transações acima de 20% do capital exigem aprovação
dos administradores e ¾ das cotas".

- **Por que o agente não viu (v1):** o digitador não tinha instrução de
  copiar cláusulas na ficha — e o especialista só vê a pasta. A análise saiu
  rasa.
- **O conserto:** instrução nova ao digitador (`extract.social_contract@v2`):
  capturar administradores, poderes de assinatura e restrições/alçadas
  estatutárias. Arquivo passou a repassar; balcão, conferente e especialista
  não mudaram — a pasta ficou mais completa.
- **O desdobramento:** com a alçada estruturada, um check futuro
  (`alcada_x_pleito`) pode carimbar automaticamente: "pleito de R$ 2,5 mi
  excede 20% do capital de R$ 500 mil → operação exige aprovação de ¾ das
  cotas" — citando a cláusula. Texto vira veredito.

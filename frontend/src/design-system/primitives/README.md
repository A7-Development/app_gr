# Primitives

Re-export curado de Tremor Raw + `Sheet` (drawer lateral). Esta pasta NAO inventa primitivos -- ela e um **barrel oficial** que centraliza imports.

## Por que existe

Sem primitives barrel, cada arquivo importava `@/components/tremor/Button`, `@/components/tremor/Dialog`, etc. Com o barrel, o consumidor importa de um ponto so:

```ts
// Antes
import { Button } from "@/components/tremor/Button"
import { Dialog, DialogContent } from "@/components/tremor/Dialog"

// Depois
import { Button, Dialog, DialogContent } from "@/design-system/primitives"
```

`@/components/tremor/*` continua existindo como fonte verbatim (CLAUDE.md §3) -- nao mexer la.

## Arquivos

| Arquivo | Conteudo |
|---|---|
| `index.ts` | Re-exports de `Button`, `Card`, `Input`, `Badge`, `Divider`, `Label`, `Textarea`, `Checkbox`, `Switch`, `RadioGroup*`, `Select*`, `Tabs*`, `TabNavigation*`, `Dialog*`, `Drawer*`, `Tooltip*`, `Popover*`, `DropdownMenu*`, `Accordion*`, `Calendar`, `DatePicker*`, `Table*` -- todos do Tremor. + `Sheet*` (este arquivo). |
| `Sheet.tsx` | Right-side drawer (Radix Dialog stylized). Zonas: `SheetHeader`, `SheetHero`, `SheetBody`, `SheetFooter`. Tamanhos: `sm` (400px), `md` (560px), `lg` (720px). |

## Imports

```ts
import {
  // Tremor Raw (primitivos)
  Button, Card, Input, Badge, Divider, Label, Textarea,
  Checkbox, Switch, RadioGroup, RadioGroupItem,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Tabs, TabsContent, TabsList, TabsTrigger,
  TabNavigation, TabNavigationLink,
  Dialog, DialogContent, DialogTitle, DialogTrigger, DialogClose, DialogHeader, DialogFooter, DialogDescription,
  Drawer, DrawerContent, DrawerTrigger, ...,
  Tooltip,
  Popover, PopoverContent, PopoverTrigger,
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, ...,
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
  Calendar, type Matcher,
  DatePicker, DateRangePicker, type DateRange, type DatePreset,
  Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow, TableFoot, TableRoot,

  // Sheet (drawer lateral, exclusivo deste DS)
  Sheet, SheetContent, SheetHeader, SheetHero, SheetBody, SheetFooter,
  SheetTitle, SheetDescription, SheetTrigger, SheetClose,
  type SheetSize,
} from "@/design-system/primitives"
```

## Quando usar Sheet vs Drawer vs Dialog

| Caso | Use |
|---|---|
| Drill-down de linha de tabela com hero/tabs/property list | `<DrillDownSheet>` (`@/design-system/components/DrillDownSheet`) -- compound API |
| Drawer simples lateral (form ou chat) | `<Drawer>` Tremor |
| Modal centrado (alert, confirmacao, form curto) | `<Dialog>` Tremor |
| Sheet customizado sem features de drill-down | `<Sheet>` primitivo (este aqui) |

## Proibido

- Importar Radix cru para algo que o Tremor ja cobre -- use o primitivo curado
- Adicionar primitivo novo sem motivo claro -- `Sheet` foi adicionado porque o Tremor `Drawer` nao tem zonas estruturadas (Hero, Body, Footer); para outras necessidades reutilizar Tremor

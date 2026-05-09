// src/design-system/primitives/index.ts
// Barrel export for all design system primitives.
// Primitives = Tremor Raw re-exports + Sheet (right-side drill-down container).
//
// Usage:
//   import { Button, Card, Sheet, SheetContent } from "@/design-system/primitives"

export { Button, buttonVariants, type ButtonProps } from "@/components/tremor/Button"
export { Input, inputStyles, type InputProps } from "@/components/tremor/Input"
export { Card, type CardProps } from "@/components/tremor/Card"
export { Badge, badgeVariants, type BadgeProps } from "@/components/tremor/Badge"
export { Divider } from "@/components/tremor/Divider"
export { Label } from "@/components/tremor/Label"
export { Textarea, type TextareaProps } from "@/components/tremor/Textarea"
export { Checkbox } from "@/components/tremor/Checkbox"
export { Switch } from "@/components/tremor/Switch"
export { RadioGroup, RadioGroupItem } from "@/components/tremor/RadioGroup"
export {
  Select,
  SelectContent,
  SelectGroup,
  SelectGroupLabel,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
export {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/tremor/Tabs"
export {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/tremor/Dialog"
export {
  Drawer,
  DrawerBody,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/tremor/Drawer"
export {
  Tooltip,
  type TooltipProps,
} from "@/components/tremor/Tooltip"
export {
  Popover,
  PopoverAnchor,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuSubMenuTrigger,
  DropdownMenuSubMenu,
  DropdownMenuSubMenuContent,
  DropdownMenuGroup,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuCheckboxItem,
  DropdownMenuIconWrapper,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/tremor/DropdownMenu"
export {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/tremor/Accordion"
export { Calendar, type Matcher } from "@/components/tremor/Calendar"
export {
  DatePicker,
  DateRangePicker,
  type DatePreset,
  type DateRangePreset,
  type DateRange,
} from "@/components/tremor/DatePicker"
export {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFoot,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"

// Sheet primitive (right-side drill-down)
export {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetHero,
  SheetTitle,
  SheetTrigger,
  type SheetSize,
} from "./Sheet"

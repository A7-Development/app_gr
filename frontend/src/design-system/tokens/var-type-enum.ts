// src/design-system/tokens/var-type-enum.ts
//
// Espelha o enum VarType de
// `backend/app/shared/workflow/nodes/_base.py::VarType`. Mantenha em
// sincronia — se adicionar VarType novo no backend, adicione aqui também
// (e o token visual em var-type.ts).

export type VarType =
  | "string"
  | "cpf"
  | "cnpj"
  | "email"
  | "phone"
  | "date"
  | "datetime"
  | "number"
  | "money_brl"
  | "score"
  | "boolean"
  | "url"
  | "uuid"
  | "file"
  | "object"
  | "list"

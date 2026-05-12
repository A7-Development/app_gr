#!/usr/bin/env node
/**
 * PostToolUse hook: design-system audit reminder.
 *
 * Reads the hook payload from stdin (JSON with `tool_input.file_path`).
 * If the file is in a UI-critical area (frontend/src/app/(app)/**.tsx or
 * frontend/src/design-system/components/**.tsx), emits a JSON response
 * that injects a `system-reminder` into the next turn telling Claude to
 * invoke the `audit-page-consistency` skill on that file.
 *
 * Stays SILENT (no stdout, exit 0) for non-matching files so it doesn't
 * spam during normal operation.
 *
 * MODO DESIGN EXPLORATORIO gate (2026-05-11): hook fica desligado enquanto
 * o banner "MODO DESIGN EXPLORATORIO ATIVO" estiver presente em CLAUDE.md.
 * Source of truth e o proprio CLAUDE.md — remover o banner re-ativa o hook
 * automaticamente. Skill audit-page-consistency continua disponivel via
 * invocacao manual.
 *
 * Exit codes:
 *   0 — always (we never block; this hook is purely advisory)
 */

const fs = require("fs");
const path = require("path");

try {
  const claudeMdPath = path.resolve(__dirname, "..", "..", "CLAUDE.md");
  const claudeMd = fs.readFileSync(claudeMdPath, "utf8");
  if (/MODO DESIGN EXPLORATORIO ATIVO/.test(claudeMd)) {
    process.exit(0);
  }
} catch {
  // If CLAUDE.md unreadable, fall through to default (audit enabled).
}

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (raw += chunk));
process.stdin.on("end", () => {
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  const filePath =
    payload?.tool_input?.file_path ??
    payload?.tool_response?.filePath ??
    "";
  if (!filePath) process.exit(0);

  // Normalize backslashes (Windows) to forward slashes for matching.
  const norm = filePath.replace(/\\/g, "/");

  const isCritical =
    /\/frontend\/src\/app\/\(app\)\/.+\.tsx$/.test(norm) ||
    /\/frontend\/src\/design-system\/components\/.+\.tsx$/.test(norm);

  if (!isCritical) process.exit(0);

  const message =
    `DESIGN SYSTEM AUDIT NEEDED — arquivo ${filePath} editado em zona de UI critica ` +
    `(frontend/src/app/(app)/ ou frontend/src/design-system/components/). ` +
    `Antes de marcar a tarefa como completa, invoque a skill audit-page-consistency ` +
    `neste arquivo. Foco em violacoes Tremor/Strata: ` +
    `(1) <table> HTML cru ou Tremor Table cru — deve usar <DataTableShell> ou <DataTable>; ` +
    `(2) magic numbers como text-[Npx], p-[Npx], px-[Npx], py-[Npx], gap-[Npx] — ` +
    `usar tokens em design-system/tokens/ (cardTokens, tableTokens, nodeCategoryTokens); ` +
    `(3) cores Tailwind fora da paleta canonica do CLAUDE.md sec 4 ` +
    `(emerald/amber/violet/rose/teal/sky/indigo soltas — so OK em chart series via chartUtils ` +
    `ou via tokens nomeados de identidade); ` +
    `(4) Card headers com paddings inventados — usar cardTokens.header/body; ` +
    `(5) hex literals (#XXXXXX) ou rgba() soltos fora dos tokens; ` +
    `(6) inline styles style={{...}} fora das excecoes documentadas em CLAUDE.md sec 5 ` +
    `(EChartsOption + radial-gradient multi-stop em surfaces/); ` +
    `(7) cn() ou classnames usado em vez de cx(); ` +
    `(8) icones nao Ri* (lucide, heroicons, react-icons proibidos). ` +
    `Reporte violacoes e ja proponha as correcoes.`;

  const out = {
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: message,
    },
    suppressOutput: true,
  };

  process.stdout.write(JSON.stringify(out));
  process.exit(0);
});

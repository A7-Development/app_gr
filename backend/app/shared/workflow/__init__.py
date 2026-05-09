"""Workflow engine — shared kernel.

Provides the primitives for defining and executing workflows of nodes
(triggers, document requests, specialist agents, human reviews, etc).

This is a SHARED KERNEL — modules consume it via `app.shared.workflow.public`.
The credito module instantiates one workflow per dossie. Future modules
(risco, laboratorio) may consume it for their own automated processes.

See CLAUDE.md and ~/.claude/plans/c-users-ricardopimenta-a7-credit-securi-agile-hearth.md
for the architectural plan.
"""

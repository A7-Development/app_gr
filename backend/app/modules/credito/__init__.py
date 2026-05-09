"""Credito module — credit dossier platform.

The credito module wraps the workflow engine (`app.shared.workflow`) with
domain semantics: a "dossie" is a credit analysis container that orchestrates
bureau queries, document uploads, IA specialist agents, and a final opinion
for the credit committee.

See ~/.claude/plans/c-users-ricardopimenta-a7-credit-securi-agile-hearth.md
for the full architectural plan and CLAUDE.md sec 11 for module rules.
"""

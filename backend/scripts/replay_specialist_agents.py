"""Replay specialist_agent + opinion nodes against current silver/state.

Caso de uso: bug de exposicao em algum node upstream (ex.: counts errados
no bureau_query) gerou agentes especialistas com analise calibrada em cima
do dado errado. Apos corrigir o bug e re-mapear silver, este script
re-executa os specialist_agents downstream sem rodar workflow inteiro
(nao paga consulta a bureau, nao recria human_input, nao toca trigger).

Cada node listado em --nodes:
    1. Carrega previous_outputs (todos os COMPLETED anteriores em
       ordem de started_at — assim o agente le o output ATUAL do
       upstream, ja patcheado).
    2. Monta NodeContext.
    3. Instancia SpecialistAgentNode com config={"agent": <agent_name>}
       (lido de input_data.agent do node_run existente).
    4. Roda execute() — chama Anthropic, valida schema.
    5. Atualiza workflow_node_run.output_data + tokens + cost.

Uso (do diretorio backend/):

    .venv\\Scripts\\python.exe scripts/replay_specialist_agents.py \\
        --run-id 735b8402-ccfb-49a8-a951-9f9d547ab807 \\
        --nodes specialist_agent_mtful9,opinion

Nao apaga decision_log/ai_usage_event antigos — fica como trilha do
estado anterior (auditoria preserva o bug + a correcao).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  ensure mapper resolution
import app.warehouse  # noqa: F401  ensure warehouse models registered

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.shared.workflow.models.run import WorkflowNodeRun, WorkflowRun
from app.shared.workflow.nodes._base import NodeContext
from app.shared.workflow.nodes.specialist_agent import SpecialistAgentNode


async def replay(run_id_str: str, node_ids: list[str]) -> int:
    run_id = UUID(run_id_str)

    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_id)
        if run is None:
            print(f"[erro] workflow_run {run_id} nao encontrado", file=sys.stderr)
            return 2

        for target_node_id in node_ids:
            target_node_id = target_node_id.strip()

            # Re-le node_runs a CADA iteracao — garante que previous_outputs
            # leia o output ATUAL (incluindo nodes regravados em iteracoes
            # anteriores deste mesmo replay).
            all_runs = (
                await db.execute(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.run_id == run_id)
                    .order_by(WorkflowNodeRun.started_at)
                )
            ).scalars().all()
            run_by_node_id = {nr.node_id: nr for nr in all_runs}

            nr = run_by_node_id.get(target_node_id)
            if nr is None:
                print(
                    f"[erro] node_id '{target_node_id}' nao encontrado em run",
                    file=sys.stderr,
                )
                continue
            if nr.node_type != "specialist_agent":
                print(
                    f"[erro] {target_node_id} nao e specialist_agent "
                    f"(type={nr.node_type})",
                    file=sys.stderr,
                )
                continue

            agent_name = (nr.input_data or {}).get("agent")
            if not agent_name:
                print(
                    f"[erro] {target_node_id}: input_data.agent ausente",
                    file=sys.stderr,
                )
                continue

            print(f"\n[replay] {target_node_id} (agent={agent_name})")

            previous_outputs: dict[str, dict] = {}
            for other in all_runs:
                if other.node_id == target_node_id:
                    break
                if other.status == "COMPLETED":
                    previous_outputs[other.node_id] = {
                        "output": other.output_data or {},
                        "duration_ms": other.duration_ms or 0,
                    }

            ctx = NodeContext(
                run_id=run.id,
                tenant_id=run.tenant_id,
                node_id=target_node_id,
                initiated_by=run.initiated_by,
                previous_outputs=previous_outputs,
                trigger_data=run.trigger_data or {},
            )

            node = SpecialistAgentNode(config={"agent": agent_name})
            try:
                result = await node.execute(ctx, db)
            except Exception as e:
                print(
                    f"  FAIL: {type(e).__name__}: {e}", file=sys.stderr
                )
                continue

            nr.output_data = result.data
            nr.tokens_input = result.tokens_input
            nr.tokens_output = result.tokens_output
            nr.cost_brl = result.cost_brl
            await db.commit()
            await db.refresh(nr)

            run_by_node_id[target_node_id] = nr

            print(
                f"  OK: tokens in/out={result.tokens_input}/"
                f"{result.tokens_output} cost=R${result.cost_brl}"
            )

    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--nodes",
        required=True,
        help=(
            "comma-separated node_ids em ordem de execucao "
            "(o primeiro e re-rodado primeiro; previous_outputs do segundo "
            "ja inclui o novo output do primeiro)"
        ),
    )
    args = parser.parse_args()
    return await replay(args.run_id, args.nodes.split(","))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

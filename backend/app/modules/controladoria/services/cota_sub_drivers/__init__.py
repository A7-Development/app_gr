"""Drivers da Cota Sub — primeiro consumidor do framework MetricSpec.

Fase 3b do refactor de proveniencia transversal (2026-05-18). Cada driver
declara seu MetricSpec aqui; o compute_fn correspondente vive em
`compute.py` (a ser criado na proxima sessao). O service `cota_sub.py`
orquestra: itera os 11 drivers, chama compute_fn de cada um, acumula
DriverResult[], compara Sigma drivers com Delta_PL_MEC e expoe o residuo.

Ver memo `project_cota_sub_metodo_gestor` (2026-05-17) — decomposicao em
11 categorias patrimoniais derivada da planilha do gestor REALINVEST,
substituindo os 7 explainers heuristicos e o particionamento COSIF do
mesmo dia.
"""

from app.modules.controladoria.services.cota_sub_drivers.catalog import (
    COTA_SUB_DRIVERS,
    COTA_SUB_DRIVERS_BY_NAME,
    get_driver_spec,
)
from app.modules.controladoria.services.cota_sub_drivers.compute import (
    COMPUTE_FNS,
    CotaSubDriversComputation,
    DriverResult,
    Evidence,
    compute_drivers,
)

__all__ = [
    "COMPUTE_FNS",
    "COTA_SUB_DRIVERS",
    "COTA_SUB_DRIVERS_BY_NAME",
    "CotaSubDriversComputation",
    "DriverResult",
    "Evidence",
    "compute_drivers",
    "get_driver_spec",
]

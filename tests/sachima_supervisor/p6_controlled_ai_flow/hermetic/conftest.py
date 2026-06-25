"""P6-A hermetic-local merge-gate binding (FR5/FR8).

Every test here runs a **real** ops-owned Temporal Worker inside a hermetic
time-skipping env under an isolated namespace — no production / staging cluster.
Importing the harness here fails collection early (one error for the whole gate)
if the hermetic surface is broken, and is the single place for shared fixtures.
"""

from __future__ import annotations

from tests.sachima_supervisor.p6_controlled_ai_flow.hermetic import _harness  # noqa: F401

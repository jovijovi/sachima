"""Hermetic-local Temporal merge-gate binding (T9, FR8, Gate H).

All tests in this directory are the **merge-blocking** hermetic-local gate: they
run a real Temporal Worker inside ``WorkflowEnvironment.start_time_skipping()``
under an isolated namespace, with no production / staging cluster dependency.

The reusable harness lives in ``_harness.py`` (env + ops Worker + runtime client
+ sandbox passthrough runner). This conftest imports it so a harness import error
surfaces as a collection error for the whole gate rather than per test, and is the
single place to add shared hermetic fixtures.
"""

from __future__ import annotations

# Importing the harness here binds every probe module to the same env/worker
# construction and fails collection early if the hermetic surface is broken.
from tests.sachima_supervisor.p5_temporal.hermetic import _harness  # noqa: F401

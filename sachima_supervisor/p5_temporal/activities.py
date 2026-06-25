"""P5 Temporal Slice 1 activities (FR2/FR5).

The Slice 1 ``p5_step_activity`` body is **controlled-deterministic**: it
validates the sanitized activity input and produces exactly one claim-check
artifact ref + digest. There is **no** real ``acpx``/agent execution, no
subprocess, no socket, no network, and no raw stdout / exception text — the body
is a pure function of the sanitized input, so it can never leak material into
Temporal history.
"""

from __future__ import annotations

from temporalio import activity

from . import contracts as C

P5_STEP_ACTIVITY_NAME = "p5_step_activity"


@activity.defn(name=P5_STEP_ACTIVITY_NAME)
async def p5_step_activity(value: C.ActivityInput) -> C.ActivityOutput:
    """Controlled-deterministic step body — claim-check artifact ref only."""

    return C.build_activity_output(value)


#: Activity registration list for the ops-owned Worker builder.
P5_TEMPORAL_ACTIVITIES = [p5_step_activity]


__all__ = ["P5_STEP_ACTIVITY_NAME", "p5_step_activity", "P5_TEMPORAL_ACTIVITIES"]

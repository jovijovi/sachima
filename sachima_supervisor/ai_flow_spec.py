"""Controlled AI FLOW workflow-spec validation (WP4 slice 1, FR1).

Local/offline only. Defines the caller-owned, schema-versioned workflow
specification dataclasses and ``validate_workflow_spec`` — a fail-closed,
exact-typed validator that accepts only a bounded, acyclic, linear, read-only
graph and rejects everything else (wrong schema, cycles, duplicate/unknown
steps, undeclared edges, fan-out beyond the linear slice-1 shape, missing or
unknown/future role keys, non-read/search capabilities, hostile container
subclasses, and unsatisfied input/output contracts).

This module owns its own boundary validators by convention (see the WP4
architecture packet §1.3): sanitization primitives are duplicated per module on
purpose so a change to one slice's validator can never silently alter another's
security boundary. Only the **public** role-binding constants are imported from
``activity_controlled_exec`` so the runnable allowlist stays in lockstep.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .activity_controlled_exec import (
    CONTROLLED_EXEC_FUTURE_ROLE_KEYS,
    CONTROLLED_EXEC_ROLE_ALLOWLIST,
)

# --------------------------------------------------------------------------- #
# Public constants
# --------------------------------------------------------------------------- #
SCHEMA_VERSION = "sachima.ai_flow.local.v1"

#: Read-only capabilities a workflow role may declare. Anything else is a
#: security/authorization failure (terminal, non-retryable).
ALLOWED_CAPABILITIES: tuple[str, ...] = ("read", "search")

#: Finite ceilings so an over-large bound can never be admitted. Slice 1 stays
#: small and bounded by construction.
MAX_STEPS_CEILING = 16
MAX_RETRIES_CEILING = 8
MAX_ARTIFACT_BYTES_CEILING = 8 * 1024 * 1024
MAX_RUNTIME_SECONDS_CEILING = 24 * 60 * 60

_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "workflow_id", "approval_ref", "bounds", "roles", "steps", "edges"}
)
_BOUNDS_KEYS = frozenset(
    {"max_steps", "max_retries_per_step", "max_artifact_bytes", "max_runtime_seconds"}
)
_ROLE_KEYS = frozenset({"role_key", "capabilities"})
_STEP_KEYS = frozenset(
    {"step_id", "logical_role", "input_refs", "output_contract", "depends_on"}
)

_REF_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


# --------------------------------------------------------------------------- #
# Public dataclasses + error
# --------------------------------------------------------------------------- #
class AiFlowSpecError(Exception):
    """Fail-closed workflow-spec validation error carrying a stable code."""

    def __init__(self, error_code: str, message: str = "") -> None:
        self.error_code = error_code
        super().__init__(message or error_code)


@dataclass(frozen=True)
class RoleBinding:
    logical_role: str
    role_key: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    logical_role: str
    input_refs: tuple[str, ...]
    output_contract: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowBounds:
    max_steps: int
    max_retries_per_step: int
    max_artifact_bytes: int
    max_runtime_seconds: int


@dataclass(frozen=True)
class WorkflowSpec:
    schema_version: str
    workflow_id: str
    approval_ref: str
    bounds: WorkflowBounds
    roles: tuple[RoleBinding, ...]
    steps: tuple[StepSpec, ...]
    edges: tuple[tuple[str, str], ...]


# --------------------------------------------------------------------------- #
# Exact-type primitives (copied per module by convention)
# --------------------------------------------------------------------------- #
def _is_exact_str(value: Any) -> bool:
    return type(value) is str


def _is_safe_ref(value: Any) -> bool:
    return _is_exact_str(value) and _REF_RE.fullmatch(value) is not None


def _is_exact_int(value: Any) -> bool:
    # ``type(True) is int`` is False, so booleans are rejected here.
    return type(value) is int


def _reject(code: str, message: str) -> AiFlowSpecError:
    return AiFlowSpecError(code, message)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _validate_bounds(raw: Any) -> WorkflowBounds:
    if type(raw) is not dict or set(raw) != _BOUNDS_KEYS:
        raise _reject("spec_bounds_invalid", "bounds must be an exact bounds mapping")
    ceilings = {
        "max_steps": MAX_STEPS_CEILING,
        "max_retries_per_step": MAX_RETRIES_CEILING,
        "max_artifact_bytes": MAX_ARTIFACT_BYTES_CEILING,
        "max_runtime_seconds": MAX_RUNTIME_SECONDS_CEILING,
    }
    for key, ceiling in ceilings.items():
        value = raw[key]
        if not _is_exact_int(value) or value < 1 or value > ceiling:
            raise _reject(
                "spec_bounds_invalid",
                f"bound {key!r} must be a positive int within its ceiling",
            )
    return WorkflowBounds(
        max_steps=raw["max_steps"],
        max_retries_per_step=raw["max_retries_per_step"],
        max_artifact_bytes=raw["max_artifact_bytes"],
        max_runtime_seconds=raw["max_runtime_seconds"],
    )


def _validate_roles(raw: Any) -> tuple[RoleBinding, ...]:
    if type(raw) is not dict or not raw:
        raise _reject("spec_roles_invalid", "roles must be a non-empty mapping")
    bindings: list[RoleBinding] = []
    for logical_role, body in raw.items():
        if not _is_safe_ref(logical_role):
            raise _reject("spec_roles_invalid", "unsafe logical role name")
        if type(body) is not dict or set(body) != _ROLE_KEYS:
            raise _reject("spec_roles_invalid", "role body must be an exact mapping")
        role_key = body["role_key"]
        if not _is_exact_str(role_key):
            raise _reject("spec_roles_invalid", "role_key must be an exact str")
        if role_key in CONTROLLED_EXEC_FUTURE_ROLE_KEYS:
            raise _reject(
                "spec_role_capability_rejected",
                "future/write-capable role key is not runnable in slice 1",
            )
        if CONTROLLED_EXEC_ROLE_ALLOWLIST.get(role_key) is None:
            raise _reject("spec_unknown_role", "role_key is not in the read-only allowlist")
        capabilities = body["capabilities"]
        if type(capabilities) is not list or not capabilities:
            raise _reject("spec_role_capability_rejected", "capabilities must be a non-empty list")
        seen: set[str] = set()
        for cap in capabilities:
            if not _is_exact_str(cap) or cap not in ALLOWED_CAPABILITIES or cap in seen:
                raise _reject(
                    "spec_role_capability_rejected",
                    "capabilities must be a unique subset of (read, search)",
                )
            seen.add(cap)
        bindings.append(
            RoleBinding(
                logical_role=logical_role,
                role_key=role_key,
                capabilities=tuple(capabilities),
            )
        )
    return tuple(bindings)


def _validate_steps(raw: Any, *, role_names: set[str], max_steps: int) -> tuple[StepSpec, ...]:
    if type(raw) is not list or not raw:
        raise _reject("spec_steps_invalid", "steps must be a non-empty list")
    if len(raw) > max_steps:
        raise _reject("spec_bounds_exceeded", "step count exceeds max_steps")
    steps: list[StepSpec] = []
    seen_ids: set[str] = set()
    for entry in raw:
        if type(entry) is not dict or set(entry) != _STEP_KEYS:
            raise _reject("spec_steps_invalid", "step must be an exact step mapping")
        step_id = entry["step_id"]
        if not _is_safe_ref(step_id):
            raise _reject("spec_steps_invalid", "unsafe step id")
        if step_id in seen_ids:
            raise _reject("spec_duplicate_step", "duplicate step id")
        seen_ids.add(step_id)
        logical_role = entry["logical_role"]
        if not _is_safe_ref(logical_role) or logical_role not in role_names:
            raise _reject("spec_missing_role_binding", "step references an undeclared role")
        input_refs = entry["input_refs"]
        if type(input_refs) is not list or any(not _is_safe_ref(r) for r in input_refs):
            raise _reject("spec_steps_invalid", "input_refs must be a list of safe refs")
        output_contract = entry["output_contract"]
        if not _is_safe_ref(output_contract):
            raise _reject("spec_contract_invalid", "output_contract must be a non-empty safe ref")
        depends_on = entry["depends_on"]
        if type(depends_on) is not list or any(not _is_safe_ref(d) for d in depends_on):
            raise _reject("spec_steps_invalid", "depends_on must be a list of safe refs")
        steps.append(
            StepSpec(
                step_id=step_id,
                logical_role=logical_role,
                input_refs=tuple(input_refs),
                output_contract=output_contract,
                depends_on=tuple(depends_on),
            )
        )
    return tuple(steps)


def _validate_graph(steps: tuple[StepSpec, ...], raw_edges: Any) -> tuple[tuple[str, str], ...]:
    step_ids = {step.step_id for step in steps}
    # depends_on entries must reference real steps and not self.
    for step in steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                raise _reject("spec_unknown_edge", "depends_on references an unknown step")
            if dep == step.step_id:
                raise _reject("spec_cycle", "step cannot depend on itself")
    expected_edges = {
        (dep, step.step_id) for step in steps for dep in step.depends_on
    }
    # edges must be an exact, declared, non-duplicate set derivable from deps.
    if type(raw_edges) is not list:
        raise _reject("spec_edges_invalid", "edges must be a list")
    parsed: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for edge in raw_edges:
        if type(edge) is not list or len(edge) != 2:
            raise _reject("spec_edges_invalid", "each edge must be a [from, to] pair")
        src, dst = edge
        if not _is_exact_str(src) or not _is_exact_str(dst):
            raise _reject("spec_edges_invalid", "edge endpoints must be exact strings")
        if src not in step_ids or dst not in step_ids:
            raise _reject("spec_unknown_edge", "edge endpoint is not a declared step")
        pair = (src, dst)
        if pair in seen_edges:
            raise _reject("spec_edges_invalid", "duplicate edge")
        seen_edges.add(pair)
        parsed.append(pair)
    if seen_edges != expected_edges:
        raise _reject(
            "spec_edges_not_derivable",
            "edges must equal the set derivable from declared dependencies",
        )
    # Linear shape: each node has in-degree <= 1 and out-degree <= 1.
    out_degree: dict[str, int] = {}
    in_degree: dict[str, int] = {}
    for src, dst in parsed:
        out_degree[src] = out_degree.get(src, 0) + 1
        in_degree[dst] = in_degree.get(dst, 0) + 1
    if any(value > 1 for value in out_degree.values()) or any(
        value > 1 for value in in_degree.values()
    ):
        raise _reject("spec_fan_out_rejected", "graph fans out beyond the linear slice-1 shape")
    _assert_acyclic(steps, parsed)
    return tuple(parsed)


def _assert_acyclic(steps: tuple[StepSpec, ...], edges: list[tuple[str, str]]) -> None:
    # Kahn's algorithm over the declared edge set.
    indeg = {step.step_id: 0 for step in steps}
    adj: dict[str, list[str]] = {step.step_id: [] for step in steps}
    for src, dst in edges:
        indeg[dst] += 1
        adj[src].append(dst)
    queue = [node for node, deg in indeg.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for nxt in adj[node]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if visited != len(steps):
        raise _reject("spec_cycle", "workflow graph contains a cycle")


def _validate_contracts(steps: tuple[StepSpec, ...]) -> None:
    by_id = {step.step_id: step for step in steps}
    # Reverse reachability: ancestors[step] = all transitive predecessors.
    ancestors: dict[str, set[str]] = {}

    def _ancestors(step_id: str, stack: tuple[str, ...] = ()) -> set[str]:
        if step_id in ancestors:
            return ancestors[step_id]
        acc: set[str] = set()
        for dep in by_id[step_id].depends_on:
            acc.add(dep)
            acc |= _ancestors(dep, stack + (step_id,))
        ancestors[step_id] = acc
        return acc

    for step in steps:
        anc = _ancestors(step.step_id)
        produced_upstream = {by_id[a].output_contract for a in anc}
        for ref in step.input_refs:
            if step.depends_on:
                # Non-root steps must consume only an ancestor's output contract.
                if ref not in produced_upstream:
                    raise _reject(
                        "spec_contract_invalid",
                        "input ref is not produced by any upstream step",
                    )
            # Root steps consume external workflow inputs; safe refs already checked.


def validate_workflow_spec(raw: Mapping[str, Any]) -> WorkflowSpec:
    """Validate a raw workflow mapping into a frozen ``WorkflowSpec``.

    Fail-closed and exact-typed: the root must be a plain ``dict`` with exactly
    the declared keys; hostile ``str``/``dict``/``list`` subclasses are rejected
    because every primitive check uses ``type(x) is ...`` rather than
    ``isinstance``.
    """

    if type(raw) is not dict or set(raw) != _TOP_LEVEL_KEYS:
        raise _reject("spec_shape_invalid", "workflow spec must be an exact plain mapping")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise _reject("spec_schema_version_mismatch", "unsupported workflow schema version")
    if not _is_safe_ref(raw["workflow_id"]):
        raise _reject("spec_shape_invalid", "workflow_id must be a safe ref")
    if not _is_safe_ref(raw["approval_ref"]):
        raise _reject("spec_shape_invalid", "approval_ref must be a safe ref")

    bounds = _validate_bounds(raw["bounds"])
    roles = _validate_roles(raw["roles"])
    role_names = {role.logical_role for role in roles}
    steps = _validate_steps(raw["steps"], role_names=role_names, max_steps=bounds.max_steps)
    edges = _validate_graph(steps, raw["edges"])
    _validate_contracts(steps)
    return WorkflowSpec(
        schema_version=raw["schema_version"],
        workflow_id=raw["workflow_id"],
        approval_ref=raw["approval_ref"],
        bounds=bounds,
        roles=roles,
        steps=steps,
        edges=edges,
    )


# --------------------------------------------------------------------------- #
# Digests
# --------------------------------------------------------------------------- #
def _digest_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _spec_projection(spec: WorkflowSpec) -> dict[str, Any]:
    return {
        "schema_version": spec.schema_version,
        "workflow_id": spec.workflow_id,
        "approval_ref": spec.approval_ref,
        "bounds": {
            "max_steps": spec.bounds.max_steps,
            "max_retries_per_step": spec.bounds.max_retries_per_step,
            "max_artifact_bytes": spec.bounds.max_artifact_bytes,
            "max_runtime_seconds": spec.bounds.max_runtime_seconds,
        },
        "roles": sorted(
            (
                {
                    "logical_role": role.logical_role,
                    "role_key": role.role_key,
                    "capabilities": list(role.capabilities),
                }
                for role in spec.roles
            ),
            key=lambda item: item["logical_role"],
        ),
        "steps": [
            {
                "step_id": step.step_id,
                "logical_role": step.logical_role,
                "input_refs": list(step.input_refs),
                "output_contract": step.output_contract,
                "depends_on": list(step.depends_on),
            }
            for step in spec.steps
        ],
        "edges": sorted([list(edge) for edge in spec.edges]),
    }


def workflow_spec_digest(spec: WorkflowSpec) -> str:
    """Return ``sha256:<hex>`` over the canonical workflow-spec projection."""

    return _digest_hex(_spec_projection(spec))


def role_binding_digest(spec: WorkflowSpec) -> str:
    """Return ``sha256:<hex>`` over the canonical role-binding projection."""

    projection = sorted(
        (
            {
                "logical_role": role.logical_role,
                "role_key": role.role_key,
                "capabilities": list(role.capabilities),
            }
            for role in spec.roles
        ),
        key=lambda item: item["logical_role"],
    )
    return _digest_hex({"role_bindings": projection})


# --------------------------------------------------------------------------- #
# Canonical read-only flow (pure deterministic data, reused by tests/smoke)
# --------------------------------------------------------------------------- #
def canonical_read_only_workflow_mapping() -> dict[str, Any]:
    """Return a fresh, independent copy of the canonical bounded linear flow.

    ``architect -> programmer_candidate -> reviewer``, all bound to read-only
    role keys. Returned as a deeply independent dict so callers may mutate it
    for negative tests without affecting one another.
    """

    return {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": "wf_controlled_ai_flow_local_v1",
        "approval_ref": "controlled_ai_flow_approval_v1",
        "bounds": {
            "max_steps": 3,
            "max_retries_per_step": 1,
            "max_artifact_bytes": 65536,
            "max_runtime_seconds": 900,
        },
        "roles": {
            "architect": {
                "role_key": "sachima.claude.read_only_reviewer",
                "capabilities": ["read", "search"],
            },
            "programmer_candidate": {
                "role_key": "sachima.claude.read_only_reviewer",
                "capabilities": ["read", "search"],
            },
            "reviewer": {
                "role_key": "sachima.codex.primary_reviewer",
                "capabilities": ["read", "search"],
            },
        },
        "steps": [
            {
                "step_id": "architect",
                "logical_role": "architect",
                "input_refs": ["request_summary"],
                "output_contract": "architecture_packet",
                "depends_on": [],
            },
            {
                "step_id": "programmer_candidate",
                "logical_role": "programmer_candidate",
                "input_refs": ["architecture_packet"],
                "output_contract": "implementation_candidate_analysis",
                "depends_on": ["architect"],
            },
            {
                "step_id": "reviewer",
                "logical_role": "reviewer",
                "input_refs": ["implementation_candidate_analysis"],
                "output_contract": "blocker_review",
                "depends_on": ["programmer_candidate"],
            },
        ],
        "edges": [
            ["architect", "programmer_candidate"],
            ["programmer_candidate", "reviewer"],
        ],
    }

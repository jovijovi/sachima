"""The shared role-routing matrix — one YAML authority, parsed once, read twice.

What is proven here:

* the accepted shape parses **exactly**: model/effort literals are preserved
  byte-for-byte (context suffixes, embedded selectors, the literal ``N/A``
  effort), a ``null`` fallback and an exact fallback pair both round-trip, and
  the source digest is the digest of the file bytes;
* every deviation from the accepted shape fails closed with one stable code
  and never echoes the material;
* resolution answers with exactly one of four stable codes — unconfigured,
  invalid, missing, paused — and never with an AGENT-wide fallback, and it
  re-reads the file on every call so an edit applies to the next question;
* the rendered table keeps the original column order and filters exactly;
* the module CLI validates, renders, and filters the same parsed authority,
  and reports invalid material as a stable code only.

Fixtures are generic: no deployment matrix, no display names, no operator
path. Forbidden terms in this prose are no-leak boundary canaries only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from gateway.sachima_agent_role_routing_matrix import (
    ROUTING_MATRIX_SCHEMA_VERSION,
    SACHIMA_ROLE_ROUTE_MISSING,
    SACHIMA_ROLE_ROUTE_PAUSED,
    SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV,
    SACHIMA_ROLE_ROUTING_MATRIX_INVALID,
    SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED,
    SACHIMA_ROLE_ROUTING_STABLE_CODES,
    RoleRouteFallback,
    RoleRoutingMatrixSource,
    RoutingMatrixError,
    build_routing_matrix,
    load_routing_matrix,
    main,
    parse_routing_matrix,
    render_routing_matrix_table,
    resolve_role_route,
)

MODEL_BIG = "model-alpha-big[1m]"
MODEL_SMALL = "model-alpha-small[1m]"
MODEL_REVIEW = "model-alpha-review"
MODEL_SELECTOR = "model-beta[effort=high,fast=true]"
SECRET_CANARY = "canary-matrix-material-must-never-be-echoed"

VALID_YAML = f"""\
schema_version: 1
default_agents:
  architect: alpha
routes:
  - agent_id: alpha
    role_id: architect
    availability: Available
    model: "{MODEL_BIG}"
    effort: max
    fallback:
      model: "{MODEL_SMALL}"
      effort: max
  - agent_id: alpha
    role_id: code_reviewer
    availability: Available
    model: "{MODEL_REVIEW}"
    effort: xhigh
    fallback: null
  - agent_id: beta
    role_id: architect
    availability: Paused
    model: "{MODEL_SELECTOR}"
    effort: "N/A"
    fallback: null
"""


def _document() -> dict:
    return {
        "schema_version": 1,
        "default_agents": {"architect": "alpha"},
        "routes": [
            {
                "agent_id": "alpha",
                "role_id": "architect",
                "availability": "Available",
                "model": MODEL_BIG,
                "effort": "max",
                "fallback": {"model": MODEL_SMALL, "effort": "max"},
            },
            {
                "agent_id": "alpha",
                "role_id": "code_reviewer",
                "availability": "Available",
                "model": MODEL_REVIEW,
                "effort": "xhigh",
                "fallback": None,
            },
            {
                "agent_id": "beta",
                "role_id": "architect",
                "availability": "Paused",
                "model": MODEL_SELECTOR,
                "effort": "N/A",
                "fallback": None,
            },
        ],
    }


def _write(tmp_path: Path, text: str = VALID_YAML, name: str = "routing-matrix.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# A. The accepted shape parses exactly
# --------------------------------------------------------------------------- #
def test_a_valid_document_parses_exactly_and_preserves_every_literal():
    raw = VALID_YAML.encode("utf-8")
    matrix = parse_routing_matrix(raw)

    assert matrix.schema_version == ROUTING_MATRIX_SCHEMA_VERSION == 1
    assert dict(matrix.default_agents) == {"architect": "alpha"}
    assert matrix.source_digest == _digest(raw)
    assert len(matrix.routes) == 3

    architect = matrix.route("alpha", "architect")
    assert architect is not None
    assert architect.model == MODEL_BIG
    assert architect.effort == "max"
    assert architect.availability == "Available"
    assert architect.available is True
    assert architect.fallback == RoleRouteFallback(model=MODEL_SMALL, effort="max")

    reviewer = matrix.route("alpha", "code_reviewer")
    assert reviewer is not None
    assert reviewer.model == MODEL_REVIEW
    assert reviewer.effort == "xhigh"
    assert reviewer.fallback is None

    paused = matrix.route("beta", "architect")
    assert paused is not None
    assert paused.available is False
    # The embedded selector and the literal ``N/A`` effort are preserved
    # exactly — no normalization, no trimming, no second spelling.
    assert paused.model == MODEL_SELECTOR
    assert paused.effort == "N/A"

    # Exact identity only: no case folding, no borrowing across the pair.
    assert matrix.route("Alpha", "architect") is None
    assert matrix.route("alpha", "Architect") is None
    assert matrix.route("beta", "code_reviewer") is None
    assert matrix.route(None, "architect") is None


def test_as_dict_round_trips_through_build_with_the_same_digest():
    raw = VALID_YAML.encode("utf-8")
    matrix = parse_routing_matrix(raw)
    document = matrix.as_dict()
    assert document == _document()
    rebuilt = build_routing_matrix(document, source_digest=matrix.source_digest)
    assert rebuilt == matrix


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d.pop("default_agents"), id="missing-default-agents"),
        pytest.param(lambda d: d.pop("routes"), id="missing-routes"),
        pytest.param(lambda d: d.update(extra=1), id="unknown-top-level-key"),
        pytest.param(lambda d: d.update(schema_version=2), id="schema-version-2"),
        pytest.param(lambda d: d.update(schema_version="1"), id="schema-version-text"),
        pytest.param(lambda d: d.update(schema_version=True), id="schema-version-bool"),
        pytest.param(lambda d: d.update(routes=[]), id="no-routes"),
        pytest.param(lambda d: d.update(routes={}), id="routes-not-a-list"),
        pytest.param(lambda d: d.update(default_agents=None), id="default-agents-null"),
        pytest.param(
            lambda d: d.update(default_agents={"architect": "gamma"}),
            id="default-agent-without-a-route",
        ),
        pytest.param(
            lambda d: d.update(default_agents={"Architect": "alpha"}),
            id="default-agent-role-not-a-token",
        ),
        pytest.param(lambda d: d["routes"][0].pop("fallback"), id="missing-fallback"),
        pytest.param(lambda d: d["routes"][0].update(priority=1), id="unknown-route-key"),
        pytest.param(
            lambda d: d["routes"][0].update(availability="available"),
            id="availability-case",
        ),
        pytest.param(
            lambda d: d["routes"][0].update(availability="Retired"),
            id="availability-unknown",
        ),
        pytest.param(lambda d: d["routes"][0].update(model=""), id="model-empty"),
        pytest.param(lambda d: d["routes"][0].update(model="a\nb"), id="model-control-char"),
        pytest.param(lambda d: d["routes"][0].update(model="m" * 513), id="model-too-long"),
        pytest.param(lambda d: d["routes"][0].update(model=5), id="model-not-text"),
        pytest.param(lambda d: d["routes"][0].update(effort="very high"), id="effort-space"),
        pytest.param(lambda d: d["routes"][0].update(effort="n/a"), id="effort-na-lowercase"),
        pytest.param(lambda d: d["routes"][0].update(effort=None), id="effort-null"),
        pytest.param(
            lambda d: d["routes"][0].update(fallback={"model": MODEL_SMALL}),
            id="fallback-missing-effort",
        ),
        pytest.param(
            lambda d: d["routes"][0].update(
                fallback={"model": MODEL_SMALL, "effort": "max", "priority": 1}
            ),
            id="fallback-unknown-key",
        ),
        pytest.param(
            lambda d: d["routes"][0].update(fallback={"model": "", "effort": "max"}),
            id="fallback-model-empty",
        ),
        pytest.param(lambda d: d["routes"][0].update(agent_id="Alpha"), id="agent-id-case"),
        pytest.param(lambda d: d["routes"][0].update(role_id="Architect"), id="role-id-case"),
        pytest.param(
            lambda d: d["routes"].append(dict(d["routes"][0])), id="duplicate-pair"
        ),
        pytest.param(lambda d: d["routes"].append("alpha"), id="route-not-a-mapping"),
    ],
)
def test_every_deviation_from_the_accepted_shape_fails_closed(mutate):
    document = _document()
    mutate(document)
    with pytest.raises(RoutingMatrixError) as excinfo:
        build_routing_matrix(document, source_digest=_digest(b"x"))
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"- just\n- a list\n", id="top-level-list"),
        pytest.param(b"routes: [\n", id="unparseable-yaml"),
        pytest.param(b"\xff\xfe", id="not-utf8"),
        pytest.param(SECRET_CANARY.encode("utf-8"), id="plain-text"),
    ],
)
def test_invalid_bytes_fail_closed_without_echoing_the_material(raw):
    with pytest.raises(RoutingMatrixError) as excinfo:
        parse_routing_matrix(raw)
    rendered = repr(excinfo.value) + str(excinfo.value)
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID
    assert SECRET_CANARY not in rendered
    assert excinfo.value.__cause__ is None


def test_the_stable_codes_are_the_closed_set_the_coordinator_reports():
    assert SACHIMA_ROLE_ROUTING_STABLE_CODES == frozenset(
        {
            SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED,
            SACHIMA_ROLE_ROUTING_MATRIX_INVALID,
            SACHIMA_ROLE_ROUTE_MISSING,
            SACHIMA_ROLE_ROUTE_PAUSED,
        }
    )
    assert all(code.startswith("sachima_role_") for code in SACHIMA_ROLE_ROUTING_STABLE_CODES)


# --------------------------------------------------------------------------- #
# B. Loading: the file bytes are the authority and the digest is theirs
# --------------------------------------------------------------------------- #
def test_loading_reads_the_file_bytes_and_digests_exactly_those_bytes(tmp_path):
    path = _write(tmp_path)
    matrix = load_routing_matrix(str(path))
    assert matrix.source_digest == _digest(path.read_bytes())
    assert matrix.route("alpha", "architect").model == MODEL_BIG

    # A byte-level edit is a different authority, and its digest says so —
    # even when the parsed content is identical.
    path.write_bytes(path.read_bytes() + b"\n# trailing comment\n")
    edited = load_routing_matrix(str(path))
    assert edited.routes == matrix.routes
    assert edited.source_digest != matrix.source_digest


@pytest.mark.parametrize("path", [None, "", "   ", 5])
def test_loading_an_unnamed_path_is_invalid(path):
    with pytest.raises(RoutingMatrixError) as excinfo:
        load_routing_matrix(path)
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID


def test_loading_a_missing_or_unreadable_file_is_invalid_not_empty(tmp_path):
    with pytest.raises(RoutingMatrixError) as excinfo:
        load_routing_matrix(str(tmp_path / "absent.yaml"))
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID
    with pytest.raises(RoutingMatrixError) as excinfo:
        load_routing_matrix(str(tmp_path))  # a directory, not a file
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID


def test_the_source_never_serializes_or_reprs_its_private_path(tmp_path):
    path = _write(tmp_path, name=SECRET_CANARY + ".yaml")
    source = RoleRoutingMatrixSource(str(path))
    assert SECRET_CANARY not in repr(source)
    assert SECRET_CANARY not in str(source)
    assert source.load().route("alpha", "architect").model == MODEL_BIG
    with pytest.raises(RoutingMatrixError):
        RoleRoutingMatrixSource("")


# --------------------------------------------------------------------------- #
# C. Resolution: one stable code per cause, never an AGENT-wide fallback
# --------------------------------------------------------------------------- #
def test_resolution_answers_with_the_route_and_the_digest_it_came_from(tmp_path):
    path = _write(tmp_path)
    source = RoleRoutingMatrixSource(str(path))
    resolution = resolve_role_route(source, "alpha", "code_reviewer")
    assert resolution.resolved is True
    assert resolution.refusal is None
    assert resolution.route.model == MODEL_REVIEW
    assert resolution.route.effort == "xhigh"
    assert resolution.source_digest == _digest(path.read_bytes())


def test_resolution_without_a_configured_source_is_unconfigured():
    resolution = resolve_role_route(None, "alpha", "architect")
    assert resolution.resolved is False
    assert resolution.refusal == SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED
    assert resolution.route is None and resolution.source_digest is None


def test_resolution_over_an_invalid_file_is_invalid(tmp_path):
    path = _write(tmp_path, text="routes: [\n")
    resolution = resolve_role_route(RoleRoutingMatrixSource(str(path)), "alpha", "architect")
    assert resolution.refusal == SACHIMA_ROLE_ROUTING_MATRIX_INVALID
    assert resolution.route is None


@pytest.mark.parametrize(
    ("agent_id", "role_id"),
    [
        ("alpha", "project_manager"),  # no route for the pair
        ("gamma", "architect"),  # AGENT absent from the matrix
        ("alpha", "Architect"),  # not a role token: not a near miss
        ("alpha", "architect "),
        ("alpha", ""),
        ("alpha", None),
        ("Alpha", "architect"),  # not a canonical agent id
    ],
)
def test_resolution_of_an_absent_pair_is_missing_never_borrowed(tmp_path, agent_id, role_id):
    path = _write(tmp_path)
    resolution = resolve_role_route(RoleRoutingMatrixSource(str(path)), agent_id, role_id)
    assert resolution.refusal == SACHIMA_ROLE_ROUTE_MISSING
    assert resolution.route is None


def test_resolution_of_a_paused_route_is_paused_and_carries_no_route(tmp_path):
    path = _write(tmp_path)
    resolution = resolve_role_route(RoleRoutingMatrixSource(str(path)), "beta", "architect")
    assert resolution.refusal == SACHIMA_ROLE_ROUTE_PAUSED
    assert resolution.route is None
    assert resolution.source_digest is None


def test_resolution_re_reads_the_file_on_every_call(tmp_path):
    path = _write(tmp_path)
    source = RoleRoutingMatrixSource(str(path))
    first = resolve_role_route(source, "alpha", "architect")
    assert first.route.model == MODEL_BIG

    path.write_text(VALID_YAML.replace(MODEL_BIG, "model-alpha-next"), encoding="utf-8")
    second = resolve_role_route(source, "alpha", "architect")
    assert second.route.model == "model-alpha-next"
    assert second.source_digest != first.source_digest

    # And the file becoming invalid stops routing on the next call — it does
    # not keep answering from what it last read.
    path.write_text("schema_version: 1\n", encoding="utf-8")
    third = resolve_role_route(source, "alpha", "architect")
    assert third.refusal == SACHIMA_ROLE_ROUTING_MATRIX_INVALID


# --------------------------------------------------------------------------- #
# D. Rendering: the original column order, exact filters
# --------------------------------------------------------------------------- #
HEADER = "| AGENT | Role | Model | Effort | Availability | Fallback Model / Effort |"
DIVIDER = "|---|---|---|---|---|---|"


def test_the_rendered_table_keeps_the_original_column_order():
    matrix = parse_routing_matrix(VALID_YAML.encode("utf-8"))
    lines = render_routing_matrix_table(matrix).splitlines()
    assert lines[0] == HEADER
    assert lines[1] == DIVIDER
    assert lines[2:] == [
        f"| alpha | architect | `{MODEL_BIG}` | `max` | Available | `{MODEL_SMALL} + max` |",
        f"| alpha | code_reviewer | `{MODEL_REVIEW}` | `xhigh` | Available |  |",
        f"| beta | architect | `{MODEL_SELECTOR}` | `N/A` | Paused |  |",
    ]


def test_the_rendered_table_filters_exactly():
    matrix = parse_routing_matrix(VALID_YAML.encode("utf-8"))
    by_agent = render_routing_matrix_table(matrix, agent_id="alpha").splitlines()
    assert len(by_agent) == 4 and all("| alpha |" in row for row in by_agent[2:])
    by_role = render_routing_matrix_table(matrix, role_id="architect").splitlines()
    assert [row.split(" | ")[0] for row in by_role[2:]] == ["| alpha", "| beta"]
    paused = render_routing_matrix_table(matrix, availability="Paused").splitlines()
    assert len(paused) == 3 and "| beta | architect |" in paused[2]
    both = render_routing_matrix_table(
        matrix, agent_id="alpha", role_id="code_reviewer"
    ).splitlines()
    assert len(both) == 3 and MODEL_REVIEW in both[2]
    # A filter that matches nothing renders the header and no rows — it does
    # not widen to "everything" and does not fold case.
    assert render_routing_matrix_table(matrix, agent_id="Alpha").splitlines() == [HEADER, DIVIDER]
    assert render_routing_matrix_table(matrix, role_id="nobody").splitlines() == [HEADER, DIVIDER]


# --------------------------------------------------------------------------- #
# E. The CLI: validate, render, filter — same parsed authority, stable codes
# --------------------------------------------------------------------------- #
def test_the_cli_validates_and_reports_the_digest_and_counts(tmp_path, capsys):
    path = _write(tmp_path)
    assert main(["--file", str(path), "--validate"]) == 0
    out = capsys.readouterr()
    assert "routing_matrix_ok" in out.out
    assert f"digest={_digest(path.read_bytes())}" in out.out
    assert "routes=3" in out.out
    assert "agents=2" in out.out
    assert "roles=2" in out.out
    assert "schema_version=1" in out.out
    assert out.err == ""


def test_the_cli_reports_invalid_material_as_a_stable_code_only(tmp_path, capsys):
    path = _write(tmp_path, text=SECRET_CANARY + ": [\n")
    assert main(["--file", str(path), "--validate"]) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.strip() == SACHIMA_ROLE_ROUTING_MATRIX_INVALID
    assert SECRET_CANARY not in out.err

    assert main(["--file", str(path)]) == 1
    assert capsys.readouterr().err.strip() == SACHIMA_ROLE_ROUTING_MATRIX_INVALID


def test_the_cli_renders_the_table_by_default_and_filters(tmp_path, capsys):
    path = _write(tmp_path)
    assert main(["--file", str(path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == HEADER and len(lines) == 5

    assert main(["--file", str(path), "--agent", "alpha", "--role", "architect"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3 and MODEL_BIG in lines[2]

    assert main(["--file", str(path), "--availability", "Paused"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3 and "| beta |" in lines[2]


def test_the_cli_renders_json_of_the_same_parsed_authority(tmp_path, capsys):
    path = _write(tmp_path)
    assert main(["--file", str(path), "--format", "json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["schema_version"] == 1
    assert document["default_agents"] == {"architect": "alpha"}
    assert document["source_digest"] == _digest(path.read_bytes())
    assert [r["role_id"] for r in document["routes"]] == [
        "architect",
        "code_reviewer",
        "architect",
    ]
    assert main(["--file", str(path), "--format", "json", "--agent", "beta"]) == 0
    filtered = json.loads(capsys.readouterr().out)
    assert [r["agent_id"] for r in filtered["routes"]] == ["beta"]
    assert filtered["routes"][0]["effort"] == "N/A"
    assert filtered["routes"][0]["fallback"] is None


def test_the_cli_reads_the_configured_env_path_only_when_no_file_is_named(
    tmp_path, capsys, monkeypatch
):
    path = _write(tmp_path)
    monkeypatch.delenv(SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV, raising=False)
    assert main(["--validate"]) == 2
    assert capsys.readouterr().err.strip() == SACHIMA_ROLE_ROUTING_MATRIX_UNCONFIGURED

    monkeypatch.setenv(SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV, str(path))
    assert main(["--validate"]) == 0
    assert "routing_matrix_ok" in capsys.readouterr().out

    other = _write(tmp_path, text=VALID_YAML.replace(MODEL_BIG, "model-named"), name="other.yaml")
    assert main(["--file", str(other), "--agent", "alpha", "--role", "architect"]) == 0
    assert "model-named" in capsys.readouterr().out


def test_the_cli_refuses_an_unknown_availability_filter(tmp_path, capsys):
    path = _write(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--file", str(path), "--availability", "Retired"])
    assert excinfo.value.code == 2


# --------------------------------------------------------------------------- #
# F. The composition-root helper: optional, validated once, re-read later
# --------------------------------------------------------------------------- #
def test_the_configured_source_is_optional_validated_once_and_reread_later(tmp_path):
    from gateway.sachima_agent_role_routing_matrix import (
        configured_routing_matrix_source,
    )

    assert configured_routing_matrix_source({}) is None
    assert configured_routing_matrix_source({SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV: "  "}) is None

    path = _write(tmp_path)
    source = configured_routing_matrix_source(
        {SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV: str(path)}
    )
    assert source is not None
    assert source.load().route("alpha", "architect").model == MODEL_BIG

    # Declared-but-invalid raises at composition; an already-composed source
    # re-reads, so the same edit refuses on its next call.
    path.write_text("routes: [\n", encoding="utf-8")
    with pytest.raises(RoutingMatrixError) as excinfo:
        configured_routing_matrix_source({SACHIMA_ROLE_ROUTING_MATRIX_FILE_ENV: str(path)})
    assert str(excinfo.value) == SACHIMA_ROLE_ROUTING_MATRIX_INVALID
    with pytest.raises(RoutingMatrixError):
        source.load()

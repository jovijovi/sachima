"""Tests for dashboard-ready progress event log reads."""

import json
from pathlib import Path

from gateway.progress.reader import (
    get_progress_transaction_events,
    list_progress_transactions,
)


def _write_jsonl(path: Path, records: list[dict | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        if isinstance(record, str):
            lines.append(record)
        else:
            lines.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _operation(tx_id: str, *, written_at: float, event_type: str = "tool.started", status: str = "running", preview: str = "pytest", op_id: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "record_type": "progress.operation",
        "written_at": written_at,
        "transaction": {
            "id": tx_id,
            "title": f"Task {tx_id}",
            "status": "running",
            "started_at": 1.0,
            "updated_at": written_at,
            "completed_at": None,
        },
        "operation": {
            "id": op_id or f"op-{tx_id}-{written_at}",
            "event_type": event_type,
            "tool_name": "terminal",
            "status": status,
            "preview": preview,
            "args_preview": None,
            "started_at": written_at - 0.5,
            "updated_at": written_at,
            "completed_at": written_at if status == "completed" else None,
            "duration": 0.5 if status == "completed" else None,
            "is_error": status == "failed",
            "metadata": {},
        },
    }


def _snapshot(tx_id: str, *, written_at: float, status: str = "completed") -> dict:
    return {
        "schema_version": 1,
        "record_type": "progress.snapshot",
        "written_at": written_at,
        "transaction": {
            "id": tx_id,
            "title": f"Task {tx_id}",
            "status": status,
            "started_at": 1.0,
            "updated_at": written_at,
            "completed_at": written_at if status != "running" else None,
        },
    }


def test_list_progress_transactions_missing_file_returns_empty_without_creating(tmp_path):
    path = tmp_path / "missing" / "events.jsonl"

    result = list_progress_transactions(path)

    assert result == {"transactions": [], "skipped_lines": 0}
    assert not path.exists()


def test_get_progress_transaction_events_missing_file_returns_empty_without_creating(tmp_path):
    path = tmp_path / "missing" / "events.jsonl"

    result = get_progress_transaction_events(path, "tx-missing")

    assert result == {"transaction": None, "events": [], "skipped_lines": 0}
    assert not path.exists()


def test_progress_reader_skips_malformed_jsonl_and_returns_valid_records(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_jsonl(path, [_operation("tx-1", written_at=2.0), "not-json", _snapshot("tx-1", written_at=3.0)])

    result = list_progress_transactions(path)
    detail = get_progress_transaction_events(path, "tx-1")

    assert result["skipped_lines"] == 1
    assert detail["skipped_lines"] == 1
    assert [tx["id"] for tx in result["transactions"]] == ["tx-1"]
    assert [event["record_type"] for event in detail["events"]] == ["progress.operation", "progress.snapshot"]


def test_progress_reader_aggregates_transactions_and_latest_snapshot_wins(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_jsonl(
        path,
        [
            _operation("older", written_at=2.0),
            _operation("tx-1", written_at=3.0, event_type="tool.started", status="running"),
            _operation("tx-1", written_at=4.0, event_type="tool.completed", status="completed", preview="pytest -q"),
            _snapshot("tx-1", written_at=5.0, status="completed"),
            _snapshot("older", written_at=6.0, status="failed"),
        ],
    )

    result = list_progress_transactions(path)
    transactions = result["transactions"]

    assert [tx["id"] for tx in transactions] == ["older", "tx-1"]
    assert transactions[0]["status"] == "failed"
    assert transactions[1]["status"] == "completed"
    assert transactions[1]["operation_count"] == 2
    assert transactions[1]["last_operation"] == {
        "event_type": "tool.completed",
        "tool_name": "terminal",
        "status": "completed",
        "preview": "pytest -q",
        "duration": 0.5,
        "is_error": False,
    }


def test_progress_reader_preserves_sanitized_context_usage_in_summary_and_events(tmp_path):
    path = tmp_path / "events.jsonl"
    snapshot = _snapshot("tx-context", written_at=5.0, status="completed")
    snapshot["transaction"]["context_usage"] = {
        "current_tokens": "40960",
        "context_window": 128000,
        "peak_tokens": 65536,
        "compression_count": 2,
        "threshold_tokens": 102400,
    }
    _write_jsonl(path, [_operation("tx-context", written_at=3.0), snapshot])

    result = list_progress_transactions(path)
    detail = get_progress_transaction_events(path, "tx-context")

    expected = {
        "current_tokens": 40_960,
        "context_window": 128_000,
        "peak_tokens": 65_536,
        "compression_count": 2,
        "threshold_tokens": 102_400,
    }
    assert result["transactions"][0]["context_usage"] == expected
    assert detail["transaction"]["context_usage"] == expected
    assert detail["events"][-1]["transaction"]["context_usage"] == expected


def test_progress_reader_preserves_iteration_usage_in_summary_and_events(tmp_path):
    path = tmp_path / "events.jsonl"
    snapshot = _snapshot("tx-rounds", written_at=5.0, status="completed")
    snapshot["transaction"]["iteration_usage"] = {"current": "12", "maximum": 90}
    _write_jsonl(path, [_operation("tx-rounds", written_at=3.0), snapshot])

    result = list_progress_transactions(path)
    detail = get_progress_transaction_events(path, "tx-rounds")

    expected = {"current": 12, "maximum": 90}
    assert result["transactions"][0]["iteration_usage"] == expected
    assert detail["transaction"]["iteration_usage"] == expected
    assert detail["events"][-1]["transaction"]["iteration_usage"] == expected


def test_progress_reader_omits_iteration_usage_without_meaningful_max(tmp_path):
    path = tmp_path / "events.jsonl"
    snapshot = _snapshot("tx-no-max", written_at=5.0, status="completed")
    snapshot["transaction"]["iteration_usage"] = {"current": 5, "maximum": 0}
    _write_jsonl(path, [snapshot])

    result = list_progress_transactions(path)

    assert result["transactions"][0]["iteration_usage"] is None


def test_progress_reader_old_records_without_iteration_usage_remain_valid(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_jsonl(path, [_operation("tx-legacy", written_at=2.0), _snapshot("tx-legacy", written_at=3.0)])

    result = list_progress_transactions(path)

    assert [tx["id"] for tx in result["transactions"]] == ["tx-legacy"]
    assert result["transactions"][0]["iteration_usage"] is None


def test_progress_reader_reads_across_rotated_files(tmp_path):
    path = tmp_path / "events.jsonl"
    archive = tmp_path / "events.jsonl.1"
    # The older transaction survives only in the rotated archive; the newer one
    # is still in the live file. The reader must aggregate across both.
    _write_jsonl(archive, [_snapshot("older", written_at=1.0, status="completed")])
    _write_jsonl(path, [_snapshot("newer", written_at=5.0, status="running")])

    result = list_progress_transactions(path)
    ids = {tx["id"] for tx in result["transactions"]}

    assert ids == {"older", "newer"}
    # A transaction that lives only in the archive is still independently readable.
    detail = get_progress_transaction_events(path, "older")
    assert detail["transaction"] is not None
    assert detail["transaction"]["id"] == "older"


def test_progress_reader_skips_file_that_disappears_during_rotation(monkeypatch, tmp_path):
    path = tmp_path / "events.jsonl"
    archive = tmp_path / "events.jsonl.1"
    _write_jsonl(path, [_snapshot("live", written_at=5.0, status="running")])
    _write_jsonl(archive, [_snapshot("archive", written_at=1.0, status="completed")])

    from gateway.progress import reader

    real_bounded_lines = reader._bounded_lines

    def flaky_bounded_lines(candidate, *, max_bytes, max_lines):
        if Path(candidate) == path:
            raise FileNotFoundError(str(candidate))
        return real_bounded_lines(candidate, max_bytes=max_bytes, max_lines=max_lines)

    monkeypatch.setattr(reader, "_bounded_lines", flaky_bounded_lines)

    result = list_progress_transactions(path)

    assert result["skipped_lines"] == 0
    assert [tx["id"] for tx in result["transactions"]] == ["archive"]


def test_progress_reader_filters_status_and_applies_limits(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_jsonl(
        path,
        [
            _snapshot("a", written_at=2.0, status="completed"),
            _snapshot("b", written_at=3.0, status="failed"),
            _snapshot("c", written_at=4.0, status="completed"),
        ],
    )

    result = list_progress_transactions(path, status="completed", limit=1)

    assert [tx["id"] for tx in result["transactions"]] == ["c"]


def test_progress_reader_returns_recent_limited_events_in_chronological_order(tmp_path):
    path = tmp_path / "events.jsonl"
    _write_jsonl(path, [_operation("tx-1", written_at=float(i), op_id=f"op-{i}") for i in range(1, 6)])

    result = get_progress_transaction_events(path, "tx-1", limit=3)

    assert [event["operation"]["id"] for event in result["events"]] == ["op-3", "op-4", "op-5"]


def test_progress_reader_bounds_lines_and_handles_weird_scalars(tmp_path):
    path = tmp_path / "events.jsonl"
    records = [_snapshot("old", written_at=1.0)]
    records.append(
        {
            "schema_version": 1,
            "record_type": "progress.snapshot",
            "written_at": "not-a-number",
            "transaction": {
                "id": 123,
                "title": {"password": "reader-secret"},
                "status": True,
                "started_at": "bad",
                "updated_at": "bad",
                "completed_at": "bad",
            },
        }
    )
    _write_jsonl(path, records)

    result = list_progress_transactions(path, max_lines=1)

    assert len(result["transactions"]) == 1
    tx = result["transactions"][0]
    assert tx["id"] == "123"
    assert "reader-secret" not in json.dumps(tx, ensure_ascii=False)
    assert tx["started_at"] is None

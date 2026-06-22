from __future__ import annotations

from .models import TransactionRecord


class InMemoryTransactionStore:
    """Tiny in-memory store for Phase 3 mock orchestration.

    This store is intentionally boring: no files, no network, no database, no
    durable guarantees. Phase 3 validates the contract shape before Temporal.
    """

    def __init__(self) -> None:
        self._records: dict[str, TransactionRecord] = {}

    def put(self, record: TransactionRecord) -> None:
        self._records[record.transaction_id] = record.clone()

    def get(self, transaction_id: str) -> TransactionRecord:
        try:
            return self._records[transaction_id].clone()
        except KeyError as exc:
            raise KeyError(f"unknown transaction_id: {transaction_id}") from exc

    def update(self, record: TransactionRecord) -> None:
        if record.transaction_id not in self._records:
            raise KeyError(f"unknown transaction_id: {record.transaction_id}")
        self._records[record.transaction_id] = record.clone()

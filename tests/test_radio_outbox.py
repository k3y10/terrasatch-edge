from pathlib import Path

import pytest

from terrasatch_edge.radio_outbox import RadioOutbox, RadioOutboxFull, retry_delay_seconds


def test_outbox_persists_source_id_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite3"
    first = RadioOutbox(path, max_items=2)
    assert first.enqueue("source-1", {"source_message_id": "source-1", "text": "hello"})
    assert not first.enqueue("source-1", {"source_message_id": "source-1", "text": "changed"})

    reopened = RadioOutbox(path, max_items=2)
    item = reopened.due(now=10**12)
    assert item is not None
    assert item.source_message_id == "source-1"
    assert item.payload["text"] == "hello"


def test_outbox_failure_retries_then_delivery_removes(tmp_path: Path) -> None:
    outbox = RadioOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("stable-id", {"source_message_id": "stable-id"})
    next_attempt = outbox.failed("stable-id", "offline", now=100)
    assert next_attempt == 110
    assert outbox.due(now=109) is None
    assert outbox.due(now=110).source_message_id == "stable-id"
    outbox.delivered("stable-id")
    assert outbox.depth() == 0


def test_outbox_bound_and_retry_schedule(tmp_path: Path) -> None:
    outbox = RadioOutbox(tmp_path / "outbox.sqlite3", max_items=1)
    outbox.enqueue("one", {"source_message_id": "one"})
    with pytest.raises(RadioOutboxFull):
        outbox.enqueue("two", {"source_message_id": "two"})
    assert [retry_delay_seconds(value) for value in range(1, 6)] == [10, 30, 60, 300, 600]

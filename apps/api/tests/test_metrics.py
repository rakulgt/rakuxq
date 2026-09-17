import json
import sqlite3
from datetime import UTC, datetime, timedelta

from rakuxq_api.domain import Orientation, RecognitionResult, RecognitionStatus, SideToMove
from rakuxq_api.metrics import PublicMetricsStore
from rakuxq_api.metrics_cli import backup


def _result(request_id: str, status: RecognitionStatus) -> RecognitionResult:
    return RecognitionResult(
        request_id=request_id,
        status=status,
        grid=[list(".........") for _ in range(10)],
        piece_placement="9/9/9/9/9/9/9/9/9/9",
        fen="9/9/9/9/9/9/9/9/9/9 w",
        full_fen="9/9/9/9/9/9/9/9/9/9 w - - 0 1",
        side_to_move=SideToMove.RED,
        orientation=Orientation.RED_BOTTOM,
        confidence=0.88,
        warnings=[],
        prediction=None,
    )


def test_public_metrics_keep_lifetime_totals_and_prune_event_details(tmp_path):
    store = PublicMetricsStore(tmp_path / "public.sqlite3", event_hours=72)
    store.initialize()
    now = datetime(2026, 9, 17, 10, tzinfo=UTC)

    assert store.record(
        _result("old", RecognitionStatus.REVIEW_REQUIRED), now - timedelta(hours=73)
    )
    assert store.record(_result("recent", RecognitionStatus.ACCEPTED), now - timedelta(hours=1))
    assert not store.record(_result("recent", RecognitionStatus.ACCEPTED), now)

    snapshot = store.snapshot(now=now)

    assert snapshot["lifetime"]["successful"] == 2
    assert snapshot["lifetime"]["accepted"] == 1
    assert snapshot["recent"]["successful"] == 1
    assert snapshot["recent"]["accepted"] == 1
    assert snapshot["events"] == [
        {
            "occurred_at": "2026-09-17T09:00:00.000Z",
            "status": "accepted",
            "fen": "9/9/9/9/9/9/9/9/9/9 w",
            "confidence": 0.88,
            "duration_ms": 0,
        }
    ]
    serialized = str(snapshot)
    assert "request_id" not in serialized
    assert "source_id" not in serialized
    assert "key_id" not in serialized


def test_public_metrics_ignore_results_without_fen(tmp_path):
    store = PublicMetricsStore(tmp_path / "public.sqlite3")
    store.initialize()
    result = _result("missing", RecognitionStatus.REVIEW_REQUIRED)
    result.fen = None

    assert not store.record(result)
    assert store.snapshot()["lifetime"]["successful"] == 0


def test_public_metrics_import_existing_audit_without_identifiers(tmp_path):
    audit_record = tmp_path / "audit" / "record-1"
    audit_record.mkdir(parents=True)
    (audit_record / "interaction.json").write_text(
        json.dumps(
            {
                "received_at": "2026-09-17T09:00:00Z",
                "duration_ms": 420,
                "response": {
                    "request_id": "rec_private_source",
                    "recognition_status": "accepted",
                    "fen": "4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1",
                    "confidence": 0.91,
                },
            }
        ),
        encoding="utf-8",
    )
    store = PublicMetricsStore(tmp_path / "public.sqlite3")
    store.initialize()

    assert store.import_audit_directory(tmp_path / "audit") == 1
    assert store.import_audit_directory(tmp_path / "audit") == 0
    snapshot = store.snapshot(now=datetime(2026, 9, 17, 10, tzinfo=UTC))
    assert snapshot["events"][0]["fen"] == "4k4/9/9/9/9/9/9/9/9/4K4 w"
    assert "rec_private_source" not in str(snapshot)


def test_public_metrics_backup_is_a_readable_consistent_database(tmp_path):
    database = tmp_path / "public.sqlite3"
    store = PublicMetricsStore(database)
    store.initialize()
    assert store.record(_result("source", RecognitionStatus.ACCEPTED))

    destination = backup(database, tmp_path / "backups", keep_days=30)

    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT successful FROM public_totals").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM public_events").fetchone() == (1,)

from unittest.mock import patch

from fastapi.testclient import TestClient

from rakuxq_api.domain import BoardPrediction, CellPrediction, Orientation
from rakuxq_api.main import app
from rakuxq_api.providers.base import RecognitionProvider
from rakuxq_api.service import RecognitionService

START_GRID = [
    list("rnbakabnr"),
    list("........."),
    list(".c.....c."),
    list("p.p.p.p.p"),
    list("........."),
    list("........."),
    list("P.P.P.P.P"),
    list(".C.....C."),
    list("........."),
    list("RNBAKABNR"),
]


class FixedProvider(RecognitionProvider):
    name = "fixed-api-test"

    def ready(self):
        return True

    def recognize(self, image, orientation):
        cells = [
            CellPrediction(rank, file, symbol, 0.999)
            for rank, row in enumerate(START_GRID)
            for file, symbol in enumerate(row)
        ]
        return BoardPrediction(
            grid=[row.copy() for row in START_GRID],
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=0.999,
            provider=self.name,
            model_version="test",
        )


class PartialProvider(FixedProvider):
    name = "partial-api-test"

    def recognize(self, image, orientation):
        prediction = super().recognize(image, orientation)
        prediction.cells[9] = CellPrediction(
            rank=1,
            file=0,
            symbol=".",
            confidence=0.1,
            visible=False,
            assumed_empty=True,
            raw_symbol="x",
        )
        prediction.board_confidence = 0.4
        return prediction


client = TestClient(app)


def test_public_homepage_and_empty_metrics_are_available_without_api_key():
    homepage = client.get("/")
    metrics = client.get("/api/public/stats")

    assert homepage.status_code == 200
    assert "让现实中的每一个" in homepage.text
    assert "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w" in homepage.text
    assert homepage.text.count('<use href="#star') == 14
    assert metrics.status_code == 200
    assert metrics.json()["recent_window_hours"] == 72
    assert metrics.json()["shortcut_url"] is None


def test_health_reports_not_ready_provider_as_degraded():
    missing_provider = FixedProvider()
    with (
        patch.object(missing_provider, "ready", return_value=False),
        patch("rakuxq_api.main.provider", missing_provider),
    ):
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["provider_ready"] is False
    assert response.json()["status"] == "degraded"


def test_shortcuts_endpoint_returns_plain_fen():
    fake_service = RecognitionService(FixedProvider())
    with patch("rakuxq_api.main.service", fake_service):
        response = client.post(
            "/v1/fen",
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "red"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["x-rakuxq-provider"] == "fixed-api-test"
    assert response.headers["x-rakuxq-model-version"] == "test"
    assert response.headers["x-rakuxq-request-id"].startswith("rec_")
    assert response.text == (
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"
    )


def test_json_endpoint_accepts_url_ready_percent_20w_alias():
    fake_service = RecognitionService(FixedProvider())
    with patch("rakuxq_api.main.service", fake_service):
        response = client.post(
            "/v1/recognitions",
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "%20w"},
        )

    assert response.status_code == 200
    assert response.json()["side_to_move"] == "red"
    assert response.json()["fen"].endswith(" w")
    assert response.json()["full_fen"].endswith(" w - - 0 1")


def test_fen_endpoint_accepts_url_ready_percent_20b_alias():
    fake_service = RecognitionService(FixedProvider())
    with patch("rakuxq_api.main.service", fake_service):
        response = client.post(
            "/v1/fen",
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "%20b"},
        )

    assert response.status_code == 200
    assert response.text.endswith(" b")


def test_shortcuts_endpoint_discloses_assumed_empty_cells():
    fake_service = RecognitionService(PartialProvider())
    with patch("rakuxq_api.main.service", fake_service):
        response = client.post(
            "/v1/fen",
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "red"},
        )

    assert response.status_code == 200
    assert "UNSEEN_CELLS_ASSUMED_EMPTY" in response.headers["x-rakuxq-warnings"]
    assert response.headers["x-rakuxq-assumed-empty-cells"] == "1,0"
    assert response.headers["x-rakuxq-assumed-empty-details"] == "1,0:out_of_frame"


def test_shortcuts_endpoint_requires_side_to_move_for_fen():
    fake_service = RecognitionService(FixedProvider())
    with patch("rakuxq_api.main.service", fake_service):
        response = client.post(
            "/v1/fen",
            files={"image": ("board.png", b"image", "image/png")},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["status"] == "review_required"
    assert "SIDE_TO_MOVE_UNKNOWN" in response.json()["detail"]["warnings"]


def test_upload_rejects_non_image_content_type():
    response = client.post(
        "/v1/fen",
        files={"image": ("board.txt", b"not an image", "text/plain")},
        data={"side_to_move": "red"},
    )

    assert response.status_code == 415

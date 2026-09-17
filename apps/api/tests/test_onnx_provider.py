import numpy as np

from rakuxq_api.providers.onnx import OnnxRecognitionProvider


def _provider() -> OnnxRecognitionProvider:
    return OnnxRecognitionProvider("pose.onnx", "layout.onnx")


def test_portrait_screenshot_uses_single_pose_scale():
    assert _provider()._pose_paddings(width=1280, height=2774) == (1.25,)


def test_regular_photo_keeps_dual_pose_scale_fallback():
    assert _provider()._pose_paddings(width=1600, height=1200) == (1.25, 1.5)


def test_warmup_resolves_symbolic_batch_dimension():
    assert OnnxRecognitionProvider._concrete_shape(["batch", 3, 315, 280]) == (
        1,
        3,
        315,
        280,
    )


def test_grid_visibility_marks_only_centers_outside_the_photo():
    corners = np.array(
        [[-10, 10], [80, 10], [-10, 90], [80, 90]], dtype=np.float32
    )

    _, visible = OnnxRecognitionProvider._visible_grid_mask(corners, 100, 100)

    assert sum(visible) == 80
    assert all(not visible[rank * 9] for rank in range(10))
    assert all(visible[rank * 9 + 1] for rank in range(10))


def test_corners_outside_photo_trigger_pose_fallback():
    corners = np.array(
        [[0, 0], [100, 0], [0, 99], [99, 99]], dtype=np.float32
    )

    assert OnnxRecognitionProvider._corners_extend_outside(corners, 100, 100)


def test_same_image_prototype_refines_only_weak_known_piece():
    import cv2

    warped = np.full((500, 450, 3), 220, dtype=np.uint8)
    symbols = ["."] * 90
    confidences = np.full(90, 0.99, dtype=np.float32)
    visible = [True] * 90

    def mark(index: int, symbol: str, confidence: float, glyph: str):
        rank, file = divmod(index, 9)
        center = (round(50 + file * 43.75), round(50 + rank * (400 / 9)))
        cv2.circle(warped, center, 17, (25, 25, 25), -1)
        cv2.putText(
            warped,
            glyph,
            (center[0] - 10, center[1] + 9),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        symbols[index] = symbol
        confidences[index] = confidence

    mark(10, "r", 0.95, "R")
    mark(20, "b", 0.60, "R")
    mark(30, "p", 0.95, "P")

    refined, effective, details = OnnxRecognitionProvider._same_image_prototype_refinement(
        warped, symbols, confidences, visible
    )

    assert refined[20] == "r"
    assert effective[20] >= 0.72
    assert details[0]["from"] == "b"
    assert details[0]["to"] == "r"


def test_same_image_prototype_never_promotes_unknown_or_empty():
    warped = np.full((500, 450, 3), 220, dtype=np.uint8)
    symbols = ["."] * 90
    symbols[10] = "r"
    symbols[20] = "x"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[20] = 0.2
    visible = [True] * 90

    refined, _, details = OnnxRecognitionProvider._same_image_prototype_refinement(
        warped, symbols, confidences, visible
    )

    assert refined[20] == "x"
    assert details == []

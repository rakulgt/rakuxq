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
    corners = np.array([[0, 0], [100, 0], [0, 99], [99, 99]], dtype=np.float32)

    assert OnnxRecognitionProvider._corners_extend_outside(corners, 100, 100)


def test_geometric_corner_recovery_rotates_without_ever_mirroring():
    tl = np.array([100.0, 100.0], dtype=np.float32)
    tr = np.array([900.0, 110.0], dtype=np.float32)
    bl = np.array([90.0, 1010.0], dtype=np.float32)
    br = np.array([910.0, 1000.0], dtype=np.float32)
    pose_permuted = np.array([bl, tl, br, tr], dtype=np.float32)

    candidates = dict(
        OnnxRecognitionProvider._geometric_rotation_candidates(pose_permuted)
    )

    assert np.allclose(candidates["rotation_0"], [tl, tr, bl, br])
    assert np.allclose(candidates["rotation_180"], [br, bl, tr, tl])
    assert np.allclose(candidates["rotation_90"], [tr, br, tl, bl])
    assert np.allclose(candidates["rotation_270"], [bl, tl, br, tr])
    assert not any(
        np.allclose(candidate, [tr, tl, br, bl])
        for candidate in candidates.values()
    )


def test_geometric_corner_recovery_tries_sideways_rotations_first():
    corners = np.array(
        [[100, 100], [1100, 100], [100, 850], [1100, 850]],
        dtype=np.float32,
    )

    candidates = OnnxRecognitionProvider._geometric_rotation_candidates(corners)

    assert [name for name, _ in candidates[:2]] == ["rotation_90", "rotation_270"]


def test_corner_recovery_penalizes_king_failures_more_than_piece_overflow():
    king_failure = OnnxRecognitionProvider._blocking_warning_penalty(
        ("RED_KING_COUNT",)
    )
    piece_overflow = OnnxRecognitionProvider._blocking_warning_penalty(("TOO_MANY_C",))

    assert king_failure > piece_overflow


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


def test_king_anchor_colours_are_diagnostic_only_and_never_change_raw_symbols():
    import cv2

    warped = np.full((500, 450, 3), (210, 180, 130), dtype=np.uint8)
    symbols = ["."] * 90
    confidences = np.full(90, 0.99, dtype=np.float32)
    visible = [True] * 90

    def mark(index: int, symbol: str, colour: tuple[int, int, int]):
        rank, file = divmod(index, 9)
        center = (round(50 + file * 43.75), round(50 + rank * (400 / 9)))
        cv2.circle(warped, center, 17, colour, -1)
        symbols[index] = symbol

    mark(4, "k", (25, 25, 25))
    mark(85, "K", (220, 25, 25))
    mark(27, "R", (25, 25, 25))
    mark(54, "r", (220, 25, 25))

    original = symbols.copy()
    details = OnnxRecognitionProvider._king_anchor_color_diagnostics(
        warped, symbols, confidences, visible
    )

    assert symbols == original
    assert {(detail["from"], detail["suggested"]) for detail in details} == {
        ("R", "r"),
        ("r", "R"),
    }
    assert all(detail["applied"] is False for detail in details)


def test_king_anchor_diagnostics_do_not_override_real_failure_pattern():
    import cv2

    warped = np.full((500, 450, 3), (210, 180, 130), dtype=np.uint8)
    symbols = ["."] * 90
    confidences = np.full(90, 0.99, dtype=np.float32)
    visible = [True] * 90

    def mark(index: int, symbol: str, confidence: float, colour: tuple[int, int, int]):
        rank, file = divmod(index, 9)
        center = (round(50 + file * 43.75), round(50 + rank * (400 / 9)))
        cv2.circle(warped, center, 17, colour, -1)
        symbols[index] = symbol
        confidences[index] = confidence

    mark(14, "k", 0.90, (25, 25, 25))
    mark(67, "K", 0.95, (220, 25, 25))
    mark(57, "N", 0.9219509, (25, 25, 25))
    mark(59, "p", 0.9194706, (220, 25, 25))
    mark(66, "A", 0.9115211, (25, 25, 25))

    original = symbols.copy()
    details = OnnxRecognitionProvider._king_anchor_color_diagnostics(
        warped, symbols, confidences, visible
    )

    assert symbols == original
    assert symbols[57] == "N"
    assert symbols[59] == "p"
    assert symbols[66] == "A"
    assert {(detail["from"], detail["suggested"]) for detail in details} == {
        ("N", "n"),
        ("p", "P"),
        ("A", "a"),
    }
    assert all(detail["raw_confidence"] > 0.91 for detail in details)


def test_king_anchor_colours_do_nothing_when_anchor_colours_are_indistinguishable():
    import cv2

    warped = np.full((500, 450, 3), (210, 180, 130), dtype=np.uint8)
    symbols = ["."] * 90
    confidences = np.full(90, 0.99, dtype=np.float32)
    visible = [True] * 90
    for index, symbol in ((4, "k"), (85, "K"), (27, "R")):
        rank, file = divmod(index, 9)
        center = (round(50 + file * 43.75), round(50 + rank * (400 / 9)))
        cv2.circle(warped, center, 17, (80, 80, 80), -1)
        symbols[index] = symbol

    details = OnnxRecognitionProvider._king_anchor_color_diagnostics(
        warped, symbols, confidences, visible
    )

    assert details == []

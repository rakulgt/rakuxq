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
    assert details[0]["method"] == "same_image_prototype_correction"


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


def test_visual_fusion_confirms_low_confidence_piece_from_type_and_camp():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[56] = "C"
    model_confidences = np.full(90, 0.99, dtype=np.float32)
    model_confidences[56] = 0.5296
    visible = [True] * 90
    type_evidence = [
        {
            "rank": 6,
            "file": 2,
            "best_type": "c",
            "similarity": 0.7009,
            "type_margin": 0.2555,
            "prototype_symbol": "c",
            "prototype_rank": 2,
            "prototype_file": 1,
        }
    ]
    color_evidence = [
        {
            "rank": 6,
            "file": 2,
            "suggested": "C",
            "red_distance": 0.2798,
            "black_distance": 0.6216,
            "assignment_margin": 0.3418,
            "anchor_distance": 0.6371,
        }
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            model_confidences,
            np.zeros(90, dtype=np.float32),
            model_confidences,
            visible,
            type_evidence,
            color_evidence,
        )
    )

    assert refined[56] == "C"
    assert effective[56] >= 0.75
    assert details[0]["method"] == "same_image_prototype_confirmation"
    assert details[0]["from"] == details[0]["to"] == "C"


def test_visual_fusion_corrects_only_low_confidence_camp_when_legality_improves():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[19] = "c"
    symbols[22] = "c"
    symbols[56] = "c"
    model_confidences = np.full(90, 0.99, dtype=np.float32)
    model_confidences[56] = 0.5339
    visible = [True] * 90
    type_evidence = [
        {
            "rank": 6,
            "file": 2,
            "best_type": "c",
            "similarity": 0.9235,
            "type_margin": 0.4497,
            "prototype_symbol": "C",
            "prototype_rank": 2,
            "prototype_file": 4,
        }
    ]
    color_evidence = [
        {
            "rank": 6,
            "file": 2,
            "suggested": "C",
            "red_distance": 0.2881,
            "black_distance": 0.6272,
            "assignment_margin": 0.3391,
            "anchor_distance": 0.6370,
        }
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            model_confidences,
            np.zeros(90, dtype=np.float32),
            model_confidences,
            visible,
            type_evidence,
            color_evidence,
        )
    )

    assert refined[56] == "C"
    assert effective[56] >= 0.75
    assert details[0]["method"] == "same_image_prototype_camp_correction"
    assert "TOO_MANY_c" in details[0]["blocking_warnings_before"]
    assert "TOO_MANY_c" not in details[0]["blocking_warnings_after"]


def test_visual_fusion_never_overrides_high_confidence_piece():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[56] = "C"
    confidences = np.full(90, 0.99, dtype=np.float32)
    visible = [True] * 90
    type_evidence = [
        {
            "rank": 6,
            "file": 2,
            "best_type": "c",
            "similarity": 0.99,
            "type_margin": 0.90,
            "prototype_symbol": "c",
            "prototype_rank": 2,
            "prototype_file": 1,
        }
    ]
    color_evidence = [
        {
            "rank": 6,
            "file": 2,
            "suggested": "c",
            "red_distance": 0.60,
            "black_distance": 0.10,
            "assignment_margin": 0.50,
            "anchor_distance": 0.60,
        }
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            confidences,
            np.zeros(90, dtype=np.float32),
            confidences,
            visible,
            type_evidence,
            color_evidence,
        )
    )

    assert refined[56] == "C"
    assert effective[56] == confidences[56]
    assert details == []


def test_visual_fusion_rejects_camp_change_that_does_not_improve_legality():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[56] = "C"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[56] = 0.55
    visible = [True] * 90
    type_evidence = [
        {
            "rank": 6,
            "file": 2,
            "best_type": "c",
            "similarity": 0.90,
            "type_margin": 0.30,
            "prototype_symbol": "c",
            "prototype_rank": 2,
            "prototype_file": 1,
        }
    ]
    color_evidence = [
        {
            "rank": 6,
            "file": 2,
            "suggested": "c",
            "red_distance": 0.60,
            "black_distance": 0.10,
            "assignment_margin": 0.50,
            "anchor_distance": 0.60,
        }
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            confidences,
            np.zeros(90, dtype=np.float32),
            confidences,
            visible,
            type_evidence,
            color_evidence,
        )
    )

    assert refined[56] == "C"
    assert effective[56] == confidences[56]
    assert details == []


def test_visual_fusion_confirms_only_weak_piece_from_decisive_margin_and_camp():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[38] = "p"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[38] = 0.5379
    model_margins = np.zeros(90, dtype=np.float32)
    model_margins[38] = 0.1614
    visible = [True] * 90
    color_evidence = [
        {
            "rank": 4,
            "file": 2,
            "suggested": "p",
            "red_distance": 0.680,
            "black_distance": 0.372,
            "assignment_margin": 0.308,
            "anchor_distance": 0.676,
        }
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            confidences,
            model_margins,
            confidences,
            visible,
            [],
            color_evidence,
        )
    )

    assert refined[38] == "p"
    assert effective[38] >= 0.75
    assert details[0]["method"] == "model_margin_camp_confirmation"


def test_visual_fusion_rejects_decisive_margin_when_two_pieces_are_weak():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    symbols[38] = "p"
    symbols[39] = "p"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[38] = 0.60
    confidences[39] = 0.60
    model_margins = np.zeros(90, dtype=np.float32)
    model_margins[38] = 0.30
    model_margins[39] = 0.30
    visible = [True] * 90
    color_evidence = [
        {
            "rank": 4,
            "file": 2,
            "suggested": "p",
            "red_distance": 0.70,
            "black_distance": 0.20,
            "assignment_margin": 0.50,
            "anchor_distance": 0.60,
        },
        {
            "rank": 4,
            "file": 3,
            "suggested": "p",
            "red_distance": 0.70,
            "black_distance": 0.20,
            "assignment_margin": 0.50,
            "anchor_distance": 0.60,
        },
    ]

    refined, effective, details = (
        OnnxRecognitionProvider._apply_low_confidence_visual_fusion(
            symbols,
            confidences,
            model_margins,
            confidences,
            visible,
            [],
            color_evidence,
        )
    )

    assert refined == symbols
    assert np.array_equal(effective, confidences)
    assert details == []


def test_decisive_empty_confirmation_accepts_single_clear_borderline_empty():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[41] = 0.7350
    margins = np.zeros(90, dtype=np.float32)
    margins[41] = 0.6332
    visible = [True] * 90

    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols,
        confidences,
        margins,
        confidences,
        visible,
    )

    assert effective[41] >= 0.75
    assert details[0]["method"] == "model_margin_empty_confirmation"


def test_decisive_empty_confirmation_rejects_unknown_or_multiple_weak_cells():
    symbols = ["."] * 90
    symbols[4] = "k"
    symbols[84] = "K"
    confidences = np.full(90, 0.99, dtype=np.float32)
    confidences[41] = 0.70
    margins = np.zeros(90, dtype=np.float32)
    margins[41] = 0.60
    visible = [True] * 90

    symbols[10] = "x"
    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols,
        confidences,
        margins,
        confidences,
        visible,
    )
    assert effective[41] == confidences[41]
    assert details == []

    symbols[10] = "."
    confidences[42] = 0.70
    margins[42] = 0.60
    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols,
        confidences,
        margins,
        confidences,
        visible,
    )
    assert effective[41] == confidences[41]
    assert effective[42] == confidences[42]
    assert details == []

from unittest.mock import patch

import cv2
import numpy as np
import pytest

from rakuxq_api.providers.occupancy import LocalOccupancyProbe
from rakuxq_api.providers.onnx import OnnxRecognitionProvider


def _board(target_piece=False, central_cursor=True, low_contrast=False):
    image = np.full((500, 450, 3), (61, 28, 43), dtype=np.uint8)
    symbols = ["."] * 90
    confidences = np.full(90, .99, dtype=np.float32)
    for rank in range(10):
        y = round(50 + rank*400/9)
        cv2.line(image, (50, y), (400, y), (182, 155, 92), 2)
    for file in range(9):
        x = round(50 + file*43.75)
        cv2.line(image, (x, 50), (x, 450), (182, 155, 92), 2)

    def piece(index):
        rank, file = divmod(index, 9)
        center = (round(50 + file*43.75), round(50 + rank*400/9))
        if not low_contrast:
            cv2.circle(image, center, 19, (95, 65, 30), -1)
            cv2.circle(image, center, 16, (225, 192, 105), -1)
        cv2.putText(image, '+', (center[0]-6, center[1]+5), cv2.FONT_HERSHEY_SIMPLEX,
                    .5, (0, 0, 0), 2)

    for index, symbol in [(4, 'k'), (84, 'K'), (63, 'R'), (59, 'P')]:
        symbols[index] = symbol
        piece(index)
    target = (round(50 + 7*43.75), 450)
    if target_piece:
        piece(88)  # Raw layout says '.', but the image really contains a piece.
    elif central_cursor:
        cv2.circle(image, target, 6, (255, 255, 255), 2)
        cv2.circle(image, target, 2, (255, 255, 255), -1)
    confidences[88] = .52
    return image, symbols, confidences


@pytest.mark.parametrize('central_cursor', [False, True])
def test_occupancy_confirms_background_with_or_without_small_cursor(central_cursor):
    image, symbols, confidences = _board(central_cursor=central_cursor)
    probe = LocalOccupancyProbe(image, symbols, confidences, [True]*90)
    assert probe._hsv is None  # No preprocessing until the weak-cell path calls it.
    evidence = probe.check_empty(88)
    assert evidence['confirmed_empty'] is True
    assert evidence['vote'] == 'empty'
    assert evidence['piece_control_errors'] == 0
    assert evidence['distance_margin'] >= .15
    assert evidence['centre_exclusion_radius'] == 9


def test_occupancy_vetoes_an_actual_piece_even_if_layout_calls_it_empty():
    image, symbols, confidences = _board(target_piece=True)
    evidence = LocalOccupancyProbe(image, symbols, confidences, [True]*90).check_empty(88)
    assert evidence['confirmed_empty'] is False
    assert evidence['vote'] == 'occupied'
    margins = np.zeros(90, dtype=np.float32)
    margins[88] = .39
    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols, confidences, margins, confidences, [True]*90,
        occupancy_probe=LocalOccupancyProbe(image, symbols, confidences, [True]*90),
    )
    assert np.array_equal(effective, confidences)
    assert details[0]['applied'] is False
    assert details[0]['occupancy']['vote'] == 'occupied'


def test_occupancy_abstains_when_known_pieces_are_not_distinguishable_from_board():
    image, symbols, confidences = _board(low_contrast=True)
    evidence = LocalOccupancyProbe(image, symbols, confidences, [True]*90).check_empty(88)
    assert evidence['confirmed_empty'] is False
    assert evidence['vote'] == 'uncertain'
    assert evidence['reason'] == 'piece_and_board_appearance_not_separable'


@pytest.mark.parametrize('case', ['no_empty_references', 'one_piece', 'partial', 'known_piece'])
def test_occupancy_abstains_without_sufficient_reliable_evidence(case):
    image, symbols, confidences = _board()
    visible = [True]*90
    if case == 'no_empty_references':
        confidences[:] = .79
    elif case == 'one_piece':
        confidences[59] = confidences[63] = confidences[84] = .89
    elif case == 'partial':
        visible[0] = False
    elif case == 'known_piece':
        symbols[88] = 'r'
    probe = LocalOccupancyProbe(image, symbols, confidences, visible)
    evidence = probe.check_empty(88)
    assert evidence['confirmed_empty'] is False
    assert probe._hsv is None


def test_occupancy_is_additional_evidence_not_a_bypass_of_model_or_legality_gates():
    image, symbols, confidences = _board()
    margins = np.zeros(90, dtype=np.float32)
    margins[88] = .39
    before = confidences.copy()
    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols, confidences, margins, confidences, [True]*90,
        occupancy_probe=LocalOccupancyProbe(image, symbols, confidences, [True]*90),
    )
    assert effective[88] == .75
    assert details[0]['occupancy']['confirmed_empty'] is True
    assert np.array_equal(confidences, before)
    assert symbols[88] == '.'
    with patch.object(LocalOccupancyProbe, 'check_empty') as check:
        confidences[88] = .99  # Normal image: no occupancy work or extra layout inference.
        OnnxRecognitionProvider._apply_decisive_empty_confirmation(
            symbols, confidences, margins, confidences, [True]*90,
            occupancy_probe=LocalOccupancyProbe(image, symbols, confidences, [True]*90),
        )
    check.assert_not_called()


def test_dominant_empty_score_alone_no_longer_confirms_without_visual_probe():
    _, symbols, confidences = _board()
    margins = np.zeros(90, dtype=np.float32)
    margins[88] = .39
    effective, details = OnnxRecognitionProvider._apply_decisive_empty_confirmation(
        symbols, confidences, margins, confidences, [True]*90,
    )
    assert np.array_equal(effective, confidences)
    assert details == []

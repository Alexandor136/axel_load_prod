"""Чтение кейса нового формата: колонки, рамка кузова, объём."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from axle_load.case import is_case_dir, read_case
from axle_load.errors import InputDataError, MissingInputError

from helpers import (
    BODY_LENGTH_M,
    BODY_WIDTH_M,
    make_case,
    write_ascii_ply,
)


def test_is_case_dir(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    assert is_case_dir(case.path)
    assert not is_case_dir(tmp_path)


def test_synthetic_case(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    data = read_case(case.path)

    assert data.columns == case.columns
    assert data.height_map.n_raw == case.columns
    assert data.frame.rear_y_m == pytest.approx(BODY_LENGTH_M)
    assert data.frame.width_m == pytest.approx(BODY_WIDTH_M)
    # Сетка вокселей отсчитывается от нуля: origin = −1 м по всем осям.
    assert data.frame.origin_m == (-1.0, -1.0, -1.0)
    assert data.height_map.dx == pytest.approx(0.04)
    assert data.height_map.dy == pytest.approx(0.04)
    assert data.volume_m3 == pytest.approx(case.volume_m3, rel=1e-9)
    np.testing.assert_allclose(
        np.sort(data.height_map.h), case.heights_m, atol=1e-12
    )
    # Кузов в ТЗ: X отсчитывается от заднего борта.
    assert data.body_points[:, 0].min() == pytest.approx(0.0, abs=1e-9)
    assert data.body_points[:, 0].max() == pytest.approx(BODY_LENGTH_M, abs=1e-9)


def test_missing_file(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    (case.path / "4_B2M" / "result_b2m.ply").unlink()
    with pytest.raises(MissingInputError):
        read_case(case.path)


def test_body_without_red_points(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    points = np.array([[0.0, 0.0, 2.6], [5.0, 9.0, 5.6]])
    colors = np.tile(np.array((0, 255, 0), dtype=np.uint8), (2, 1))
    write_ascii_ply(case.path / "4_B2M" / "result_b2m.ply", points, colors)
    with pytest.raises(InputDataError, match="красных"):
        read_case(case.path)


def test_columns_outside_body(tmp_path: Path) -> None:
    """Воксели вне bbox кузова ловятся проверкой origin."""
    case = make_case(tmp_path)
    # Индекс 400 по X → 15 м, далеко за пределами 5.883 м.
    write_ascii_ply(
        case.path / "5_LoadEstimation" / "0_entire_mass.ply",
        np.array([[400.0, 100.0, 92.0], [400.0, 100.0, 100.0]]),
    )
    with pytest.raises(InputDataError, match="bbox"):
        read_case(case.path)


def _real_case_dir() -> Path | None:
    repo = Path(__file__).resolve().parents[2]
    for body in (repo / "data_new").rglob("4_B2M"):
        candidate = body.parent
        if is_case_dir(candidate):
            return candidate
    return None


@pytest.mark.skipif(_real_case_dir() is None, reason="нет data_new с кейсом")
def test_real_case_volume() -> None:
    case_dir = _real_case_dir()
    assert case_dir is not None
    data = read_case(case_dir)
    assert data.columns == 6998
    # case.log: 14.464 м³; inclusive-формула дала бы 14.871.
    assert data.volume_m3 == pytest.approx(14.423, abs=0.05)
    # Рамка кузова — bbox красных точек, а не округлённые числа из ТЗ.
    assert data.frame.rear_y_m == pytest.approx(9.629, abs=1e-3)
    assert data.frame.width_m == pytest.approx(5.883, abs=1e-3)
    assert data.frame.origin_m == (-1.0, -1.0, -1.0)

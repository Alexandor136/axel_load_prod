"""PLY: чтение ASCII (новый формат) и binary (round-trip записи)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from axle_load.jsonio import read_ply, write_ply

from helpers import write_ascii_ply

POINTS = np.array([[0.0, 0.0, 2.5], [1.5, 9.5, 5.5], [5.8, 0.1, 2.7]])
COLORS = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)


def test_read_ascii_with_colors(tmp_path: Path) -> None:
    path = write_ascii_ply(tmp_path / "a.ply", POINTS, COLORS)
    cloud = read_ply(path)

    assert cloud.points.shape == (3, 3)
    np.testing.assert_allclose(cloud.points, POINTS)
    assert cloud.colors is not None
    np.testing.assert_array_equal(cloud.colors, COLORS)
    np.testing.assert_array_equal(cloud.select_color((255, 0, 0)), [True, False, False])


def test_read_ascii_without_colors(tmp_path: Path) -> None:
    path = write_ascii_ply(tmp_path / "a.ply", POINTS)
    cloud = read_ply(path)
    np.testing.assert_allclose(cloud.points, POINTS)
    assert cloud.colors is None


def test_binary_roundtrip(tmp_path: Path) -> None:
    path = write_ply(tmp_path / "b.ply", POINTS, COLORS)
    cloud = read_ply(path)
    np.testing.assert_allclose(cloud.points, POINTS)
    assert cloud.colors is not None
    np.testing.assert_array_equal(cloud.colors, COLORS)


def test_ascii_bad_column_count(tmp_path: Path) -> None:
    path = tmp_path / "bad.ply"
    path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\n"
        "property float y\nproperty float z\nend_header\n1 2\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="колонок"):
        read_ply(path)

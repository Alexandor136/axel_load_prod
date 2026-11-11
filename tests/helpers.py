"""Синтетический кейс нового формата для тестов."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Габариты кузова как у реального кейса: x — поперёк, y — вдоль.
BODY_WIDTH_M = 5.883
BODY_LENGTH_M = 9.629
BODY_Z_MIN = 2.6
BODY_Z_MAX = 5.637

# Колонки груза в индексах вокселей (0.04 м, origin −1 м).
IX = np.arange(30, 71, 2)
IY = np.arange(100, 161, 2)
ZMIN = 92
# Высота колонки в вокселях: 10..30, зависит от (ix, iy) — чтобы карта не была плоской.
HEIGHTS_IDX = (
    (IX[:, None] - IX.min()) + (IY[None, :] - IY.min())
) % 21 + 10


def write_ascii_ply(
    path: Path,
    points: np.ndarray,
    colors: np.ndarray | None = None,
) -> Path:
    """Пишет ASCII PLY (format ascii 1.0) с опциональным RGB."""
    points = np.asarray(points, dtype=np.float64)
    header = [
        "ply",
        "format ascii 1.0",
        f"element vertex {points.shape[0]}",
        "property float x",
        "property float y",
        "property float z",
    ]
    if colors is not None:
        header += [
            "property uchar red",
            "property uchar green",
            "property uchar blue",
        ]
    header.append("end_header")

    rows: list[str] = []
    for i in range(points.shape[0]):
        row = f"{points[i, 0]:.9f} {points[i, 1]:.9f} {points[i, 2]:.9f}"
        if colors is not None:
            red, green, blue = (int(c) for c in colors[i])
            row += f" {red} {green} {blue}"
        rows.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([*header, *rows]) + "\n", encoding="ascii")
    return path


def body_points() -> np.ndarray:
    """Красные точки модели кузова: рёбра bbox, чтобы bbox был точным."""
    xs = (0.0, BODY_WIDTH_M)
    ys = (0.0, BODY_LENGTH_M)
    zs = (BODY_Z_MIN, BODY_Z_MAX)
    return np.array(
        [(x, y, z) for x in xs for y in ys for z in zs], dtype=np.float64
    )


def mass_points() -> np.ndarray:
    """Сплошной объём груза: в каждой колонке воксели от ZMIN до ZMIN + h."""
    xs, ys = np.meshgrid(IX, IY, indexing="ij")
    rows: list[tuple[float, float, float]] = []
    for ix, iy, height in zip(
        xs.ravel(), ys.ravel(), HEIGHTS_IDX.ravel(), strict=True
    ):
        for z in range(ZMIN, ZMIN + int(height) + 1):
            rows.append((float(ix), float(iy), float(z)))
    return np.asarray(rows, dtype=np.float64)


@dataclass(frozen=True)
class SyntheticCase:
    """Каталог кейса и ожидаемые числа."""

    path: Path
    columns: int
    volume_m3: float
    heights_m: np.ndarray


def make_case(root: Path) -> SyntheticCase:
    """Создаёт кейс: ``4_B2M/result_b2m.ply`` + ``5_LoadEstimation/0_entire_mass.ply``."""
    case = root / "case"
    red = body_points()
    red_rgb = np.tile(np.array((255, 0, 0), dtype=np.uint8), (red.shape[0], 1))
    # Зелёные точки скана: bbox не меняют, но проверяют фильтр по цвету.
    green = red + np.array((0.0, 0.0, 0.5))
    green_rgb = np.tile(np.array((0, 255, 0), dtype=np.uint8), (green.shape[0], 1))
    write_ascii_ply(
        case / "4_B2M" / "result_b2m.ply",
        np.vstack([red, green]),
        np.vstack([red_rgb, green_rgb]),
    )
    write_ascii_ply(case / "5_LoadEstimation" / "0_entire_mass.ply", mass_points())

    heights = (HEIGHTS_IDX.astype(np.float64) * 0.04).ravel()
    volume = float(heights.sum() * 0.04 * 0.04)
    return SyntheticCase(
        path=case,
        columns=int(IX.size * IY.size),
        volume_m3=volume,
        heights_m=np.sort(heights),
    )

"""Чтение кейса нового формата: ``0_entire_mass.ply`` + ``result_b2m.ply``.

Файлы пайплайна:

* ``5_LoadEstimation/0_entire_mass.ply`` — сплошной объём груза, координаты
  в ИНДЕКСАХ вокселей 0.04 м. В каждой колонке (ix, iy) много вокселей:
  ``zmin`` — днище, ``zmax`` — верх груза.
* ``4_B2M/result_b2m.ply`` — выровненная сцена в метрах модели: красные точки
  ``(255, 0, 0)`` — модель кузова, зелёные ``(0, 255, 0)`` — скан.

Старый формат (``DataProcessing`` + ``Postprocessing/log.json``) не
поддерживается.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .clouds import body_outline_from_cloud, build_height_map_from_columns
from .errors import InputDataError, MissingInputError
from .jsonio import read_ply
from .schemas import VOXEL_INDENTS_M, BodyFrame, BodyOutline, Columns, HeightMap

ENTIRE_MASS_REL = Path("5_LoadEstimation") / "0_entire_mass.ply"
BODY_MODEL_REL = Path("4_B2M") / "result_b2m.ply"
BODY_RGB = (255, 0, 0)


@dataclass(frozen=True)
class CaseData:
    """Всё, что нужно для расчёта и отрисовки одного кейса."""

    height_map: HeightMap
    outline: BodyOutline
    frame: BodyFrame
    body_points: np.ndarray  # (N, 3) в метрах ТЗ
    volume_m3: float
    columns: int


def case_files(case_dir: str | Path) -> tuple[Path, Path]:
    """Пути к двум обязательным файлам кейса."""
    case_dir = Path(case_dir)
    return case_dir / ENTIRE_MASS_REL, case_dir / BODY_MODEL_REL


def is_case_dir(case_dir: str | Path) -> bool:
    """True, если каталог похож на кейс нового формата."""
    mass, body = case_files(case_dir)
    return mass.is_file() and body.is_file()


def _read_columns(path: Path) -> Columns:
    """Склеивает воксели в колонки (ix, iy): zmin — днище, zmax — верх."""
    cloud = read_ply(path)
    if cloud.points.size == 0:
        raise InputDataError(f"{path}: облако пустое")

    points = cloud.points
    xy = points[:, :2]
    keys = np.rint(xy).astype(np.int64)
    # Координаты обязаны быть индексами вокселей, иначе перевод в метры врёт.
    if not np.allclose(xy, keys, atol=1e-3):
        raise InputDataError(
            f"{path}: координаты X/Y должны быть индексами вокселей, "
            f"а не метрами"
        )
    if not np.all(np.isfinite(points[:, 2])):
        raise InputDataError(f"{path}: в Z есть NaN или inf")

    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    zmin = np.full(uniq.shape[0], np.inf)
    zmax = np.full(uniq.shape[0], -np.inf)
    np.minimum.at(zmin, inverse, points[:, 2])
    np.maximum.at(zmax, inverse, points[:, 2])

    # Детерминированный порядок колонок: сначала ix, затем iy.
    order = np.lexsort((uniq[:, 1], uniq[:, 0]))
    uniq = uniq[order]
    zmin = zmin[order]
    zmax = zmax[order]

    return Columns(
        top_xy=uniq,
        top_z=zmax,
        floor_xy=uniq,
        floor_z=zmin,
        approx_source=f"{path.name} ({uniq.shape[0]} колонок)",
    )


def _check_inside_body(columns: Columns, frame: BodyFrame, path: Path) -> None:
    """Колонки груза должны лежать внутри bbox кузова (ловит неверный origin)."""
    centers = frame.centers(np.asarray(columns.top_xy, dtype=np.float64))
    x, y = centers[:, 0], centers[:, 1]
    tol = frame.voxel_size_m
    inside = (
        (x >= -tol)
        & (x <= frame.width_m + tol)
        & (y >= -tol)
        & (y <= frame.rear_y_m + tol)
    )
    if not np.all(inside):
        raise InputDataError(
            f"{path}: колонки груза выходят за bbox кузова — "
            f"проверьте origin воксельной сетки"
        )


def read_case(
    case_dir: str | Path,
    *,
    cell_size_m: float = 0.04,
    y_sign: float = 1.0,
    validate: bool = True,
) -> CaseData:
    """Читает кейс и строит карту высот и контур кузова.

    Args:
        case_dir: каталог с ``5_LoadEstimation`` и ``4_B2M``.
        cell_size_m: размер вокселя, м (в новом пайплайне 0.04).
        y_sign: +1 — Y > 0 справа по ходу, -1 — зеркально.
        validate: проверять непустоту и положительный объём.

    Returns:
        ``CaseData`` с картой высот, контуром и рамкой кузова.

    Raises:
        MissingInputError: нет одного из двух файлов кейса.
        InputDataError: файл пуст, нет красных точек кузова или объём ≤ 0.
    """
    case_dir = Path(case_dir)
    mass_path, body_path = case_files(case_dir)
    missing = [str(p) for p in (mass_path, body_path) if not p.is_file()]
    if missing:
        raise MissingInputError(
            f"{case_dir}: нет файлов кейса: " + ", ".join(missing)
        )

    # Кузов: красные точки модели, bbox задаёт рамку и origin воксельной сетки.
    body = read_ply(body_path)
    if body.colors is None:
        raise InputDataError(f"{body_path}: нет цвета (нужны красные точки кузова)")
    red = body.points[body.select_color(BODY_RGB)]
    if red.shape[0] == 0:
        raise InputDataError(f"{body_path}: нет красных точек модели кузова")

    bbox_max = red.max(axis=0)
    # Сетка вокселей в этом пайплайне отсчитывается от нуля, а не от bbox
    # модели: origin = −1 м по всем осям. Проверено по скану: при origin_z=-1
    # верх колонок совпадает с зелёными точками у 99.8% колонок (median −0.04 м),
    # при origin_z = bbox_min-1 расхождение 2.6 м.
    frame = BodyFrame(
        rear_y_m=float(bbox_max[1]),
        width_m=float(bbox_max[0]),
        y_sign=y_sign,
        voxel_size_m=cell_size_m,
        origin_m=tuple(-float(v) for v in VOXEL_INDENTS_M),
    )

    # Кузов в координатах ТЗ → три проекции для отрисовки.
    x_spec, y_spec = frame.to_spec(red[:, 0], red[:, 1])
    body_points = np.column_stack([x_spec, y_spec, red[:, 2]])
    outline = body_outline_from_cloud(body_points)
    if outline is None:
        raise InputDataError(f"{body_path}: не удалось построить контур кузова")

    # Груз: сплошной объём → колонки → карта высот в метрах ТЗ.
    columns = _read_columns(mass_path)
    _check_inside_body(columns, frame, mass_path)
    height_map = build_height_map_from_columns(columns, frame)
    volume = float(np.sum(height_map.h) * height_map.dx * height_map.dy)
    if validate and (height_map.h.size == 0 or volume <= 0.0):
        raise InputDataError(f"{mass_path}: нулевой объём груза")

    return CaseData(
        height_map=height_map,
        outline=outline,
        frame=frame,
        body_points=body_points,
        volume_m3=volume,
        columns=int(height_map.h.size),
    )

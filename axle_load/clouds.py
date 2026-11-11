"""Построение карты высот и контура кузова из колонок вокселей."""

from __future__ import annotations

import numpy as np

from .schemas import BodyFrame, BodyOutline, Columns, HeightMap

BIN_M = 0.10


def _envelope(
    coord: np.ndarray, value: np.ndarray, bin_m: float, mode: str
) -> tuple[np.ndarray, np.ndarray]:
    """Бинирует точки и строит верхнюю (max) или нижнюю (min) огибающую.

    coord — координата бинирования (X или Y в ТЗ);
    value — измеряемая величина (Z или Y);
    возвращает (центры бинов, огибающая).
    """
    # Индекс бина: floor(coord / bin_m), уникальные бины + обратное отображение.
    bins = np.floor(coord / bin_m).astype(np.int64)
    uniq, inverse = np.unique(bins, return_inverse=True)
    # Начальное значение: −inf для max, +inf для min (нейтраль агрегации).
    out = np.full(uniq.size, -np.inf if mode == "max" else np.inf)
    # Строчный (at) агрегат: max/min внутри каждого бина без сортировки.
    if mode == "max":
        np.maximum.at(out, inverse, value)
    else:
        np.minimum.at(out, inverse, value)
    # Центр бина = (индекс + 0.5) * bin_m — перевод обратно в метры.
    return (uniq + 0.5) * bin_m, out


def body_outline_from_cloud(
    points: np.ndarray | None,
    bin_m: float = BIN_M,
) -> BodyOutline | None:
    """Строит три проекции кузова по облаку в координатах ТЗ."""
    if points is None or len(points) == 0:
        return None
    pts = np.asarray(points, dtype=np.float64)
    x_spec, y_spec, z = pts[:, 0], pts[:, 1], pts[:, 2]
    # Три проекции: сбоку (X→Z), поперёк (Y→Z), сверху (X→Y).
    side_x, z_top = _envelope(x_spec, z, bin_m, "max")
    _, z_bot = _envelope(x_spec, z, bin_m, "min")
    cross_y, cz_top = _envelope(y_spec, z, bin_m, "max")
    _, cz_bot = _envelope(y_spec, z, bin_m, "min")
    top_x, y_max = _envelope(x_spec, y_spec, bin_m, "max")
    _, y_min = _envelope(x_spec, y_spec, bin_m, "min")
    return BodyOutline(
        side_x=side_x,
        side_z_top=z_top,
        side_z_bot=z_bot,
        cross_y=cross_y,
        cross_z_top=cz_top,
        cross_z_bot=cz_bot,
        top_x=top_x,
        top_y_min=y_min,
        top_y_max=y_max,
    )


def build_height_map_from_columns(
    columns: Columns, frame: BodyFrame, log_volume_m3: float | None = None
) -> HeightMap:
    """Строит карту высот в координатах ТЗ из сырых колонок.

    Для каждой колонки: H = (z_top − z_floor) · voxel_size; колонки без
    днища или с отрицательной высотой отбрасываются (счётчики в HeightMap).
    """
    # Словарь днища: (ix, iy) → z_днища для быстрого поиска.
    floor_map = {
        (int(ix), int(iy)): float(iz)
        for (ix, iy), iz in zip(columns.floor_xy, columns.floor_z, strict=False)
    }

    # Фильтрация колонок верха: нужна опора на днище и z_top ≥ z_floor.
    z_top_of: list[float] = []
    xy_kept: list[tuple[int, int]] = []
    dropped_negative = 0
    dropped_no_floor = 0
    for (ix, iy), iz in zip(columns.top_xy, columns.top_z, strict=False):
        key = (int(ix), int(iy))
        z_bot = floor_map.get(key)
        if z_bot is None:
            dropped_no_floor += 1
            continue
        if float(iz) < z_bot:
            dropped_negative += 1
            continue
        xy_kept.append(key)
        z_top_of.append(float(iz))

    # Перевод индексов → метры модели → координаты ТЗ.
    voxel = frame.voxel_size_m
    if xy_kept:
        idx = np.asarray(xy_kept, dtype=np.float64)
        centers = frame.centers(idx)  # (N, 3) в метрах модели
        x_spec, y_spec = frame.to_spec(centers[:, 0], centers[:, 1])
        # z_floor — абсолютная высота днища: центр вокселя днища по Z.
        z_floor_idx = np.asarray([floor_map[k] for k in xy_kept], dtype=np.float64)
        z_floor = frame.centers(np.column_stack([idx[:, 0], idx[:, 1], z_floor_idx]))[
            :, 2
        ]
        # Высота груза: разность индексов × размер вокселя, м.
        h = (np.asarray(z_top_of, dtype=np.float64) - z_floor_idx) * voxel
    else:
        x_spec = np.empty(0)
        y_spec = np.empty(0)
        h = np.empty(0)
        z_floor = np.empty(0)

    return HeightMap(
        x=np.asarray(x_spec, dtype=np.float64),
        y=np.asarray(y_spec, dtype=np.float64),
        h=h,
        z_floor=z_floor,
        dx=voxel,
        dy=voxel,
        n_raw=int(columns.top_xy.shape[0]),
        n_dropped_negative=dropped_negative,
        n_dropped_no_floor=dropped_no_floor,
        log_volume_m3=log_volume_m3,
        approx_source=columns.approx_source,
    )

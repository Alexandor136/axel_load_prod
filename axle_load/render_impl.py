"""Графика рейса: три листа дашборда — продольный разрез, поперечный
разрез и схема колёс.

Кузов — контуры модели (body.ply) в координатах ТЗ; при отсутствии модели —
прямой ортогональный силуэт по константам TruckConfig. Груз лежит на реальном
(наклонном) дне данных; равномерного «идеального груза» нет. На графиках —
только итоговый ЦМ: красный ✕ (вычисленный) и синий ● (идеальный,
X = rear + ideal%·wheelbase, Y = 0) с аннотациями ΔX/ΔY. Тонны на
ось/колёсах — только груз; % на колёсах и у мостов — от полной массы
(баланс). Полосы нормы: баланс 30–36% по X и ЦМ ±0.30 м по Y.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch, Polygon, Rectangle  # noqa: E402

from .calc import AnalysisResult  # noqa: E402
from .clouds import BIN_M as _OUTLINE_BIN_M  # noqa: E402
from .schemas import BodyFrame, BodyOutline, HeightMap, TruckConfig  # noqa: E402

_BIN_M = 0.08
_X_LABEL = "X, м (от заднего торца к кабине)"
_Y_LABEL = "Y, м (от оси симметрии)"
_Z_LABEL = "Z, м (высота, система координат модели)"
_GUARD_THICKNESS_M = 0.40
# Fallback-геометрия силуэта, если нет BodyOutline (не параметры типа).
_FALLBACK_FLOOR_Z_M = 3.0
_FALLBACK_BOARD_TOP_Z_M = 4.78
_FALLBACK_WALL_X_M = 7.65
_FALLBACK_GUARD_TOP_Z_M = 5.60

# Цвета зон баланса (зелёный/жёлтый/красный/неизвестно).
_ZONE_COLORS: dict[str, str] = {
    "green": "#d8f4dd",
    "yellow": "#fff2c4",
    "red": "#ffd8d8",
    "unknown": "#ececec",
}
_NORM_BAND_COLOR = "#8fe6b0"  # коридор нормы на разрезах
_NORM_LINE_COLOR = "limegreen"  # линия идеала

# Габариты для схемы колёс (вид сверху), паспорт шин 27.00R49 / серия 7558.
_TIRE_OD_M = 2.54  # наружный диаметр шины
_TIRE_WIDTH_M = 0.69  # ширина шины
_DUAL_GAP_M = 0.06  # зазор между шинами сдвоенной пары
_CABIN_DEPTH_M = 2.4  # кабина по X (схема)
_CABIN_WIDTH_M = 2.6  # кабина по Y (схема)


# --------------------------------------------------------------------------- #
#  Профили для разрезов                                                       #
# --------------------------------------------------------------------------- #
_SMOOTH_M = 0.5


def _odd(n: int) -> int:
    """Нечётное число ≥3 — размер окна скользящего среднего."""
    return max(3, n if n % 2 == 1 else n + 1)


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    """Скользящее среднее с игнорированием NaN (взвешенное по числу конечных).

    Неконечные значения (NaN) исключаются из числителя и знаменателя,
    поэтому края пропусков не «притягиваются» к нулю.
    """
    if window < 3 or values.size < window or not np.isfinite(values).any():
        return values
    ok = np.isfinite(values)
    # Числитель: сумма конечных значений в окне; знаменатель: их количество.
    num = np.convolve(np.where(ok, values, 0.0), np.ones(window), mode="same")
    den = np.convolve(ok.astype(float), np.ones(window), mode="same")
    out = np.full_like(values, np.nan)
    return np.divide(num, den, out=out, where=den > 0)


def _rdp(points: np.ndarray, eps: float) -> np.ndarray:
    """Аппроксимация ломаной Рамера–Дугласа–Пекера (отрезки, допуск eps)."""
    n = points.shape[0]
    if n < 3:
        return points
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True
    stack: list[tuple[int, int]] = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        p0 = points[i0]
        seg = points[i1] - p0
        length = float(np.hypot(seg[0], seg[1]))
        rel = points[i0 + 1 : i1] - p0
        if length < 1e-12:
            dist = np.hypot(rel[:, 0], rel[:, 1])
        else:
            dist = np.abs(rel[:, 0] * seg[1] - rel[:, 1] * seg[0]) / length
        k = int(np.argmax(dist))
        if dist[k] > eps:
            idx = i0 + 1 + k
            keep[idx] = True
            stack.append((i0, idx))
            stack.append((idx, i1))
    return points[keep]


def _contour_window() -> int:
    """Окно сглаживания контура модели (~1 м) для бинов 0.10 м."""
    return _odd(round(1.0 / _OUTLINE_BIN_M))


def _section_profile(
    hm: HeightMap, edges: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """На каждую продольную ячейку: центры, дно (данные), низ и верх груза.

    Для каждого X-бина берём: floor — минимум z_floor (дно кузова);
    bot — минимум z_floor по колонкам с грузом; top — максимум z_floor + h.
    Затем сглаживаем скользящим средним.
    """
    centers = 0.5 * (edges[:-1] + edges[1:])
    floor = np.full(centers.size, np.nan)
    bot = np.full(centers.size, np.nan)
    top = np.full(centers.size, np.nan)
    # digitize: индекс бина для каждой колонки (−1 → до первого ребра).
    idx = np.digitize(hm.x, edges) - 1
    z_ok = np.isfinite(hm.z_floor)
    h_ok = np.isfinite(hm.h)
    for i in range(centers.size):
        cells = idx == i
        z_floor = hm.z_floor[cells & z_ok]
        if z_floor.size:
            floor[i] = float(np.min(z_floor))
        # Груз: только колонки с конечными z_floor и h > 0.
        cargo = cells & z_ok & h_ok & (hm.h > 0.0)
        if cargo.any():
            bot[i] = float(np.min(hm.z_floor[cargo]))
            top[i] = float(np.max(hm.z_floor[cargo] + hm.h[cargo]))
    # Сглаживание ~0.5 м (окно по размеру бина).
    window = _odd(round(_SMOOTH_M / _BIN_M))
    return (
        centers,
        _smooth(floor, window),
        _smooth(bot, window),
        _smooth(top, window),
    )


def _cross_profile(
    hm: HeightMap, x_plane_m: float, y_edges: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """В плоскости X = x_plane_m: центры, дно, низ и верх груза по Y-бинам.

    Берём колонки в полосе ±0.3 м (или ±dx) вокруг плоскости разреза,
    затем для каждого Y-бина — min(z_floor) для дна, min/max для груза.
    """
    centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    floor = np.full(centers.size, np.nan)
    bot = np.full(centers.size, np.nan)
    top = np.full(centers.size, np.nan)
    if hm.is_empty:
        return centers, floor, bot, top

    # Полоса колонок вокруг плоскости разреза: ±max(0.3, dx).
    near = np.abs(hm.x - x_plane_m) <= max(0.3, hm.dx)
    if not near.any():
        return centers, floor, bot, top

    y = hm.y[near]
    z_floor = hm.z_floor[near]
    h = hm.h[near]
    z_ok = np.isfinite(z_floor)
    h_ok = np.isfinite(h)
    # Индекс Y-бина для каждой колонки; clip — за пределами edges → крайний бин.
    idx = np.clip(np.digitize(y, y_edges) - 1, 0, centers.size - 1)
    for b in range(centers.size):
        cells = idx == b
        zf = z_floor[cells & z_ok]
        if zf.size:
            floor[b] = float(np.min(zf))
        cargo = cells & z_ok & h_ok & (h > 0.0)
        if cargo.any():
            bot[b] = float(np.min(z_floor[cargo]))
            top[b] = float(np.max(z_floor[cargo] + h[cargo]))
    step = float(y_edges[1] - y_edges[0])
    window = _odd(round(_SMOOTH_M / step)) if step > 0.0 else 3
    return (
        centers,
        _smooth(floor, window),
        _smooth(bot, window),
        _smooth(top, window),
    )


def _body_floor_z(hm: HeightMap, truck: TruckConfig) -> float:
    """Нижняя граница силуэта: не выше самого низкого дна данных.

    Берём min(ideal_floor_z, минимум конечных z_floor) — чтобы силуэт
    не «подвисал» над реальным дном кузова.
    """
    if hm.z_floor.size == 0:
        return _FALLBACK_FLOOR_Z_M
    finite = hm.z_floor[np.isfinite(hm.z_floor)]
    if finite.size == 0:
        return _FALLBACK_FLOOR_Z_M
    return float(min(_FALLBACK_FLOOR_Z_M, float(np.min(finite))))


def _clip_to_body(
    artist: object,
    vertices: np.ndarray,
    ax: plt.Axes,
) -> None:
    """Обрезает художника по замкнутому полигону кузова."""
    points = np.asarray(vertices, dtype=np.float64)
    if points.ndim != 2 or points.shape[0] < 3:
        return
    clip = Polygon(
        points,
        closed=True,
        transform=ax.transData,
        facecolor="none",
        edgecolor="none",
    )
    artist.set_clip_path(clip)


def _side_body_vertices(
    outline: BodyOutline | None,
    frame: BodyFrame,
    truck: TruckConfig,
    z_body: float,
) -> np.ndarray:
    """Полигон бокового силуэта кузова для обрезки полос."""
    if outline is not None and outline.side_x.size:
        xs = np.concatenate([outline.side_x, outline.side_x[::-1]])
        zs = np.concatenate([outline.side_z_top, outline.side_z_bot[::-1]])
        return np.column_stack([xs, zs])
    xs = np.array([0.0, frame.rear_y_m, frame.rear_y_m, 0.0])
    zs = np.array([z_body, z_body, _FALLBACK_BOARD_TOP_Z_M, _FALLBACK_BOARD_TOP_Z_M])
    return np.column_stack([xs, zs])


def _cross_body_vertices(
    outline: BodyOutline | None,
    frame: BodyFrame,
    truck: TruckConfig,
    z_body: float,
) -> np.ndarray:
    """Полигон поперечного силуэта кузова для обрезки полос."""
    half_w = frame.width_m / 2.0
    if outline is not None and outline.cross_y.size:
        ys = np.concatenate([outline.cross_y, outline.cross_y[::-1]])
        zs = np.concatenate([outline.cross_z_top, outline.cross_z_bot[::-1]])
        return np.column_stack([ys, zs])
    ys = np.array([-half_w, half_w, half_w, -half_w])
    zs = np.array([z_body, z_body, _FALLBACK_BOARD_TOP_Z_M, _FALLBACK_BOARD_TOP_Z_M])
    return np.column_stack([ys, zs])


def _top_body_vertices(
    outline: BodyOutline | None,
    frame: BodyFrame,
    half_w: float,
) -> np.ndarray:
    """Полигон вида сверху для обрезки полос на схеме колёс."""
    if outline is not None and outline.top_x.size:
        xs = np.concatenate([outline.top_x, outline.top_x[::-1]])
        ys = np.concatenate([outline.top_y_max, outline.top_y_min[::-1]])
        return np.column_stack([xs, ys])
    xs = np.array([0.0, frame.rear_y_m, frame.rear_y_m, 0.0])
    ys = np.array([-half_w, -half_w, half_w, half_w])
    return np.column_stack([xs, ys])


def _envelope_top(hm: HeightMap, y_edges: np.ndarray) -> np.ndarray:
    """Верх груза «Макс. высота по длине»: максимум по всем X в Y-бинах.

    Огибающая сверху — для линии «Макс. высота по длине» на разрезе вдоль.
    """
    centers = 0.5 * (y_edges[:-1] + y_edges[1:])
    env = np.full(centers.size, np.nan)
    if hm.is_empty:
        return env
    top_all = hm.z_floor + hm.h
    ok = np.isfinite(top_all) & np.isfinite(hm.h) & (hm.h > 0.0)
    if not ok.any():
        return env
    idx = np.clip(np.digitize(hm.y[ok], y_edges) - 1, 0, centers.size - 1)
    z = top_all[ok]
    for b in range(centers.size):
        vals = z[idx == b]
        if vals.size:
            env[b] = float(np.max(vals))
    step = float(y_edges[1] - y_edges[0])
    window = _odd(round(_SMOOTH_M / step)) if step > 0.0 else 3
    return _smooth(env, window)


# --------------------------------------------------------------------------- #
#  Текстовая панель ВНЕ графика                                               #
# --------------------------------------------------------------------------- #


# Общие параметры легенды (интервалы, отступы).
_LEGEND_KW: dict[str, float] = {
    "labelspacing": 0.6,
    "columnspacing": 1.2,
    "borderpad": 0.6,
    "handletextpad": 0.5,
}


def _legend_below(
    ax: plt.Axes,
    *,
    fs: float = 8.5,
    ncol: int = 5,
    dy: float = -0.22,
    handles: list | None = None,
) -> None:
    """Легенда под осями: dy < 0 — смещение вниз (в долях высоты axes)."""
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, dy),
        fontsize=fs,
        framealpha=0.92,
        ncol=ncol,
        markerscale=0.7,
        **_LEGEND_KW,
    )


# --------------------------------------------------------------------------- #
#  Силуэт кузова (прямые границы)                                             #
# --------------------------------------------------------------------------- #
def _draw_body_side(
    ax: plt.Axes,
    frame: BodyFrame,
    truck: TruckConfig,
    z_body: float,
    *,
    outline: BodyOutline | None = None,
    floor_x: np.ndarray | None = None,
    floor_z: np.ndarray | None = None,
) -> None:
    """Силуэт кузова сбоку: прямоугольники (fallback) или контур outline.

    outline=None — грубый силуэт: прямоугольник борта + полоса задней
    решётки; с outline — сглаженный контур (верх/низ) + дно из данных.
    """
    if outline is None:
        # Fallback: борт-прямоугольник от z_body до board_top + решётка.
        z1 = _FALLBACK_BOARD_TOP_Z_M
        xw = _FALLBACK_WALL_X_M
        zg = _FALLBACK_GUARD_TOP_Z_M
        xg = frame.rear_y_m
        ax.add_patch(
            Rectangle(
                (0.0, z_body),
                xw,
                z1 - z_body,
                fc="0.93",
                ec="0.45",
                lw=1.4,
                zorder=1,
                label="Кузов (силуэт)",
            )
        )
        ax.add_patch(
            Rectangle(
                (xw, zg - _GUARD_THICKNESS_M),
                xg - xw,
                _GUARD_THICKNESS_M,
                fc="0.93",
                ec="0.45",
                lw=1.4,
                zorder=1,
            )
        )
        return
    # Контур: сглажить верх/низ, подмешать дно из данных (floor_*), RDP-упростить.
    window = _contour_window()
    z_top = _smooth(outline.side_z_top, window)
    z_bot = _smooth(outline.side_z_bot, window)
    if floor_x is not None and floor_z is not None:
        fmask = np.isfinite(floor_z)
        if np.count_nonzero(fmask) >= 2:
            fl = np.interp(
                outline.side_x,
                floor_x[fmask],
                floor_z[fmask],
                left=np.nan,
                right=np.nan,
            )
            # Дно из данных выше outline — берём его; иначе оставляем outline.
            z_bot = np.where(np.isfinite(fl), fl, z_bot)
        z_bot = _smooth(z_bot, window)
    # Замкнутый контур: верх вперёд, низ назад (для заливки/линии).
    xs = np.concatenate([outline.side_x, outline.side_x[::-1]])
    zs = np.concatenate([z_top, z_bot[::-1]])
    pts = _rdp(np.column_stack([xs, zs]), eps=0.05)
    ax.plot(
        pts[:, 0],
        pts[:, 1],
        color="0.15",
        lw=2.2,
        zorder=4,
        label="Кузов и дно",
    )


def _draw_body_cross(
    ax: plt.Axes,
    frame: BodyFrame,
    truck: TruckConfig,
    z_body: float,
    *,
    outline: BodyOutline | None = None,
    floor_y: np.ndarray | None = None,
    floor_z: np.ndarray | None = None,
    x_plane: float | None = None,
) -> None:
    """Силуэт кузова поперёк: fallback-прямоугольник или U-образный контур.

    x_plane — если задан, высота бортов берётся из бокового профиля
    в этой точке (одинаковые борта на разрезе).
    """
    if outline is None:
        z1 = _FALLBACK_BOARD_TOP_Z_M
        half_w = frame.width_m / 2.0
        ax.add_patch(
            Rectangle(
                (-half_w, z_body),
                frame.width_m,
                z1 - z_body,
                fc="0.93",
                ec="0.45",
                lw=1.4,
                zorder=1,
                label="Кузов (силуэт)",
            )
        )
        return
    window = _contour_window()
    ys = outline.cross_y
    if x_plane is not None:
        # Высота бортов — как в месте разреза (боковой профиль на x_plane).
        wall_z = float(np.interp(x_plane, outline.side_x, outline.side_z_top))
        z_top = np.full(ys.size, wall_z)
    else:
        z_top = _smooth(outline.cross_z_top, window)
    z_bot = _smooth(outline.cross_z_bot, window)
    if floor_y is not None and floor_z is not None:
        fmask = np.isfinite(floor_z)
        if np.count_nonzero(fmask) >= 2:
            fl = np.interp(
                ys,
                floor_y[fmask],
                floor_z[fmask],
                left=np.nan,
                right=np.nan,
            )
            z_bot = np.where(np.isfinite(fl), fl, z_bot)
        z_bot = _smooth(z_bot, window)
    # Открытый U: левый борт вниз → дно → правый борт вверх (без верха).
    us_y = np.concatenate([[ys[0]], ys, [ys[-1]]])
    us_z = np.concatenate([[z_top[0]], z_bot, [z_top[-1]]])
    ax.plot(
        us_y,
        us_z,
        color="0.15",
        lw=2.2,
        zorder=4,
        label="Кузов и дно",
    )


# --------------------------------------------------------------------------- #
#  Маркеры итогового ЦМ                                                       #
# --------------------------------------------------------------------------- #
def _draw_com_markers_side(
    ax: plt.Axes, result: AnalysisResult, truck: TruckConfig
) -> None:
    if not (np.isfinite(result.total_com_x_m) and np.isfinite(result.total_com_z_m)):
        return
    z = result.total_com_z_m
    ax.plot(
        truck.ideal_com_x_m,
        z,
        "o",
        ms=10,
        color="deepskyblue",
        mec="navy",
        zorder=6,
        label="Идеальный ЦМ",
    )
    ax.plot(
        result.total_com_x_m,
        z,
        "x",
        ms=13,
        mew=2.5,
        color="red",
        zorder=6,
        label="Итоговый ЦМ (вычисл.)",
    )
    ax.annotate(
        f"ΔX = {result.com_delta_x_m:+.2f} м",
        (0.5 * (truck.ideal_com_x_m + result.total_com_x_m), z),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        color="crimson",
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
        zorder=6,
    )


def _draw_com_markers_cross(
    ax: plt.Axes, result: AnalysisResult, truck: TruckConfig
) -> None:
    if not (np.isfinite(result.total_com_y_m) and np.isfinite(result.total_com_z_m)):
        return
    z = result.total_com_z_m
    ax.plot(
        truck.ideal_com_y_m,
        z,
        "o",
        ms=10,
        color="deepskyblue",
        mec="navy",
        zorder=6,
        label="Идеальный ЦМ",
    )
    ax.plot(
        result.total_com_y_m,
        z,
        "x",
        ms=13,
        mew=2.5,
        color="red",
        zorder=6,
        label="Итоговый ЦМ (вычисл.)",
    )
    ax.annotate(
        f"ΔY = {result.com_delta_y_m:+.2f} м",
        (0.5 * (truck.ideal_com_y_m + result.total_com_y_m), z),
        textcoords="offset points",
        xytext=(0, 14),
        ha="center",
        color="crimson",
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
        zorder=6,
    )


# --------------------------------------------------------------------------- #
#  1. Продольный разрез (вид сбоку)                                           #
# --------------------------------------------------------------------------- #
def _draw_section(
    ax: plt.Axes,
    hm: HeightMap,
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    outline: BodyOutline | None = None,
    legend_fs: float = 8.5,
    legend_ncol: int = 5,
    with_legend: bool = True,
) -> None:
    """Продольный разрез (вид сбоку): норма-коридор, кузов, груз, ЦМ.

    edges — X-бины по длине кузова; коридор нормы баланса (зелёный
    span + пунктир) по позиции задней оси от кормы.
    """
    edges = np.arange(0.0, frame.rear_y_m + _BIN_M, _BIN_M)
    centers, floor, bot, top = _section_profile(hm, edges)
    z_body = _body_floor_z(hm, truck)

    # Коридор нормы: x = rear_axle_from_rear + pct/100 · wheelbase.
    x_min = (
        truck.rear_axle_from_rear_m + truck.green_min_pct / 100.0 * truck.wheelbase_m
    )
    x_max = (
        truck.rear_axle_from_rear_m + truck.green_max_pct / 100.0 * truck.wheelbase_m
    )
    span = ax.axvspan(
        x_min,
        x_max,
        fc=_NORM_BAND_COLOR,
        alpha=0.55,
        zorder=0,
        label="Норма баланса 30–36%",
    )
    _clip_to_body(
        span,
        _side_body_vertices(outline, frame, truck, z_body),
        ax,
    )
    for x_edge in (x_min, x_max):
        ax.axvline(
            x_edge,
            color=_NORM_LINE_COLOR,
            ls="--",
            lw=2.0,
            zorder=3.5,
            label="_norm_edge",
        )

    # Кузов: outline или fallback; дно — отдельной линией при outline=None.
    _draw_body_side(
        ax,
        frame,
        truck,
        z_body,
        outline=outline,
        floor_x=centers,
        floor_z=floor,
    )
    if outline is None:
        fmask = np.isfinite(floor)
        if fmask.any():
            ax.plot(
                centers[fmask],
                floor[fmask],
                color="0.15",
                lw=1.8,
                zorder=4,
                label="Дно (данные)",
            )

    # Груз: заливка между низом и верхом, только до стены (ideal_wall_x).
    cmask = np.isfinite(bot) & np.isfinite(top) & (centers <= _FALLBACK_WALL_X_M)
    if cmask.any():
        ax.fill_between(
            centers,
            bot,
            top,
            where=cmask,
            color="tab:orange",
            alpha=0.65,
            label="Груз",
            zorder=2,
        )
        ax.plot(centers[cmask], top[cmask], color="tab:orange", lw=1.5, zorder=3)

    _draw_com_markers_side(ax, result, truck)

    ax.set_xlabel(_X_LABEL)
    ax.set_ylabel(_Z_LABEL)
    ax.set_xlim(-0.4, frame.rear_y_m + 0.4)
    ax.grid(True, ls=":", alpha=0.5)
    if with_legend:
        _legend_below(ax, fs=legend_fs, ncol=legend_ncol)


# --------------------------------------------------------------------------- #
#  2. Поперечный разрез (вид сзади самосвала)                                 #
# --------------------------------------------------------------------------- #
def _draw_cross(
    ax: plt.Axes,
    hm: HeightMap,
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    outline: BodyOutline | None = None,
    legend_fs: float = 8.5,
    legend_ncol: int = 4,
    with_legend: bool = True,
) -> None:
    """Поперечный разрез (вид сзади): коридор бокового отклонения, груз, ЦМ.

    x_plane — плоскость разреза (по ЦМ груза или середина кузова);
    y_edges — Y-бины по ширине; коридор ±lateral_limit (зелёный span).
    """
    half_w = frame.width_m / 2.0
    x_plane = (
        result.cargo_com_x_m
        if np.isfinite(result.cargo_com_x_m)
        else frame.rear_y_m / 2.0
    )
    y_edges = np.arange(-half_w, half_w + frame.voxel_size_m, frame.voxel_size_m)
    z_body = _body_floor_z(hm, truck)

    span = ax.axvspan(
        -truck.lateral_limit_m,
        truck.lateral_limit_m,
        fc=_NORM_BAND_COLOR,
        alpha=0.55,
        zorder=0,
        label=f"Норма ЦМ ±{truck.lateral_limit_m:.2f} м",
    )
    _clip_to_body(
        span,
        _cross_body_vertices(outline, frame, truck, z_body),
        ax,
    )
    for y_edge in (-truck.lateral_limit_m, truck.lateral_limit_m):
        ax.axvline(
            y_edge,
            color=_NORM_LINE_COLOR,
            ls="--",
            lw=2.0,
            zorder=3.5,
            label="_norm_edge",
        )

    # Профиль в плоскости x_plane + силуэт кузова U-образного сечения.
    y_c, floor, bot, top = _cross_profile(hm, x_plane, y_edges)
    _draw_body_cross(
        ax,
        frame,
        truck,
        z_body,
        outline=outline,
        floor_y=y_c,
        floor_z=floor,
        x_plane=x_plane,
    )
    if outline is None:
        fmask = np.isfinite(floor)
        if fmask.any():
            ax.plot(
                y_c[fmask],
                floor[fmask],
                color="0.15",
                lw=3.5,
                solid_capstyle="butt",
                zorder=4,
                label="Дно (данные)",
            )

    # Груз в разрезе по ЦМ: заливка + верхняя линия.
    cmask = np.isfinite(bot) & np.isfinite(top)
    if cmask.any():
        ax.fill_between(
            y_c,
            bot,
            top,
            where=cmask,
            color="tab:orange",
            alpha=0.65,
            zorder=2,
            label="Груз (разрез по ЦМ)",
        )
        ax.plot(y_c[cmask], top[cmask], color="tab:orange", lw=1.8, zorder=3)

    # Огибающая «Макс. высота по длине» — пунктир (max по всем X в Y-бинах).
    envelope = _envelope_top(hm, y_edges)
    emask = np.isfinite(envelope)
    if emask.any():
        ax.plot(
            y_c[emask],
            envelope[emask],
            color="saddlebrown",
            ls="--",
            lw=1.8,
            zorder=3.4,
            label="Макс. высота по длине",
        )

    ax.axvline(0.0, color="0.45", ls="-.", lw=1.2, zorder=3, label="Ось симметрии")

    _draw_com_markers_cross(ax, result, truck)

    # Верх осей: max(борта, груз, огибающая) + запас.
    z_candidates = [_FALLBACK_BOARD_TOP_Z_M]
    if cmask.any():
        z_candidates.append(float(np.nanmax(top)))
    if emask.any():
        z_candidates.append(float(np.nanmax(envelope)))
    z_top = max(z_candidates)

    ax.set_xlabel(_Y_LABEL)
    ax.set_ylabel(_Z_LABEL)
    ax.set_xlim(-half_w - 1.6, half_w + 1.6)
    ax.set_ylim(z_body - 1.6, z_top + 0.5)
    ax.grid(True, ls=":", alpha=0.5)
    if with_legend:
        _legend_below(ax, fs=legend_fs, ncol=legend_ncol)


# --------------------------------------------------------------------------- #
#  Варианты идеального груза (section_*_ideal.png)                            #
# --------------------------------------------------------------------------- #
_SLOPE_COT = 1.428  # cot(35°): 1 м подъёма → 1.428 м по горизонтали
_IDEAL_COLORS = ("tab:green", "tab:blue", "tab:purple")


# --------------------------------------------------------------------------- #
#  3. Вид сверху                                                              #
# --------------------------------------------------------------------------- #
def _draw_top_outline(
    ax: plt.Axes,
    outline: BodyOutline,
    *,
    color: str,
    lw: float,
    zorder: float,
    label: str,
) -> None:
    """Контур кузова сверху: замкнутая ломаная (top_y_max вперёд, min назад), RDP."""
    xs = np.concatenate([outline.top_x, outline.top_x[::-1]])
    ys = np.concatenate([outline.top_y_max, outline.top_y_min[::-1]])
    pts = _rdp(np.column_stack([xs, ys]), eps=0.1)
    ax.plot(pts[:, 0], pts[:, 1], color=color, lw=lw, zorder=zorder, label=label)


# --------------------------------------------------------------------------- #
#  4. Схема колёс с перегрузом                                                #
# --------------------------------------------------------------------------- #
def _wheel_zone(overload_pct: float, truck: TruckConfig) -> str:
    """Зона колеса по перегрузу: ≤0 — зелёный, ≤warn — жёлтый, иначе красный."""
    if not np.isfinite(overload_pct):
        return "unknown"
    if overload_pct <= 0.0:
        return "green"
    if overload_pct <= truck.wheel_warn_pct:
        return "yellow"
    return "red"


def _balance_scale(
    ax: plt.Axes,
    value: float,
    truck: TruckConfig,
    *,
    caption: str,
    vmin: float = 20.0,
    vmax: float = 60.0,
) -> None:
    """Горизонтальная шкала баланса передней оси (по образцу блока 8).

    Сегменты: красный vmin..front_min, жёлтый front_min..green_min,
    зелёный green_min..green_max, жёлтый green_max..front_max,
    красный front_max..vmax. Деления ×5, маркер-стрелка в цвете зоны,
    единица «%» один раз справа.
    """
    ax.set_axis_off()
    ax.set_xlim(vmin, vmax)
    ax.set_ylim(-0.55, 0.75)
    # Пять сегментов шкалы по границам зон из truck.
    segs = [
        (vmin, truck.front_min_pct, _ZONE_COLORS["red"]),
        (truck.front_min_pct, truck.green_min_pct, _ZONE_COLORS["yellow"]),
        (truck.green_min_pct, truck.green_max_pct, _ZONE_COLORS["green"]),
        (truck.green_max_pct, truck.front_max_pct, _ZONE_COLORS["yellow"]),
        (truck.front_max_pct, vmax, _ZONE_COLORS["red"]),
    ]
    bar_y, bar_h = -0.10, 0.30
    for a, b, c in segs:
        ax.add_patch(
            Rectangle((a, bar_y), b - a, bar_h, fc=c, ec="0.45", lw=0.8, zorder=2)
        )
    # Засечки и числа ×5 под полосой; «%» один раз справа.
    for t in range(int(vmin), int(vmax) + 1, 5):
        ax.plot([t, t], [bar_y, bar_y - 0.10], color="0.4", lw=0.8, zorder=3)
        ax.text(
            t, bar_y - 0.14, str(t), ha="center", va="top", fontsize=7, color="0.35"
        )
    ax.text(
        vmax + 1.0,
        bar_y + bar_h / 2.0,
        "%",
        ha="left",
        va="center",
        fontsize=8,
        color="0.35",
    )
    ax.text(
        vmin,
        0.62,
        caption,
        ha="left",
        va="center",
        fontsize=9,
        fontweight="bold",
        color="0.15",
    )
    if np.isfinite(value):
        # Маркер-стрелка над полосой: цвет = зона значения; clamping к vmin..vmax.
        xm = min(max(value, vmin), vmax)
        if value < truck.front_min_pct or value > truck.front_max_pct:
            zone = "red"
        elif value < truck.green_min_pct or value > truck.green_max_pct:
            zone = "yellow"
        else:
            zone = "green"
        ax.plot(
            [xm, xm],
            [bar_y + bar_h, bar_y + bar_h + 0.22],
            color=_ZONE_COLORS[zone],
            lw=0,
        )
        ax.plot(
            xm,
            bar_y + bar_h + 0.05,
            marker="v",
            ms=10,
            color=_ZONE_COLORS[zone],
            mec="0.25",
            mew=0.8,
            zorder=5,
        )
        ax.text(
            xm,
            bar_y + bar_h + 0.28,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="0.1",
        )


def _mini_axle_scale(
    ax: plt.Axes,
    x_center: float,
    y_center: float,
    value: float,
    name: str,
    truck: TruckConfig,
    *,
    width: float = 4.5,
    height: float = 0.16,
) -> None:
    """Мини-шкала баланса моста на схеме колёс (координаты данных).

    Экран сверху вниз (ось Y инвертирована, в данных y растёт вниз):
      1) маркер-стрелка ▼ в цвете зоны + число значения — как у большой шкалы;
      2) цветная полоса из пяти сегментов;
      3) под полосой засечки ×5 с числами.

    Имя моста НЕ рисуется здесь — оно сверху самосвала в цвете оси
    (_draw_wheels). Задний мост — зеркальные зоны (зелёный 64–70 и т.д.).
    """
    # Границы зон: для заднего моста зеркалим передние (100 − front_pct).
    is_rear = name.startswith("Зад")
    if is_rear:
        g0 = 100.0 - truck.green_max_pct  # 64
        g1 = 100.0 - truck.green_min_pct  # 70
        y0 = 100.0 - truck.front_max_pct  # 62
        y1 = 100.0 - truck.front_min_pct  # 72
        vmin, vmax = 40.0, 80.0
    else:
        g0, g1 = truck.green_min_pct, truck.green_max_pct
        y0, y1 = truck.front_min_pct, truck.front_max_pct
        vmin, vmax = 20.0, 60.0
    x_left = x_center - width / 2.0

    # Преобразование «процент шкалы → x в данных».
    def _x(v: float) -> float:
        return x_left + (v - vmin) / (vmax - vmin) * width

    # Пять сегментов: красный / жёлтый / зелёный / жёлтый / красный.
    segs = [
        (vmin, y0, _ZONE_COLORS["red"]),
        (y0, g0, _ZONE_COLORS["yellow"]),
        (g0, g1, _ZONE_COLORS["green"]),
        (g1, y1, _ZONE_COLORS["yellow"]),
        (y1, vmax, _ZONE_COLORS["red"]),
    ]
    # Экранные смещения «сверху вниз» (ось Y инвертирована: +y вниз).
    VAL_DY = -0.14  # число значения над ▼
    ARR_DY = -0.05  # ▼ чуть над верхом полосы
    TICK_TXT_DY = 0.13
    bar_top = y_center - height / 2.0  # верх полосы (меньший y — выше на экране)
    bar_bot = y_center + height / 2.0  # низ полосы
    for a, b, c in segs:
        ax.add_patch(
            Rectangle(
                (_x(a), bar_top),
                _x(b) - _x(a),
                height,
                fc=c,
                ec="0.5",
                lw=0.6,
                zorder=6,
            )
        )
    # Засечки ×5 с числами — под полосой (как у большой шкалы разреза).
    tick_fs = 7.0
    for t in range(int(vmin), int(vmax) + 1, 5):
        ax.plot(
            [_x(t), _x(t)],
            [bar_bot, bar_bot + 0.06],
            color="0.4",
            lw=0.7,
            zorder=6,
        )
        ax.text(
            _x(t),
            bar_bot + TICK_TXT_DY,
            str(t),
            ha="center",
            va="top",
            fontsize=tick_fs,
            color="0.35",
            zorder=6,
        )
    # Маркер-стрелка ▼ в цвете зоны + число — как у большой шкалы.
    # Имя моста здесь не рисуется — оно сверху самосвала.
    if np.isfinite(value):
        if value < truck.front_min_pct or value > truck.front_max_pct:
            zone = "red"
        elif value < truck.green_min_pct or value > truck.green_max_pct:
            zone = "yellow"
        else:
            zone = "green"
        xm = _x(min(max(value, vmin), vmax))
        ax.plot(
            [xm, xm],
            [bar_top, bar_top + ARR_DY],
            color=_ZONE_COLORS[zone],
            lw=0,
            zorder=7,
        )
        ax.plot(
            xm,
            bar_top + ARR_DY,
            marker="v",
            ms=9,
            color=_ZONE_COLORS[zone],
            mec="0.25",
            mew=0.8,
            zorder=7,
        )
        ax.text(
            xm,
            bar_top + VAL_DY,
            f"{value:.1f}",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="0.1",
            zorder=7,
        )


def _mini_scale_layout(body_len: float) -> tuple[float, float, float]:
    """Центры и ширина двух мини-шкал под кузовом (координаты X, метры).

    Шкалы прижаты к краям с отступом 2.5 % длины кузова: подписи на стыке
    (``80`` правой и ``20`` левой) не слипаются, а правая шкала не выходит
    за борт. При кузове 9.629 м: центры 2.359 и 7.270, ширина 4.198,
    зазор между полосами ≈ 0.75 м.

    Args:
        body_len: длина кузова по X (``TruckConfig.x_limit_m``), м.

    Returns:
        ``(x_rear, x_front, width)`` — центры задней и передней шкал и ширина.
    """
    width = body_len * 0.436
    margin = body_len * 0.025
    return margin + width / 2.0, body_len - margin - width / 2.0, width


def _draw_wheels(
    ax: plt.Axes,
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    outline: BodyOutline | None = None,
    legend_fs: float = 8.5,
    axle_scales: bool = False,
    legend_dy: float = -0.17,
) -> None:
    """Схема колёс (вид сверху): оси мостов, шины, перегруз, мини-шкалы.

    axle_scales=True — под каждым мостом рисует мини-шкалу баланса
    (_mini_axle_scale) в координатах данных; +Y = правый борт внизу
    (invert_yaxis вызывается здесь).
    """
    half_w = frame.width_m / 2.0
    x_rear = truck.rear_axle_from_rear_m
    x_front = truck.front_axle_from_rear_m
    wheel_len = _TIRE_OD_M
    tire_w = _TIRE_WIDTH_M
    dual_gap = _DUAL_GAP_M
    single_w = _TIRE_WIDTH_M

    # Зелёные зоны: коридор баланса по X и норма ЦМ по Y.
    x_min = (
        truck.rear_axle_from_rear_m + truck.green_min_pct / 100.0 * truck.wheelbase_m
    )
    x_max = (
        truck.rear_axle_from_rear_m + truck.green_max_pct / 100.0 * truck.wheelbase_m
    )
    span_x = ax.axvspan(
        x_min,
        x_max,
        fc=_NORM_BAND_COLOR,
        alpha=0.35,
        zorder=0,
        label=f"Норма баланса {truck.green_min_pct:.0f}–{truck.green_max_pct:.0f}%",
    )
    span_y = ax.axhspan(
        -truck.lateral_limit_m,
        truck.lateral_limit_m,
        fc=_NORM_BAND_COLOR,
        alpha=0.35,
        zorder=0,
        label=f"Норма ЦМ ±{truck.lateral_limit_m:.2f} м",
    )
    body_vertices = _top_body_vertices(outline, frame, half_w)
    _clip_to_body(span_x, body_vertices, ax)
    _clip_to_body(span_y, body_vertices, ax)

    if outline is None:
        ax.add_patch(
            Rectangle(
                (0.0, -half_w),
                frame.rear_y_m,
                frame.width_m,
                fill=False,
                ec="0.25",
                lw=2.0,
                zorder=2,
                label="Кузов",
            )
        )
    else:
        _draw_top_outline(
            ax, outline, color="0.25", lw=2.0, zorder=2, label="Кузов (модель)"
        )

    # Кабина (схематично, чуть левее оси).
    cab_x0 = frame.rear_y_m - _CABIN_DEPTH_M
    cab_y0 = -0.45 - _CABIN_WIDTH_M / 2.0
    ax.add_patch(
        Rectangle(
            (cab_x0, cab_y0),
            _CABIN_DEPTH_M,
            _CABIN_WIDTH_M,
            fill=False,
            ec="tab:cyan",
            ls="--",
            lw=1.8,
            zorder=6,
            label="_cabin",
        )
    )
    ax.text(
        cab_x0 + _CABIN_DEPTH_M / 2.0,
        cab_y0 + _CABIN_WIDTH_M / 2.0,
        "Кабина",
        ha="center",
        va="center",
        fontsize=8,
        color="tab:cyan",
        fontweight="bold",
        zorder=7,
    )
    cargo_mass = result.cargo_mass_kg
    total_mass = result.total_mass_kg

    def _wheel_pct(full_kg: float) -> str:
        """Доля колеса или сдвоенной пары (половина моста) в полной массе, %."""
        if np.isfinite(full_kg) and np.isfinite(total_mass) and total_mass > 0.0:
            return f"{100.0 * full_kg / total_mass:.1f}%"
        return "—"

    # Полные массы мостов из balance_*_pct; доля колеса — *_right_share.
    rear_full = (
        total_mass * result.balance_rear_pct / 100.0
        if np.isfinite(result.balance_rear_pct)
        else float("nan")
    )
    front_full = (
        total_mass * result.balance_front_pct / 100.0
        if np.isfinite(result.balance_front_pct)
        else float("nan")
    )

    # Четыре колеса: (борт, x, y, кг груза, номинал, сдвоенное?, полная кг).
    # Для сдвоенной пары full_kg — нагрузка на борт, т.е. половина задней оси.
    wheels = (
        (
            "прав.",
            x_rear,
            truck.track_rear_m / 2.0,
            result.rear_right_kg,
            truck.nominal_rear_wheel_kg,
            True,
            rear_full * result.rear_right_share,
        ),
        (
            "лев.",
            x_rear,
            -truck.track_rear_m / 2.0,
            result.rear_left_kg,
            truck.nominal_rear_wheel_kg,
            True,
            rear_full * (1.0 - result.rear_right_share),
        ),
        (
            "прав.",
            x_front,
            truck.track_front_m / 2.0,
            result.front_right_kg,
            truck.nominal_front_wheel_kg,
            False,
            front_full * result.front_right_share,
        ),
        (
            "лев.",
            x_front,
            -truck.track_front_m / 2.0,
            result.front_left_kg,
            truck.nominal_front_wheel_kg,
            False,
            front_full * (1.0 - result.front_right_share),
        ),
    )

    for _, x_axle, y_wheel, kg, nominal, dual, full_kg in wheels:
        # Перегруз = 100·(kg/номинал − 1); при cargo_mass ≤ 0 — NaN.
        overload = 100.0 * (kg / nominal - 1.0) if nominal > 0.0 else float("nan")
        if cargo_mass <= 0.0:
            overload = float("nan")
        color = _ZONE_COLORS[_wheel_zone(overload, truck)]
        if dual:
            # Сдвоенная пара: два прямоугольника со смещением ±(tire_w/2 + gap/2).
            offset = tire_w / 2.0 + dual_gap / 2.0
            for delta in (-offset, offset):
                ax.add_patch(
                    Rectangle(
                        (x_axle - wheel_len / 2.0, y_wheel + delta - tire_w / 2.0),
                        wheel_len,
                        tire_w,
                        fc=color,
                        ec="0.25",
                        lw=1.2,
                        zorder=5,
                    )
                )
        else:
            ax.add_patch(
                Rectangle(
                    (x_axle - wheel_len / 2.0, y_wheel - single_w / 2.0),
                    wheel_len,
                    single_w,
                    fc=color,
                    ec="0.25",
                    lw=1.4,
                    zorder=5,
                )
            )
        # Текст на колесе: только доля в полной массе, %.
        ax.text(
            x_axle,
            y_wheel,
            _wheel_pct(full_kg),
            ha="center",
            va="center",
            fontsize=10 if not dual else 9,
            fontweight="bold",
            color="0.1",
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75),
            zorder=6,
        )

    # Оси мостов: пунктир в пределах кузова + колея + подпись сверху в цвете оси.
    label_box = dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85)
    # Мини-шкалы внизу: ширина и отступы в долях длины кузова, чтобы шкалы
    # не упирались в правый край и не слипались подписями на стыке (80|20).
    body_len = float(truck.x_limit_m)
    scale_x_rear, scale_x_front, scale_width = _mini_scale_layout(body_len)
    for x_axle, name, color, track, share in (
        (
            x_rear,
            "Задний мост",
            "tab:green",
            truck.track_rear_m,
            result.balance_rear_pct,
        ),
        (
            x_front,
            "Передний мост",
            "tab:purple",
            truck.track_front_m,
            result.balance_front_pct,
        ),
    ):
        # Пунктир оси — только в пределах кузова (±half_w), не вылезает за край.
        ax.plot(
            [x_axle, x_axle],
            [-half_w, half_w],
            color=color,
            ls="--",
            lw=1.6,
            zorder=3,
        )
        # Подпись моста — сверху самосвала, в цвет своей оси.
        if axle_scales:
            name_label = name
        else:
            name_label = f"{name} {share:.1f}%" if np.isfinite(share) else name
        ax.text(
            x_axle,
            -half_w - 0.20,
            name_label,
            ha="center",
            va="bottom",
            fontsize=9,
            color=color,
            fontweight="bold",
            bbox=label_box,
            zorder=7,
        )
        half_track = track / 2.0
        ax.plot(
            [x_axle, x_axle],
            [-half_track, half_track],
            color="0.1",
            lw=4.0,
            solid_capstyle="butt",
            zorder=4,
        )
        ax.text(
            x_axle,
            0.0,
            f"колея {track:.2f} м",
            ha="center",
            va="center",
            fontsize=8,
            color="0.25",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
            zorder=7,
        )
        if axle_scales:
            # Шкала моста — ПОД колёсами (ось Y инвертирована: +y внизу).
            x_scale = scale_x_rear if name.startswith("Зад") else scale_x_front
            _mini_axle_scale(
                ax,
                x_scale,
                half_w + 0.95,
                share,
                name,
                truck,
                width=scale_width,
            )
    ax.axhline(0.0, color="0.5", ls="-.", lw=1.0, zorder=3)

    # Легенда: зоны баланса/ЦМ + цвета колёс по перегрузу + ЦМ.
    handles: list = [
        span_x,
        span_y,
        Patch(fc=_ZONE_COLORS["green"], ec="0.4", label="перегруз ≤0%"),
        Patch(
            fc=_ZONE_COLORS["yellow"], ec="0.4", label=f"≤{truck.wheel_warn_pct:.0f}%"
        ),
        Patch(fc=_ZONE_COLORS["red"], ec="0.4", label=f">{truck.wheel_warn_pct:.0f}%"),
    ]
    # Идеальный и итоговый ЦМ + стрелка ΔX/ΔY.
    ideal_x = truck.ideal_com_x_m
    ideal_y = truck.ideal_com_y_m
    total_x = result.total_com_x_m
    total_y = result.total_com_y_m
    if np.isfinite(ideal_x) and np.isfinite(total_x) and np.isfinite(total_y):
        handles.append(
            ax.plot(
                ideal_x,
                ideal_y,
                "o",
                ms=11,
                color="deepskyblue",
                mec="navy",
                zorder=7,
                label="Идеальный ЦМ",
            )[0]
        )
        handles.append(
            ax.plot(
                total_x,
                total_y,
                "x",
                ms=14,
                mew=2.5,
                color="red",
                zorder=7,
                label="Итоговый ЦМ (вычисл.)",
            )[0]
        )
        if abs(total_x - ideal_x) + abs(total_y - ideal_y) > 0.05:
            ax.annotate(
                (
                    f"ΔX = {result.com_delta_x_m:+.2f} м, "
                    f"ΔY = {result.com_delta_y_m:+.2f} м"
                ),
                (0.5 * (ideal_x + total_x), 0.5 * (ideal_y + total_y)),
                textcoords="offset points",
                xytext=(0, 12),
                ha="center",
                color="crimson",
                fontsize=8,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75),
                zorder=7,
            )
    _legend_below(ax, fs=legend_fs, ncol=4, dy=legend_dy, handles=handles)
    ax.set_xlabel(_X_LABEL)
    ax.set_ylabel(_Y_LABEL)
    ax.set_xlim(-0.6, frame.rear_y_m + 0.55)
    # Низ расширен: шкалы + тики + легенда под колёсами.
    ax.set_ylim(-half_w - 1.0, half_w + 2.5)
    ax.invert_yaxis()  # правый борт (+Y) внизу — как при взгляде сверху
    ax.set_aspect("equal")
    ax.grid(True, ls=":", alpha=0.4)


# --------------------------------------------------------------------------- #
#  5. Дашборд v2                                                              #
# --------------------------------------------------------------------------- #
def _build_section_figure(
    hm: HeightMap,
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    cross: bool,
    title: str,
    outline: BodyOutline | None,
) -> Figure:
    """Один лист дашборда: разрез вдоль/поперёк + шкала баланса."""
    fig = Figure(figsize=(16.0, 8.0))
    FigureCanvasAgg(fig)
    grid = fig.add_gridspec(
        2,
        1,
        height_ratios=(9.0, 1.35),
        hspace=0.60,
        left=0.07,
        right=0.985,
        top=0.90,
        bottom=0.10,
    )
    ax = fig.add_subplot(grid[0])
    scale = fig.add_subplot(grid[1])
    if cross:
        _draw_cross(
            ax,
            hm,
            result,
            frame,
            truck,
            outline=outline,
            legend_fs=8.0,
            legend_ncol=4,
        )
        ax.set_title("Разрез поперёк (вид сзади)", fontsize=11)
    else:
        _draw_section(
            ax,
            hm,
            result,
            frame,
            truck,
            outline=outline,
            legend_fs=8.0,
            legend_ncol=4,
        )
        ax.set_title("Разрез вдоль", fontsize=11)
    _balance_scale(
        scale,
        result.balance_front_pct,
        truck,
        caption="Шкала баланса передней оси, %",
    )
    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold")
    return fig


def _build_wheels_figure(
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    title: str,
    outline: BodyOutline | None,
) -> Figure:
    """Третий лист дашборда: схема колёс с мини-шкалами мостов."""
    fig = Figure(figsize=(14.0, 9.8))
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.05, 0.20, 0.92, 0.72])
    # Третий лист всегда схематичный: ровный прямоугольник по bbox модели,
    # без зависимости от body.ply и RDP-упрощения.
    del outline
    _draw_wheels(
        ax,
        result,
        frame,
        truck,
        outline=None,
        legend_fs=8.5,
        axle_scales=True,
        legend_dy=-0.12,
    )
    ax.set_title("Колёса: нагрузка и перегруз", fontsize=11)
    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold")
    return fig


def build_dashboard_figures(
    hm: HeightMap,
    result: AnalysisResult,
    frame: BodyFrame,
    truck: TruckConfig,
    *,
    title: str = "",
    outline: BodyOutline | None = None,
) -> tuple[Figure, Figure, Figure]:
    """Три объекта matplotlib: разрез вдоль, поперёк и колёса.

    Фигуры не сохраняются и не закрываются — это делает вызывающая сторона.
    """
    return (
        _build_section_figure(
            hm,
            result,
            frame,
            truck,
            cross=False,
            title=title,
            outline=outline,
        ),
        _build_section_figure(
            hm,
            result,
            frame,
            truck,
            cross=True,
            title=title,
            outline=outline,
        ),
        _build_wheels_figure(result, frame, truck, title=title, outline=outline),
    )

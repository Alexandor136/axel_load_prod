"""Типы данных, конфигурация и параметры публичного API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .calc import AnalysisResult

# --- Воксельная сетка пайплайна LoadCapacityFactor_KAS -----------------------
# В PLY лежат ИНДЕКСЫ вокселей: метры = origin + индекс * size.
VOXEL_SIZE_M = 0.04
VOXEL_INDENTS_M = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class TruckConfig:
    """Паспортные параметры и пороги самосвала.

    Все линейные размеры — в метрах, массы — в килограммах,
    проценты — в диапазоне 0..100, если не указано иное.
    """

    # Тип/модель самосвала: BELAZ_7558, CAT785B и т.п.
    model: str = "BELAZ_7558"
    # База, м: расстояние между передним и задним мостами.
    wheelbase_m: float = 4.70
    # Расстояние от заднего края кузова до заднего моста, м.
    rear_axle_from_rear_m: float = 2.85
    # Колея передней оси, м: расстояние между центрами передних колёс.
    track_front_m: float = 4.30
    # Колея задней оси, м: расстояние между центрами задних колёс.
    track_rear_m: float = 3.70
    # Масса порожнего самосвала, кг.
    empty_weight_kg: float = 74_000.0
    # Номинальная грузоподъёмность, кг.
    payload_kg: float = 90_000.0
    # Доля передней оси порожнего самосвала, 0..1.
    empty_front_pct: float = 0.509
    # Целевая доля передней оси при загрузке, %.
    loaded_front_target_pct: float = 33.0
    # Идеальная доля передней оси Komatsu, %.
    ideal_front_pct: float = 33.6
    # Нижняя граница зелёной зоны баланса, %.
    green_min_pct: float = 30.0
    # Верхняя граница зелёной зоны баланса, %.
    green_max_pct: float = 36.0
    # Нижняя граница красной зоны баланса, %.
    front_min_pct: float = 28.0
    # Верхняя граница красной зоны баланса, %.
    front_max_pct: float = 38.0
    # Максимально допустимый payload, % от номинала.
    payload_max_pct: float = 120.0
    # Минимальная масса груза для расчёта, кг.
    min_load_kg: float = 1_000.0
    # Порог перегруза колеса, %: жёлтый до порога, красный выше.
    wheel_warn_pct: float = 10.0
    # Допустимое боковое смещение ЦМ, м.
    lateral_limit_m: float = 0.30
    # Высота ЦМ порожнего самосвала, м (для маркера общего ЦМ).
    empty_com_z_m: float = 2.40
    # Верхняя граница X кузова; задаётся из bbox модели.
    x_limit_m: float = 9.629

    @property
    def front_axle_from_rear_m(self) -> float:
        """Расстояние от заднего края кузова до переднего моста."""
        return self.rear_axle_from_rear_m + self.wheelbase_m

    @property
    def ideal_rear_pct(self) -> float:
        """Идеальная доля заднего моста Komatsu: 100% − передняя."""
        return 100.0 - self.ideal_front_pct

    @property
    def payload_max_kg(self) -> float:
        """120% от номинальной грузоподъёмности (Komatsu)."""
        return self.payload_kg * self.payload_max_pct / 100.0

    @property
    def gross_weight_kg(self) -> float:
        """Полная масса: порожний самосвал + номинальный груз."""
        return self.empty_weight_kg + self.payload_kg

    @property
    def empty_rear_pct(self) -> float:
        """Доля задней оси порожнего самосвала, 0..1."""
        return 1.0 - self.empty_front_pct

    @property
    def empty_com_y_m(self) -> float:
        """ЦМ порожнего самосвала по Y: ось симметрии."""
        return 0.0

    @property
    def empty_com_x_m(self) -> float:
        """ЦМ порожнего самосвала от заднего края кузова."""
        return self.rear_axle_from_rear_m + self.empty_front_pct * self.wheelbase_m

    @property
    def ideal_com_x_m(self) -> float:
        """Идеальный итоговый ЦМ: передняя ось = ideal_front_pct."""
        return (
            self.rear_axle_from_rear_m + self.ideal_front_pct / 100.0 * self.wheelbase_m
        )

    @property
    def ideal_com_y_m(self) -> float:
        """Идеальный итоговый ЦМ по Y — ось симметрии."""
        return 0.0

    @property
    def nominal_front_axle_kg(self) -> float:
        """Номинал передней оси ТОЛЬКО на груз: паспорт 33% − порожний 50.9%."""
        return (
            self.gross_weight_kg * self.loaded_front_target_pct / 100.0
            - self.empty_weight_kg * self.empty_front_pct
        )

    @property
    def nominal_rear_axle_kg(self) -> float:
        """Номинал задней оси ТОЛЬКО на груз: паспорт 67% − порожний 49.1%."""
        return (
            self.gross_weight_kg * (100.0 - self.loaded_front_target_pct) / 100.0
            - self.empty_weight_kg * self.empty_rear_pct
        )

    @property
    def nominal_front_wheel_kg(self) -> float:
        """Номинал переднего колеса для грузовой нагрузки."""
        return self.nominal_front_axle_kg / 2.0

    @property
    def nominal_rear_wheel_kg(self) -> float:
        """Номинал заднего колеса для грузовой нагрузки."""
        return self.nominal_rear_axle_kg / 2.0


@dataclass(frozen=True)
class BodyFrame:
    """Связь координат модели (как в PLY) и координат ТЗ.

    Модель BELAZ (core_data/vehicles_models/BELAZ, bbox из models_description.json):
      x_model ∈ [0, 5.883]  — поперёк кузова;
      y_model ∈ [0, 9.629]  — вдоль кузова, y_model = 0 ПЕРЕД, y_model max ЗАД;
      z_model ∈ [0, 5.637]  — вверх, днище ≈ 2.64 м.

    ТЗ: X — от заднего борта вперёд к кабине, Y — от оси симметрии,
    Y > 0 — правая сторона по ходу движения, Z — вверх.
    """

    rear_y_m: float = 9.629
    width_m: float = 5.883
    y_sign: float = 1.0
    voxel_size_m: float = VOXEL_SIZE_M
    origin_m: tuple[float, float, float] = (-1.0, -1.0, -1.0)

    @property
    def center_x_model_m(self) -> float:
        """Продольная ось симметрии кузова в координатах модели."""
        return self.width_m / 2.0

    def centers(self, indices: np.ndarray) -> np.ndarray:
        """Центры вокселей по индексам (N, 2|3) -> (N, 2|3) метры."""
        idx = np.asarray(indices, dtype=np.float64)
        origin = np.asarray(self.origin_m, dtype=np.float64)[: idx.shape[-1]]
        return origin + (idx + 0.5) * self.voxel_size_m

    def to_spec(
        self, x_model: np.ndarray, y_model: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Модель -> ТЗ: X (от заднего борта к кабине), Y (поперёк, >0 вправо)."""
        x_spec = self.rear_y_m - np.asarray(y_model, dtype=np.float64)
        y_spec = (
            np.asarray(x_model, dtype=np.float64) - self.center_x_model_m
        ) * self.y_sign
        return x_spec, y_spec


@dataclass(frozen=True)
class HeightMap:
    """Карта высот в координатах ТЗ (одна строка на колонку вокселей)."""

    x: np.ndarray
    y: np.ndarray
    h: np.ndarray
    z_floor: np.ndarray
    dx: float
    dy: float
    n_raw: int
    n_dropped_negative: int
    n_dropped_no_floor: int
    log_volume_m3: float | None
    approx_source: str = ""

    @property
    def volume_m3(self) -> float:
        """Объём груза, м³ (= Σ m_ij / ρ)."""
        return float(np.sum(self.h) * self.dx * self.dy)

    @property
    def is_empty(self) -> bool:
        """True, если в карте нет ни одной колонки."""
        return self.h.size == 0


@dataclass(frozen=True)
class Columns:
    """Сырые колонки рейса в ИНДЕКСАХ вокселей."""

    top_xy: np.ndarray
    top_z: np.ndarray
    floor_xy: np.ndarray
    floor_z: np.ndarray
    approx_source: str = ""


@dataclass(frozen=True)
class BodyOutline:
    """Огибающие кузова в координатах ТЗ для трёх проекций."""

    side_x: np.ndarray
    side_z_top: np.ndarray
    side_z_bot: np.ndarray
    cross_y: np.ndarray
    cross_z_top: np.ndarray
    cross_z_bot: np.ndarray
    top_x: np.ndarray
    top_y_min: np.ndarray
    top_y_max: np.ndarray


@dataclass(frozen=True)
class ProcessParams:
    """Параметры одного вызова process/compute."""

    cell_size_m: float = 0.04
    density_kg_m3: float = 2600.0
    validate: bool = True
    title: str = ""


@dataclass(frozen=True)
class Computation:
    """Результат расчёта без привязки к файлам."""

    result: AnalysisResult
    height_map: HeightMap
    outline: BodyOutline | None
    frame: BodyFrame
    truck: TruckConfig
    params: ProcessParams

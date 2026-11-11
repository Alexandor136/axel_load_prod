"""Встроенный усреднённый конфиг самосвала 90-го класса.

Единицы в ``AVERAGE_CONFIG`` намеренно оставлены «как в источнике»:
проценты записаны ДОЛЯМИ (0.3225 вместо 32.25), кроме ``empty_front_pct``,
которая уже является долей. В ``TruckConfig`` проценты — диапазон 0..100,
доля передней оси порожнего — 0..1. Нормализация выполняется один раз
в ``average_truck_config()``.
"""

from __future__ import annotations

from .errors import ConfigError
from .schemas import TruckConfig

AVERAGE_MODEL_TYPE = "AVERAGE_90T_CLASS"

AVERAGE_CONFIG: dict[str, float | str] = {
    "model": AVERAGE_MODEL_TYPE,
    "wheelbase_m": 4.598,
    "rear_axle_from_rear_m": 2.996,
    "front_axle_from_rear_m": 7.594,
    "track_front_m": 4.197,
    "track_rear_m": 3.682,
    "empty_weight_kg": 72_921.0,
    "payload_kg": 91_255.0,
    "gross_weight_kg": 164_176.0,
    "empty_front_pct": 0.465,
    "empty_rear_pct": 0.535,
    "loaded_front_target_pct": 0.3225,
    "loaded_rear_target_pct": 0.6775,
    "empty_com_x_m": 5.134,
    "empty_com_y_m": 0.0,
    # Справочные значения: противоречат процентным целям (6.111 даёт 67.75%
    # на переднюю ось вместо 32.25%), поэтому в расчёте НЕ используются.
    "loaded_com_x_m": 6.111,
    "payload_com_target_x_m": 6.886,
    "green_min_pct": 0.30,
    "green_max_pct": 0.36,
    "front_min_pct": 0.28,
    "front_max_pct": 0.38,
    "payload_max_pct": 1.20,
    "min_load_kg": 1_000.0,
    "wheel_warn_pct": 0.10,
    "lateral_limit_m": 0.30,
    "empty_com_z_m": 2.40,
    "x_limit_m": 9.629,
}

_TOLERANCE = 1e-3


def _c(key: str) -> float:
    """Числовое значение из AVERAGE_CONFIG."""
    return float(AVERAGE_CONFIG[key])


def _close(left: float, right: float, key: str) -> None:
    if abs(left - right) > _TOLERANCE:
        raise ConfigError(
            f"AVERAGE_CONFIG: {key} рассогласован ({left:.6f} != {right:.6f})"
        )


def _check_invariants(truck: TruckConfig) -> None:
    """Проверяет, что конфиг внутренне согласован."""
    _close(
        truck.rear_axle_from_rear_m + truck.wheelbase_m,
        _c("front_axle_from_rear_m"),
        "front_axle_from_rear_m",
    )
    _close(
        truck.empty_weight_kg + truck.payload_kg,
        _c("gross_weight_kg"),
        "gross_weight_kg",
    )
    _close(
        truck.empty_front_pct + _c("empty_rear_pct"),
        1.0,
        "empty_rear_pct",
    )
    _close(
        truck.loaded_front_target_pct + _c("loaded_rear_target_pct") * 100.0,
        100.0,
        "loaded_rear_target_pct",
    )
    _close(
        truck.rear_axle_from_rear_m + truck.empty_front_pct * truck.wheelbase_m,
        _c("empty_com_x_m"),
        "empty_com_x_m",
    )


def average_truck_config(*, x_limit_m: float | None = None) -> TruckConfig:
    """Собирает ``TruckConfig`` из усреднённого конфига.

    Args:
        x_limit_m: верхняя граница X кузова; по умолчанию 9.629 из конфига.
            API подставляет фактический ``frame.rear_y_m`` из облака кузова.

    Returns:
        Проверенный по инвариантам ``TruckConfig``.
    """
    loaded_front = _c("loaded_front_target_pct") * 100.0
    truck = TruckConfig(
        model=str(AVERAGE_CONFIG["model"]),
        wheelbase_m=_c("wheelbase_m"),
        rear_axle_from_rear_m=_c("rear_axle_from_rear_m"),
        track_front_m=_c("track_front_m"),
        track_rear_m=_c("track_rear_m"),
        empty_weight_kg=_c("empty_weight_kg"),
        payload_kg=_c("payload_kg"),
        empty_front_pct=_c("empty_front_pct"),
        loaded_front_target_pct=loaded_front,
        ideal_front_pct=loaded_front,
        green_min_pct=_c("green_min_pct") * 100.0,
        green_max_pct=_c("green_max_pct") * 100.0,
        front_min_pct=_c("front_min_pct") * 100.0,
        front_max_pct=_c("front_max_pct") * 100.0,
        payload_max_pct=_c("payload_max_pct") * 100.0,
        min_load_kg=_c("min_load_kg"),
        wheel_warn_pct=_c("wheel_warn_pct") * 100.0,
        lateral_limit_m=_c("lateral_limit_m"),
        empty_com_z_m=_c("empty_com_z_m"),
        x_limit_m=_c("x_limit_m") if x_limit_m is None else float(x_limit_m),
    )
    _check_invariants(truck)
    return truck

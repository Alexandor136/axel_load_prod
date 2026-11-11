"""Расчёт массы, центра масс и распределения нагрузки на оси (ТЗ, п. 4–12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .schemas import HeightMap, TruckConfig


@dataclass(frozen=True)
class AnalysisResult:
    """Итоги рейса."""

    model: str
    cargo_mass_kg: float
    cargo_volume_m3: float
    cargo_com_x_m: float
    cargo_com_y_m: float
    cargo_com_z_m: float
    total_mass_kg: float
    total_com_x_m: float
    total_com_y_m: float
    total_com_z_m: float
    # Нагрузка на оси/колёса — ТОЛЬКО груз (ТЗ, п. 7, по ячейкам груза):
    # % — доля от массы груза.
    front_axle_kg: float
    rear_axle_kg: float
    front_pct: float
    rear_pct: float
    # Баланс полной массы (самосвал + груз) для зон/идеала Komatsu
    balance_front_pct: float = float("nan")
    balance_rear_pct: float = float("nan")
    # Итоговый ЦМ: идеальная позиция и отклонения по осям X/Y
    com_ideal_x_m: float = float("nan")
    com_ideal_y_m: float = float("nan")
    com_delta_x_m: float = float("nan")
    com_delta_y_m: float = float("nan")
    # зона Horus Mine: green | yellow | red | unknown
    balance_level: str = "unknown"
    balance_message: str = ""
    ideal_front_pct: float = 33.6
    front_deviation_pp: float = float("nan")  # передняя ось, процентные пункты
    front_deviation_pct: float = float("nan")  # относительное отклонение, %
    front_left_kg: float = float("nan")
    front_right_kg: float = float("nan")
    rear_left_kg: float = float("nan")
    rear_right_kg: float = float("nan")
    front_right_share: float = 0.5
    rear_right_share: float = 0.5
    front_overload_pct: float = float("nan")
    rear_overload_pct: float = float("nan")
    nominal_front_wheel_kg: float = float("nan")
    nominal_rear_wheel_kg: float = float("nan")
    warnings: list[str] = field(default_factory=list)
    is_within_norm: bool = True
    quality: dict[str, Any] = field(default_factory=dict)
    # Уклон дороги, % (0 — ровная площадка). Положительный — подъём к кабине.
    slope_pct: float = 0.0

    @property
    def ideal_rear_pct(self) -> float:
        """Идеальная доля задней оси, %."""
        return 100.0 - self.ideal_front_pct

    @property
    def status(self) -> str:
        """Статус из quality (ok | warning | critical | overload | empty | …)."""
        return str(self.quality.get("status", "ok"))

    def to_dict(self) -> dict[str, Any]:
        """Компактный JSON-контракт результата расчёта.

        Оставлены только масса/ЦМ, нагрузки, зоны, предупреждения и
        минимальный блок качества. Справочные константы и внутренние
        доли колёс сюда не попадают — они есть в params.json.
        """
        quality: dict[str, Any] = {
            "status": self.quality.get("status", "ok"),
        }
        vehicle_model = self.quality.get("vehicle_model")
        if vehicle_model:
            quality["vehicle_model"] = vehicle_model
        for key in ("volume_rel_error", "volume_mismatch"):
            if key in self.quality:
                quality[key] = self.quality[key]
        notes = [note for note in self.quality.get("notes", []) if note]
        if notes:
            quality["notes"] = notes

        return {
            "model": self.model,
            "slope_pct": round(self.slope_pct, 2),
            "cargo_mass_kg": round(self.cargo_mass_kg, 2),
            "cargo_volume_m3": round(self.cargo_volume_m3, 4),
            "cargo_com": {
                "x_m": round(self.cargo_com_x_m, 4),
                "y_m": round(self.cargo_com_y_m, 4),
                "z_m": round(self.cargo_com_z_m, 4),
            },
            "total_mass_kg": round(self.total_mass_kg, 2),
            "total_com": {
                "x_m": round(self.total_com_x_m, 4),
                "y_m": round(self.total_com_y_m, 4),
                "z_m": round(self.total_com_z_m, 4),
            },
            "com_deviation": {
                "ideal_x_m": round(self.com_ideal_x_m, 4),
                "ideal_y_m": round(self.com_ideal_y_m, 4),
                "delta_x_m": round(self.com_delta_x_m, 4),
                "delta_y_m": round(self.com_delta_y_m, 4),
            },
            "axle_load": {
                "front_kg": round(self.front_axle_kg, 1),
                "rear_kg": round(self.rear_axle_kg, 1),
                "front_pct": round(self.front_pct, 2),
                "rear_pct": round(self.rear_pct, 2),
            },
            "balance": {
                "level": self.balance_level,
                "message": self.balance_message,
                "ideal_front_pct": round(self.ideal_front_pct, 2),
                "ideal_rear_pct": round(self.ideal_rear_pct, 2),
                "front_pct": round(self.balance_front_pct, 2),
                "rear_pct": round(self.balance_rear_pct, 2),
                "front_deviation_pp": round(self.front_deviation_pp, 2),
                "front_deviation_pct": round(self.front_deviation_pct, 2),
            },
            "wheels": {
                "front_left_kg": round(self.front_left_kg, 1),
                "front_right_kg": round(self.front_right_kg, 1),
                "rear_left_kg": round(self.rear_left_kg, 1),
                "rear_right_kg": round(self.rear_right_kg, 1),
                "nominal_front_kg": round(self.nominal_front_wheel_kg, 1),
                "nominal_rear_kg": round(self.nominal_rear_wheel_kg, 1),
                "front_overload_pct": round(self.front_overload_pct, 2),
                "rear_overload_pct": round(self.rear_overload_pct, 2),
            },
            "warnings": list(self.warnings),
            "is_within_norm": self.is_within_norm,
            "quality": quality,
        }


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """Взвешенное среднее Σ(v·w)/Σw; NaN при нулевой сумме весов."""
    total = float(np.sum(weights))
    if total <= 0.0:
        return float("nan")
    return float(np.sum(values * weights) / total)


def _right_share(y_com: float, track_m: float) -> float:
    """Доля правой стороны оси: 0.5 + y / колея, clamp [0, 1]."""
    if track_m <= 0.0 or not np.isfinite(y_com):
        return 0.5
    return float(np.clip(0.5 + y_com / track_m, 0.0, 1.0))


def _side_shares(axle_kg: float, y_com: float, track_m: float) -> tuple[float, float]:
    """Кг на (левом, правом) колесе оси: доля правой по рычагу Y."""
    right_share = _right_share(y_com, track_m)
    return axle_kg * (1.0 - right_share), axle_kg * right_share


def _worst_overload(
    wheel_kg: tuple[float, float], nominal_kg: float, data_ok: bool
) -> float:
    """Худший перегруз среди колёс оси: 100·(W/номинал − 1)."""
    if not data_ok or nominal_kg <= 0.0:
        return float("nan")
    return max(100.0 * (kg / nominal_kg - 1.0) for kg in wheel_kg)


def analyze(
    height_map: HeightMap,
    truck: TruckConfig,
    density_kg_m3: float,
    *,
    slope_pct: float = 0.0,
) -> AnalysisResult:
    """m_ij = ρ · dx · dy · H_ij; ЦМ, нагрузка на оси и предупреждения.

    Args:
        height_map: карта высот груза в координатах ТЗ.
        truck: паспортные параметры и пороги самосвала.
        density_kg_m3: плотность груза, кг/м³.
        slope_pct: продольный уклон дороги, % (i = tg α). Положительный —
            подъём к кабине (перед выше), 0 — ровная площадка. Уклон
            переносит часть нагрузки через высоту ЦМ:
            ``pct_перед = 100·(d − h·i)/L``.
    """
    if not np.isfinite(slope_pct):
        raise ValueError("slope_pct должен быть конечным числом")
    if abs(slope_pct) > 100.0:
        raise ValueError("slope_pct должен быть в диапазоне −100…100 %")
    # i = tg α ≈ sin α для малых углов; в формулах используется напрямую.
    grade = slope_pct / 100.0

    warnings: list[str] = []
    notes: list[str] = []

    # Отбрасываем нечисловые высоты (NaN/inf) перед расчётом масс.
    h = height_map.h
    finite = np.isfinite(h)
    if not bool(np.all(finite)):
        notes.append(f"отброшено нечисловых высот: {int(np.sum(~finite))}")
        h = h[finite]
        x = height_map.x[finite]
        y = height_map.y[finite]
        z_floor = height_map.z_floor[finite]
    else:
        x, y, z_floor = height_map.x, height_map.y, height_map.z_floor

    # Масса каждой ячейки и итоговые масса/объём груза (ТЗ, п. 4).
    cell_mass = density_kg_m3 * height_map.dx * height_map.dy * h
    cargo_mass = float(np.sum(cell_mass))
    cargo_volume = float(np.sum(h) * height_map.dx * height_map.dy)

    # Достаточно ли данных: есть объём и масса выше порога min_load_kg.
    empty_ok = cargo_mass > 0.0 and h.size > 0
    data_ok = empty_ok and cargo_mass > truck.min_load_kg
    if not data_ok:
        warnings.append("Недостаточно данных для оценки груза")

    # ЦМ груза: взвешенные средние по высоте колонок (X, Y — плоскость,
    # Z — середина колонки над днищем).
    if empty_ok:
        cargo_x = _weighted_mean(x, h)
        cargo_y = _weighted_mean(y, h)
        cargo_z = _weighted_mean(z_floor + h / 2.0, h)
    else:
        cargo_x = cargo_y = cargo_z = float("nan")

    # ЦМ полной массы: смесь порожнего ЦМ и ЦМ груза по массам.
    total_mass = truck.empty_weight_kg + cargo_mass
    if empty_ok:
        total_x = (
            truck.empty_weight_kg * truck.empty_com_x_m + cargo_mass * cargo_x
        ) / total_mass
        total_y = (
            truck.empty_weight_kg * truck.empty_com_y_m + cargo_mass * cargo_y
        ) / total_mass
        total_z = (
            truck.empty_weight_kg * truck.empty_com_z_m + cargo_mass * cargo_z
        ) / total_mass
    else:
        total_x, total_y, total_z = (
            truck.empty_com_x_m,
            truck.empty_com_y_m,
            truck.empty_com_z_m,
        )

    # Нагрузка на оси — ТОЛЬКО груз (ТЗ, п. 7): рычаг ЦМ груза от заднего моста.
    # % — доля от массы груза (без веса самосвала).
    # Уклон: проекция веса груза сдвигает нагрузку на h·i в сторону заднего моста.
    if empty_ok and cargo_mass > 0.0:
        lever_cargo = cargo_x - truck.rear_axle_from_rear_m - cargo_z * grade
        front_kg = cargo_mass * lever_cargo / truck.wheelbase_m
        rear_kg = cargo_mass - front_kg
        front_pct = 100.0 * front_kg / cargo_mass
        rear_pct = 100.0 * rear_kg / cargo_mass
    else:
        front_kg = rear_kg = 0.0
        front_pct = rear_pct = 0.0

    # Баланс ПОЛНОЙ массы (самосвал + груз) — зоны Horus Mine / идеал Komatsu.
    # Уклон переносит нагрузку через высоту общего ЦМ: (d − h·i)/L.
    balance_front_pct = (
        100.0
        * (
            total_x
            - truck.rear_axle_from_rear_m
            - total_z * grade
        )
        / truck.wheelbase_m
    )
    balance_rear_pct = 100.0 - balance_front_pct
    level, message = _balance_zone(balance_front_pct, truck)
    ideal_rear = 100.0 - truck.ideal_front_pct
    front_dev_pp = (
        balance_front_pct - truck.ideal_front_pct if data_ok else float("nan")
    )

    # Итоговый ЦМ: идеальная позиция и отклонения по осям X/Y
    com_ideal_x = truck.ideal_com_x_m
    com_ideal_y = truck.ideal_com_y_m
    com_delta_x = total_x - com_ideal_x
    com_delta_y = total_y - com_ideal_y

    # Колёса: распределение по сторонам от ЦМ по Y (рычаг по колее моста):
    # доля_прав = 0.5 + y_ЦМ / колея, ограничена [0, 1].
    y_split = cargo_y if (empty_ok and np.isfinite(cargo_y)) else 0.0
    front_left, front_right = _side_shares(front_kg, y_split, truck.track_front_m)
    rear_left, rear_right = _side_shares(rear_kg, y_split, truck.track_rear_m)
    front_right_share = _right_share(y_split, truck.track_front_m)
    rear_right_share = _right_share(y_split, truck.track_rear_m)

    nominal_front_wheel = truck.nominal_front_wheel_kg
    nominal_rear_wheel = truck.nominal_rear_wheel_kg
    front_overload = _worst_overload(
        (front_left, front_right), nominal_front_wheel, data_ok
    )
    rear_overload = _worst_overload(
        (rear_left, rear_right), nominal_rear_wheel, data_ok
    )

    if data_ok:
        if level in ("yellow", "red"):
            warnings.append(message)
        if cargo_y < -truck.lateral_limit_m:
            warnings.append("Груз сильно смещён влево")
        elif cargo_y > truck.lateral_limit_m:
            warnings.append("Груз сильно смещён вправо")
        if np.isfinite(cargo_x) and not (0.0 <= cargo_x <= truck.x_limit_m):
            warnings.append("Центр масс груза вне кузова")
            notes.append(
                f"x_load = {cargo_x:.3f} м выходит за [0, {truck.x_limit_m}] м"
            )
    if cargo_mass > truck.payload_max_kg:
        warnings.append(
            f"Превышает предел {truck.payload_max_pct:.0f}% от номинала "
            f"({truck.payload_max_kg / 1000:.0f} т)"
        )
    elif cargo_mass > truck.payload_kg:
        warnings.append(
            f"Превышает грузоподъёмность {truck.payload_kg / 1000:.0f} т (номинал)"
        )

    if grade != 0.0:
        notes.append(
            f"учтён уклон дороги {slope_pct:+.1f} % "
            f"({'подъём' if grade > 0 else 'спуск'} к кабине)"
        )

    # Статус рейса: priorитет — нет данных, красная зона/предел, перелёт
    # номинала, жёлтая зона, норма.
    if not data_ok:
        status = "empty"
    elif level == "red" or cargo_mass > truck.payload_max_kg:
        status = "critical"
    elif cargo_mass > truck.payload_kg:
        status = "overload"
    elif level == "yellow":
        status = "warning"
    else:
        status = "ok"

    # Итоговый отчёт: метаданные качества, справочные пороги и контроль объёма.
    quality: dict[str, Any] = {
        "status": status,
        "notes": notes,
        "cells": int(h.size),
        "cells_dropped_negative": height_map.n_dropped_negative,
        "cells_dropped_no_floor": height_map.n_dropped_no_floor,
        "volume_from_log_m3": height_map.log_volume_m3,
        "density_kg_m3": density_kg_m3,
        "approx_source": height_map.approx_source,
        # Справочные константы — чтобы отчёт был самодостаточен.
        "reference": {
            "ideal_front_pct": truck.ideal_front_pct,
            "ideal_rear_pct": round(ideal_rear, 2),
            "green_band_pct": [truck.green_min_pct, truck.green_max_pct],
            "red_band_pct": [truck.front_min_pct, truck.front_max_pct],
            "payload_nominal_kg": truck.payload_kg,
            "payload_max_pct": truck.payload_max_pct,
            "payload_max_kg": truck.payload_max_kg,
            "nominal_front_wheel_kg": truck.nominal_front_wheel_kg,
            "nominal_rear_wheel_kg": truck.nominal_rear_wheel_kg,
            "wheel_warn_pct": truck.wheel_warn_pct,
            "ideal_com_x_m": round(truck.ideal_com_x_m, 4),
            "ideal_com_y_m": round(truck.ideal_com_y_m, 4),
            "track_front_m": truck.track_front_m,
            "track_rear_m": truck.track_rear_m,
        },
    }
    # Контроль объёма: карта высот vs log.json; расхождение >1% и >0.05 м³ — флаг.
    if height_map.log_volume_m3:
        delta = abs(cargo_volume - height_map.log_volume_m3) / height_map.log_volume_m3
        quality["volume_rel_error"] = round(delta, 6)
        quality["volume_mismatch"] = bool(
            delta > 0.01 and abs(cargo_volume - height_map.log_volume_m3) > 0.05
        )
        if quality["volume_mismatch"]:
            quality["notes"].append(
                f"объём карты {cargo_volume:.3f} м³ расходится с log.json "
                f"({height_map.log_volume_m3:.3f} м³) на {delta * 100:.2f}%"
            )

    return AnalysisResult(
        model=truck.model,
        cargo_mass_kg=cargo_mass,
        cargo_volume_m3=cargo_volume,
        cargo_com_x_m=cargo_x,
        cargo_com_y_m=cargo_y,
        cargo_com_z_m=cargo_z,
        total_mass_kg=total_mass,
        total_com_x_m=total_x,
        total_com_y_m=total_y,
        total_com_z_m=total_z,
        front_axle_kg=front_kg,
        rear_axle_kg=rear_kg,
        front_pct=front_pct,
        rear_pct=rear_pct,
        balance_front_pct=balance_front_pct,
        balance_rear_pct=balance_rear_pct,
        com_ideal_x_m=com_ideal_x,
        com_ideal_y_m=com_ideal_y,
        com_delta_x_m=com_delta_x,
        com_delta_y_m=com_delta_y,
        balance_level=level if data_ok else "unknown",
        balance_message=message if data_ok else "",
        ideal_front_pct=truck.ideal_front_pct,
        front_deviation_pp=front_dev_pp,
        front_deviation_pct=(
            100.0 * front_dev_pp / truck.ideal_front_pct
            if truck.ideal_front_pct and np.isfinite(front_dev_pp)
            else float("nan")
        ),
        front_left_kg=front_left,
        front_right_kg=front_right,
        rear_left_kg=rear_left,
        rear_right_kg=rear_right,
        front_right_share=front_right_share,
        rear_right_share=rear_right_share,
        front_overload_pct=front_overload,
        rear_overload_pct=rear_overload,
        nominal_front_wheel_kg=nominal_front_wheel,
        nominal_rear_wheel_kg=nominal_rear_wheel,
        warnings=warnings,
        is_within_norm=bool(level == "green" and not warnings),
        quality=quality,
        slope_pct=slope_pct,
    )


def _balance_zone(front_pct: float, truck: TruckConfig) -> tuple[str, str]:
    """Зона Horus Mine по доле передней оси: (уровень, сообщение)."""
    if front_pct < truck.front_min_pct:
        return "red", "Груз сильно смещён назад"
    if front_pct > truck.front_max_pct:
        return "red", "Груз сильно смещён вперёд"
    if front_pct < truck.green_min_pct or front_pct > truck.green_max_pct:
        return "yellow", "Отклонение от нормы"
    return "green", ""

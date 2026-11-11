"""Публичный API: кейс нового формата -> три Figure + отчёт по нагрузке."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from .calc import AnalysisResult, analyze
from .case import BODY_MODEL_REL, ENTIRE_MASS_REL, CaseData, read_case
from .config import average_truck_config
from .render import build_dashboard_figures
from .schemas import Computation, ProcessParams, TruckConfig

# Имя файла отчёта в каталоге результата.
REPORT_NAME = "axle_load_report.json"

# Порядок колёс в JSON строго фиксирован: 1 — переднее левое, 2 — переднее
# правое, 3 — заднее правое, 4 — заднее левое.
WHEEL_ORDER: tuple[tuple[str, str], ...] = (
    ("1", "front_left"),
    ("2", "front_right"),
    ("3", "rear_right"),
    ("4", "rear_left"),
)


def _wheel_percent(kg: float, total_mass_kg: float) -> float:
    """Доля колеса в полной массе, % (0.0, если масса неизвестна)."""
    if not np.isfinite(total_mass_kg) or total_mass_kg <= 0.0:
        return 0.0
    return round(100.0 * float(kg) / total_mass_kg, 1)


def _wheel_percents(result: AnalysisResult) -> dict[str, list]:
    """Проценты нагрузки на колёса от ПОЛНОЙ массы (порожний + груз)."""
    total = result.total_mass_kg
    zero = {key: [name, 0.0] for key, name in WHEEL_ORDER}
    if not np.isfinite(total) or total <= 0.0 or not np.isfinite(
        result.balance_front_pct
    ):
        return zero

    front_full = total * result.balance_front_pct / 100.0
    rear_full = total * result.balance_rear_pct / 100.0
    front_right_share = result.front_right_share
    rear_right_share = result.rear_right_share

    kg = {
        "1": front_full * (1.0 - front_right_share),
        "2": front_full * front_right_share,
        "3": rear_full * rear_right_share,
        "4": rear_full * (1.0 - rear_right_share),
    }
    return {
        key: [name, _wheel_percent(kg[key], total)] for key, name in WHEEL_ORDER
    }


def report_payload(result: AnalysisResult) -> dict:
    """Отчёт по нагрузке: проценты по осям и по колёсам.

    Проценты осей и колёс считаются от ПОЛНОЙ массы (порожний самосвал +
    груз). Заднее сдвоенное колесо — половина задней оси, без повторного
    деления на 2.

    Уклон дороги в отчёт не входит: он влияет на сами проценты, но не
    является результатом расчёта.

    Returns:
        Словарь вида::

            {
              "axles": {"front": {"pct": 41.5}, "rear": {"pct": 58.5}},
              "wheels": {"1": ["front_left", 23.5], ...},
            }
    """
    total = result.total_mass_kg
    front = result.balance_front_pct
    valid = np.isfinite(total) and total > 0.0 and np.isfinite(front)
    if valid:
        front_pct = round(float(front), 1)
        rear_pct = round(100.0 - front_pct, 1)
    else:
        front_pct = rear_pct = 0.0
    return {
        "axles": {
            "front": {"pct": front_pct},
            "rear": {"pct": rear_pct},
        },
        "wheels": _wheel_percents(result),
    }


def compute(
    case: CaseData | str | Path,
    *,
    truck: TruckConfig | None = None,
    density_kg_m3: float = 2600.0,
    cell_size_m: float = 0.04,
    y_sign: float = 1.0,
    validate: bool = True,
    slope_pct: float = 0.0,
    title: str = "",
) -> Computation:
    """Считает массы, ЦМ и распределение нагрузки без сохранения файлов.

    Args:
        case: ``CaseData`` или путь к каталогу кейса.
        truck: готовая конфигурация самосвала; иначе ``AVERAGE_CONFIG``
            (встроенный ``AVERAGE_90T_CLASS``).
        density_kg_m3: плотность груза, кг/м³.
        cell_size_m: размер вокселя, м.
        y_sign: +1 — Y > 0 справа, -1 — зеркально.
        validate: проверки входных данных.
        slope_pct: продольный уклон дороги, % (0 — ровная площадка,
            положительный — подъём к кабине).
        title: заголовок для фигур; пустая строка — без заголовка.

    Returns:
        ``Computation`` с результатом и контекстом расчёта.
    """
    data = (
        case
        if isinstance(case, CaseData)
        else read_case(
            case,
            cell_size_m=cell_size_m,
            y_sign=y_sign,
            validate=validate,
        )
    )
    truck = truck or average_truck_config(x_limit_m=data.frame.rear_y_m)

    result = analyze(data.height_map, truck, density_kg_m3, slope_pct=slope_pct)
    result.quality.update(
        {
            "source": f"{ENTIRE_MASS_REL.as_posix()} + {BODY_MODEL_REL.as_posix()}",
            "columns": data.columns,
            "volume_from_entire_mass_m3": round(data.volume_m3, 4),
            "body_rear_y_m": round(data.frame.rear_y_m, 4),
            "body_width_m": round(data.frame.width_m, 4),
            "slope_pct": round(float(slope_pct), 2),
        }
    )
    return Computation(
        result=result,
        height_map=data.height_map,
        outline=data.outline,
        frame=data.frame,
        truck=truck,
        params=ProcessParams(
            cell_size_m=cell_size_m,
            density_kg_m3=density_kg_m3,
            validate=validate,
            title=title,
        ),
    )


def process(
    case: CaseData | str | Path,
    *,
    truck: TruckConfig | None = None,
    density_kg_m3: float = 2600.0,
    cell_size_m: float = 0.04,
    y_sign: float = 1.0,
    validate: bool = True,
    slope_pct: float = 0.0,
    title: str = "",
) -> tuple[Figure, Figure, Figure, dict]:
    """Считает нагрузку и возвращает три фигуры и отчёт по нагрузке.

    Порядок фигур: продольный разрез, поперечный разрез, схема колёс.
    Фигуры не сохраняются и не закрываются — это делает вызывающая сторона.

    Returns:
        ``(fig1, fig2, fig3, report)``, где ``report`` — словарь вида
        ``{"axles": {...}, "wheels": {...}}``
        (см. :func:`report_payload`).
    """
    computation = compute(
        case,
        truck=truck,
        density_kg_m3=density_kg_m3,
        cell_size_m=cell_size_m,
        y_sign=y_sign,
        validate=validate,
        slope_pct=slope_pct,
        title=title,
    )
    figures = build_dashboard_figures(
        computation.height_map,
        computation.result,
        computation.frame,
        computation.truck,
        title=computation.params.title,
        outline=computation.outline,
    )
    return (*figures, report_payload(computation.result))


def save_report_json(payload: dict, path: str | Path) -> Path:
    """Пишет отчёт по нагрузке (UTF-8, отступ 2)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

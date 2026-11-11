"""CLI: кейс нового формата -> три JPEG и axle_load_report.json."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .api import REPORT_NAME, compute, report_payload
from .calc import AnalysisResult
from .case import is_case_dir, read_case
from .config import AVERAGE_CONFIG, average_truck_config
from .errors import AxleLoadError
from .jsonio import write_ply
from .render import build_dashboard_figures, save_jpeg
from .schemas import TruckConfig

DEFAULT_OUT_NAME = "new_result"


def _prepare_console() -> None:
    """Не падать на символах, которых нет в кодовой странице консоли Windows.

    Русская консоль Windows работает в cp1251/cp866: часть символов (например,
    «³» или «→») в них отсутствует, и ``print`` завершается ``UnicodeEncodeError``.
    Заменяем такие символы, а не роняем весь прогон.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace")
    except (ValueError, OSError):
        # Поток уже закрыт или перенаправлен — печатать всё равно сможем.
        pass



def _pct(key: str) -> float:
    """Процентный дефолт из AVERAGE_CONFIG (там проценты записаны долями)."""
    return float(AVERAGE_CONFIG[key]) * 100.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axle_load",
        description="Масса, центр масс и распределение нагрузки на оси по облакам "
        "нового формата: 5_LoadEstimation/0_entire_mass.ply + "
        "4_B2M/result_b2m.ply.",
    )
    default_out = Path.cwd() / DEFAULT_OUT_NAME
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help="каталог кейса или каталог с кейсами (по умолчанию текущая директория)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help=f"корневой каталог результатов (по умолчанию {default_out})",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help=f"явный путь к {REPORT_NAME} (для одного кейса)",
    )
    parser.add_argument(
        "--density", type=float, default=2600.0, help="плотность груза, кг/м3"
    )
    parser.add_argument(
        "--slope-pct",
        type=float,
        default=0.0,
        help="продольный уклон дороги, %%: 0 — ровно, >0 — подъём к кабине",
    )
    parser.add_argument(
        "--y-sign",
        type=float,
        choices=(-1.0, 1.0),
        default=1.0,
        help="+1: Y>0 — правая сторона по ходу, -1 — зеркально",
    )
    parser.add_argument(
        "--wheelbase",
        type=float,
        default=float(AVERAGE_CONFIG["wheelbase_m"]),
        help="база, м",
    )
    parser.add_argument(
        "--rear-axle-x",
        type=float,
        default=float(AVERAGE_CONFIG["rear_axle_from_rear_m"]),
        help="задний мост от заднего края кузова, м",
    )
    parser.add_argument(
        "--ideal-front",
        type=float,
        default=_pct("loaded_front_target_pct"),
        help="идеальная доля передней оси, %%",
    )
    parser.add_argument(
        "--green-min",
        type=float,
        default=_pct("green_min_pct"),
        help="нижняя граница зелёной зоны, %%",
    )
    parser.add_argument(
        "--green-max",
        type=float,
        default=_pct("green_max_pct"),
        help="верхняя граница зелёной зоны, %%",
    )
    parser.add_argument(
        "--front-min",
        type=float,
        default=_pct("front_min_pct"),
        help="мин. доля на переднюю ось, %%",
    )
    parser.add_argument(
        "--front-max",
        type=float,
        default=_pct("front_max_pct"),
        help="макс. доля на переднюю ось, %%",
    )
    parser.add_argument(
        "--payload-max-pct",
        type=float,
        default=_pct("payload_max_pct"),
        help="максимум от номинальной грузоподъёмности, %%",
    )
    parser.add_argument(
        "--lateral-limit",
        type=float,
        default=float(AVERAGE_CONFIG["lateral_limit_m"]),
        help="допустимое смещение ЦМ по Y, м",
    )
    parser.add_argument(
        "--min-load-kg",
        type=float,
        default=float(AVERAGE_CONFIG["min_load_kg"]),
        help="ниже этой массы — «Недостаточно данных»",
    )
    parser.add_argument(
        "--empty-com-z",
        type=float,
        default=float(AVERAGE_CONFIG["empty_com_z_m"]),
        help="высота ЦМ порожнего авто (для разреза), м",
    )
    parser.add_argument("--no-plot", action="store_true", help="не строить изображения")
    parser.add_argument(
        "--report",
        action="store_true",
        help="дополнительно писать полный report.json (по умолчанию не пишется)",
    )
    parser.add_argument(
        "--save-inputs",
        action="store_true",
        help="сохранить копии облаков в <out>/<кейс>/inputs",
    )
    return parser


def _iter_cases(paths: list[Path]) -> list[Path]:
    """Каталоги кейсов: сам путь или все кейсы под ним (рекурсивно)."""
    found: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw)
        if is_case_dir(path):
            candidates = [path]
        elif path.is_dir():
            candidates = sorted(
                {p.parent.parent for p in path.rglob("result_b2m.ply")}
            )
        else:
            candidates = []
        for candidate in candidates:
            if not is_case_dir(candidate):
                continue
            key = candidate.resolve()
            if key not in seen:
                seen.add(key)
                found.append(candidate)
    return found


def _build_truck(args: argparse.Namespace, x_limit_m: float) -> TruckConfig:
    """AVERAGE_CONFIG + переопределения CLI-флагами."""
    return replace(
        average_truck_config(x_limit_m=x_limit_m),
        wheelbase_m=args.wheelbase,
        rear_axle_from_rear_m=args.rear_axle_x,
        ideal_front_pct=args.ideal_front,
        green_min_pct=args.green_min,
        green_max_pct=args.green_max,
        front_min_pct=args.front_min,
        front_max_pct=args.front_max,
        payload_max_pct=args.payload_max_pct,
        lateral_limit_m=args.lateral_limit,
        min_load_kg=args.min_load_kg,
        empty_com_z_m=args.empty_com_z,
    )


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@dataclass
class CaseReport:
    """Итог обработки одного кейса для сводки в консоли."""

    name: str
    result: AnalysisResult
    payload: dict
    outputs: list[Path]


def process_case(case_dir: Path, args: argparse.Namespace) -> CaseReport:
    """Один кейс: расчёт, три JPEG, axle_load_report.json, опционально report.json."""
    data = read_case(case_dir, cell_size_m=0.04, y_sign=args.y_sign)
    truck = _build_truck(args, data.frame.rear_y_m)
    computation = compute(
        data,
        truck=truck,
        density_kg_m3=args.density,
        slope_pct=args.slope_pct,
    )
    payload = report_payload(computation.result)

    out_dir = args.out / case_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    json_path = args.json if args.json is not None else out_dir / REPORT_NAME
    outputs.append(_write_json(json_path, payload))

    if args.report:
        report = computation.result.to_dict()
        report["wheels"] = payload["wheels"]
        report["axles"] = payload["axles"]
        outputs.append(_write_json(out_dir / "report.json", report))

    if args.save_inputs:
        inputs = out_dir / "inputs"
        hm = computation.height_map
        outputs.append(
            write_ply(
                inputs / "cargo_top.ply",
                np.column_stack([hm.x, hm.y, hm.z_floor + hm.h]),
            )
        )
        outputs.append(write_ply(inputs / "body_model.ply", data.body_points))

    if not args.no_plot:
        figures = build_dashboard_figures(
            computation.height_map,
            computation.result,
            computation.frame,
            computation.truck,
            title=computation.params.title,
            outline=computation.outline,
        )
        outputs.extend(save_jpeg(figures, out_dir))
        for figure in figures:
            plt.close(figure)

    return CaseReport(
        name=case_dir.name,
        result=computation.result,
        payload=payload,
        outputs=outputs,
    )


def _print_row(report: CaseReport) -> None:
    """Строка сводки: масса, объём, оси, колёса и (если задан) уклон."""
    result = report.result
    wheels = report.payload["wheels"]
    wheel_pct = " / ".join(f"{wheels[key][1]:.1f}%" for key in ("1", "2", "3", "4"))
    slope = report.result.slope_pct
    slope_part = f" | уклон {slope:+.1f} %" if slope else ""
    print(
        f"{report.name}: масса {result.cargo_mass_kg / 1000:.1f} т "
        f"| объём {result.cargo_volume_m3:.2f} м3 "
        f"| оси {result.balance_front_pct:.1f}/{result.balance_rear_pct:.1f} % "
        f"| колёса {wheel_pct}{slope_part}"
    )


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI: разбор аргументов и обработка найденных кейсов."""
    _prepare_console()
    args = _build_parser().parse_args(argv)

    cases = _iter_cases(list(args.paths))
    if not cases:
        print(
            "кейсы не найдены: нужны 5_LoadEstimation/0_entire_mass.ply "
            "и 4_B2M/result_b2m.ply",
            file=sys.stderr,
        )
        return 2

    reports: list[CaseReport] = []
    for case_dir in cases:
        try:
            report = process_case(case_dir, args)
        except (AxleLoadError, ValueError) as exc:
            print(f"{case_dir.name}: ошибка — {exc}", file=sys.stderr)
            continue
        for path in report.outputs:
            print(f"{case_dir.name}: {path}")
        reports.append(report)

    if reports:
        print()
        for report in reports:
            _print_row(report)

    return 0 if reports else 1


if __name__ == "__main__":
    raise SystemExit(main())

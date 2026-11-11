"""Пример встраивания axle_load: каталог кейса -> три JPEG + axle_load_report.json.

Запуск:

    python examples/run_process.py <каталог кейса> [<каталог результатов>]

Уклон дороги (%, >0 — подъём к кабине) берётся из ``AXLE_LOAD_SLOPE_PCT``,
по умолчанию 0. Без аргументов путь к кейсу берётся из ``AXLE_LOAD_CASE``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt

# Пример запускается как скрипт: корень пакета (prod_version) добавляем в путь,
# чтобы не требовать установки или PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from axle_load import (  # noqa: E402
    REPORT_NAME,
    process,
    save_jpeg,
    save_report_json,
)


def main(argv: list[str] | None = None) -> int:
    """Считает кейс и сохраняет три листа дашборда и отчёт по нагрузке."""
    args = sys.argv[1:] if argv is None else argv
    raw_case = args[0] if args else os.environ.get("AXLE_LOAD_CASE")
    if not raw_case:
        print(
            "укажите каталог кейса: python examples/run_process.py <кейс> [<out>]",
            file=sys.stderr,
        )
        return 2

    case_dir = Path(raw_case)
    out = Path(args[1]) if len(args) > 1 else Path(__file__).resolve().parent / "out"
    slope_pct = float(os.environ.get("AXLE_LOAD_SLOPE_PCT", "0"))

    # process читает оба PLY кейса и возвращает фигуры + отчёт по нагрузке.
    fig1, fig2, fig3, report = process(case_dir, slope_pct=slope_pct)
    try:
        paths = save_jpeg((fig1, fig2, fig3), out)
        json_path = save_report_json(report, out / REPORT_NAME)
    finally:
        # Фигуры не закрываются внутри API — это делает вызывающая сторона.
        for figure in (fig1, fig2, fig3):
            plt.close(figure)

    for path in (*paths, json_path):
        print(f"сохранено: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI: дефолты из AVERAGE_CONFIG, уклон, флаг --report."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from axle_load.__main__ import (
    _build_parser,
    _prepare_console,
    _print_row,
    main,
    process_case,
)

from helpers import make_case


def test_defaults_from_average_config() -> None:
    args = _build_parser().parse_args([])
    assert args.wheelbase == pytest.approx(4.598)
    assert args.rear_axle_x == pytest.approx(2.996)
    assert args.ideal_front == pytest.approx(32.25)
    assert args.green_min == pytest.approx(30.0)
    assert args.green_max == pytest.approx(36.0)
    assert args.front_min == pytest.approx(28.0)
    assert args.front_max == pytest.approx(38.0)
    assert args.payload_max_pct == pytest.approx(120.0)
    assert args.lateral_limit == pytest.approx(0.30)
    assert args.min_load_kg == pytest.approx(1000.0)
    assert args.empty_com_z == pytest.approx(2.40)
    assert args.density == pytest.approx(2600.0)
    # Уклон по умолчанию не влияет на расчёт, report.json не пишется.
    assert args.slope_pct == pytest.approx(0.0)
    assert args.report is False


def test_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_cli_processes_case(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    out = tmp_path / "out"
    assert main([str(case.path), "--out", str(out), "--no-plot"]) == 0

    payload = json.loads(
        (out / "case" / "axle_load_report.json").read_text(encoding="utf-8")
    )
    assert set(payload) == {"axles", "wheels"}
    assert set(payload["wheels"]) == {"1", "2", "3", "4"}
    assert payload["axles"]["front"]["pct"] + payload["axles"]["rear"]["pct"] == 100.0
    # report.json без флага не создаётся.
    assert not (out / "case" / "report.json").exists()
    assert not (out / "case" / "wheels.json").exists()


def test_cli_report_flag(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    out = tmp_path / "out"
    assert main([str(case.path), "--out", str(out), "--no-plot", "--report"]) == 0

    report = json.loads((out / "case" / "report.json").read_text(encoding="utf-8"))
    assert report["model"] == "AVERAGE_90T_CLASS"
    assert report["slope_pct"] == 0.0
    assert "wheels" in report
    assert "axles" in report


def test_cli_slope_changes_axles(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    flat_out = tmp_path / "flat"
    slope_out = tmp_path / "slope"
    assert main([str(case.path), "--out", str(flat_out), "--no-plot"]) == 0
    assert (
        main(
            [
                str(case.path),
                "--out",
                str(slope_out),
                "--no-plot",
                "--slope-pct",
                "10",
            ]
        )
        == 0
    )

    flat = json.loads(
        (flat_out / "case" / "axle_load_report.json").read_text(encoding="utf-8")
    )
    sloped = json.loads(
        (slope_out / "case" / "axle_load_report.json").read_text(encoding="utf-8")
    )
    assert "slope_pct" not in sloped
    assert sloped["axles"]["front"]["pct"] < flat["axles"]["front"]["pct"]
    assert sloped["axles"]["rear"]["pct"] > flat["axles"]["rear"]["pct"]


def test_cli_without_cases_returns_2(tmp_path: Path) -> None:
    assert main([str(tmp_path), "--out", str(tmp_path / "out")]) == 2


def test_summary_survives_cp1251_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сводка печатается в консоль Windows (cp1251) без UnicodeEncodeError."""
    case = make_case(tmp_path)
    args = _build_parser().parse_args(
        [str(case.path), "--out", str(tmp_path / "out"), "--no-plot"]
    )
    report = process_case(case.path, args)

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1251", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    _prepare_console()
    _print_row(report)
    stream.flush()

    text = buffer.getvalue().decode("cp1251")
    assert "объём" in text
    assert "колёса" in text

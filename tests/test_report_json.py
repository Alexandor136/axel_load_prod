"""Контракт ``axle_load_report.json``: уклон, оси и проценты по колёсам."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from axle_load.api import REPORT_NAME, compute, report_payload, save_report_json
from axle_load.calc import AnalysisResult

from helpers import make_case


def _result(tmp_path: Path) -> AnalysisResult:
    return compute(make_case(tmp_path).path).result


def test_report_file_name() -> None:
    assert REPORT_NAME == "axle_load_report.json"


def test_contract_example(tmp_path: Path) -> None:
    """32.25/67.75 на осях и равные стороны → 16.1 / 16.1 / 33.9 / 33.9."""
    result = replace(
        _result(tmp_path),
        total_mass_kg=164_176.0,
        balance_front_pct=32.25,
        balance_rear_pct=67.75,
        front_right_share=0.5,
        rear_right_share=0.5,
        slope_pct=0.0,
    )
    payload = report_payload(result)
    assert set(payload) == {"axles", "wheels"}
    assert payload["axles"] == {"front": {"pct": 32.2}, "rear": {"pct": 67.8}}
    assert payload["wheels"] == {
        "1": ["front_left", 16.1],
        "2": ["front_right", 16.1],
        "3": ["rear_right", 33.9],
        "4": ["rear_left", 33.9],
    }


def test_order_and_labels(tmp_path: Path) -> None:
    wheels = report_payload(_result(tmp_path))["wheels"]
    assert list(wheels) == ["1", "2", "3", "4"]
    assert [wheels[key][0] for key in wheels] == [
        "front_left",
        "front_right",
        "rear_right",
        "rear_left",
    ]


def test_percentages_sum_to_100(tmp_path: Path) -> None:
    payload = report_payload(_result(tmp_path))
    wheels_total = sum(value[1] for value in payload["wheels"].values())
    axles_total = payload["axles"]["front"]["pct"] + payload["axles"]["rear"]["pct"]
    assert wheels_total == pytest.approx(100.0, abs=0.3)
    assert axles_total == pytest.approx(100.0, abs=1e-9)


def test_dual_rear_wheel_is_half_axle(tmp_path: Path) -> None:
    """Задняя пара — половина задней оси, без повторного деления на 2."""
    result = replace(
        _result(tmp_path),
        total_mass_kg=164_176.0,
        balance_front_pct=32.25,
        balance_rear_pct=67.75,
        front_right_share=0.5,
        rear_right_share=0.5,
    )
    wheels = report_payload(result)["wheels"]
    # Задняя ось 67.75 % → каждое заднее колесо 33.875 % полной массы.
    assert wheels["3"][1] == wheels["4"][1] == pytest.approx(33.875, abs=0.05)
    # Отношение заднего колеса к переднему — 67.75/32.25, а не ровно 2.
    # Допуск 0.1 п.п. — проценты округлены до одного знака.
    assert wheels["3"][1] == pytest.approx(wheels["2"][1] * (67.75 / 32.25), abs=0.1)


def test_slope_not_in_report(tmp_path: Path) -> None:
    """Уклон влияет на проценты, но в отчёт не попадает."""
    result = replace(_result(tmp_path), slope_pct=8.0)
    assert "slope_pct" not in report_payload(result)


def test_zero_mass_is_zero_not_nan(tmp_path: Path) -> None:
    payload = report_payload(replace(_result(tmp_path), total_mass_kg=0.0))
    assert all(value[1] == 0.0 for value in payload["wheels"].values())
    assert payload["axles"] == {"front": {"pct": 0.0}, "rear": {"pct": 0.0}}


def test_save_report_json(tmp_path: Path) -> None:
    path = save_report_json(
        {"axles": {}, "wheels": {"1": ["front_left", 16.1]}},
        tmp_path / "out" / REPORT_NAME,
    )
    assert path.is_file()
    assert path.name == "axle_load_report.json"
    text = path.read_text(encoding="utf-8")
    assert "front_left" in text
    assert "slope_pct" not in text

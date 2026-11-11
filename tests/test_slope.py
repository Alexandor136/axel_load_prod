"""Уклон дороги: формула переноса нагрузки и неизменность расчёта при 0 %."""

from __future__ import annotations

from pathlib import Path

import pytest

from axle_load.api import compute, report_payload

from helpers import make_case


def _computation(tmp_path: Path, slope_pct: float = 0.0):
    return compute(make_case(tmp_path).path, slope_pct=slope_pct)


def test_zero_slope_is_baseline(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    base = compute(case.path).result
    zero = compute(case.path, slope_pct=0.0).result
    assert zero.slope_pct == 0.0
    assert zero.balance_front_pct == pytest.approx(base.balance_front_pct)
    assert zero.front_axle_kg == pytest.approx(base.front_axle_kg)
    assert zero.total_com_z_m == pytest.approx(base.total_com_z_m)


def test_balance_formula_with_slope(tmp_path: Path) -> None:
    """pct_перед = 100·(d − h·i)/L для полной массы."""
    comp = _computation(tmp_path, slope_pct=8.0)
    result, truck = comp.result, comp.truck
    grade = 0.08
    expected = (
        100.0
        * (
            result.total_com_x_m
            - truck.rear_axle_from_rear_m
            - result.total_com_z_m * grade
        )
        / truck.wheelbase_m
    )
    assert result.balance_front_pct == pytest.approx(expected)
    assert result.balance_rear_pct == pytest.approx(100.0 - expected)


def test_cargo_axle_formula_with_slope(tmp_path: Path) -> None:
    """Нагрузка на оси только от груза — со своей высотой ЦМ."""
    comp = _computation(tmp_path, slope_pct=8.0)
    result, truck = comp.result, comp.truck
    grade = 0.08
    expected_front = (
        result.cargo_mass_kg
        * (
            result.cargo_com_x_m
            - truck.rear_axle_from_rear_m
            - result.cargo_com_z_m * grade
        )
        / truck.wheelbase_m
    )
    assert result.front_axle_kg == pytest.approx(expected_front)
    assert result.rear_axle_kg == pytest.approx(
        result.cargo_mass_kg - expected_front
    )


def test_uphill_moves_load_to_rear_axle(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    flat = compute(case.path).result
    uphill = compute(case.path, slope_pct=8.0).result

    assert uphill.slope_pct == 8.0
    assert uphill.balance_front_pct < flat.balance_front_pct
    assert uphill.front_axle_kg < flat.front_axle_kg
    assert uphill.balance_rear_pct > flat.balance_rear_pct


def test_downhill_moves_load_to_front_axle(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    flat = compute(case.path).result
    downhill = compute(case.path, slope_pct=-8.0).result

    assert downhill.balance_front_pct > flat.balance_front_pct
    assert downhill.front_axle_kg > flat.front_axle_kg


def test_slope_does_not_change_mass_or_com(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    flat = compute(case.path).result
    uphill = compute(case.path, slope_pct=8.0).result

    assert uphill.cargo_mass_kg == pytest.approx(flat.cargo_mass_kg)
    assert uphill.cargo_volume_m3 == pytest.approx(flat.cargo_volume_m3)
    assert uphill.cargo_com_x_m == pytest.approx(flat.cargo_com_x_m)
    assert uphill.cargo_com_z_m == pytest.approx(flat.cargo_com_z_m)


def test_slope_not_in_report(tmp_path: Path) -> None:
    payload = report_payload(_computation(tmp_path, slope_pct=10.0).result)
    assert "slope_pct" not in payload


@pytest.mark.parametrize("slope", [float("nan"), float("inf"), 150.0, -150.0])
def test_invalid_slope_rejected(tmp_path: Path, slope: float) -> None:
    case = make_case(tmp_path)
    with pytest.raises(ValueError):
        compute(case.path, slope_pct=slope)

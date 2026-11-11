"""AVERAGE_CONFIG: единицы, производные величины и проверка согласованности."""

from __future__ import annotations

import pytest

from axle_load.config import (
    AVERAGE_CONFIG,
    AVERAGE_MODEL_TYPE,
    average_truck_config,
)
from axle_load.errors import ConfigError


def test_model_and_normalized_percents() -> None:
    truck = average_truck_config()
    assert truck.model == AVERAGE_MODEL_TYPE == "AVERAGE_90T_CLASS"
    assert truck.loaded_front_target_pct == pytest.approx(32.25)
    assert truck.ideal_front_pct == pytest.approx(32.25)
    assert truck.green_min_pct == pytest.approx(30.0)
    assert truck.green_max_pct == pytest.approx(36.0)
    assert truck.front_min_pct == pytest.approx(28.0)
    assert truck.front_max_pct == pytest.approx(38.0)
    assert truck.payload_max_pct == pytest.approx(120.0)
    assert truck.wheel_warn_pct == pytest.approx(10.0)
    # Доля передней оси порожнего остаётся долей, а не процентом.
    assert truck.empty_front_pct == pytest.approx(0.465)


def test_geometry_and_masses() -> None:
    truck = average_truck_config()
    assert truck.wheelbase_m == pytest.approx(4.598)
    assert truck.rear_axle_from_rear_m == pytest.approx(2.996)
    assert truck.front_axle_from_rear_m == pytest.approx(7.594)
    assert truck.gross_weight_kg == pytest.approx(164_176.0)
    assert truck.empty_com_x_m == pytest.approx(5.134, abs=1e-3)
    assert truck.empty_rear_pct == pytest.approx(0.535)
    assert truck.ideal_rear_pct == pytest.approx(67.75)


def test_x_limit_override() -> None:
    """API подставляет фактическую длину кузова из облака."""
    assert average_truck_config(x_limit_m=12.5).x_limit_m == pytest.approx(12.5)
    assert average_truck_config().x_limit_m == pytest.approx(
        float(AVERAGE_CONFIG["x_limit_m"])
    )


def test_inconsistent_config_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AVERAGE_CONFIG сверяется сам с собой: 72 921 + 91 255 != 1 кг."""
    monkeypatch.setitem(AVERAGE_CONFIG, "gross_weight_kg", 1.0)
    with pytest.raises(ConfigError, match="gross_weight_kg"):
        average_truck_config()

"""Изменения в axle_load_3: без баннера предупреждений, проценты на колесо."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from axle_load.api import compute  # noqa: E402
from axle_load.render_impl import _build_wheels_figure, _mini_scale_layout  # noqa: E402

from helpers import make_case


def test_mini_scale_layout_keeps_gap_and_margins() -> None:
    """Шкалы под осями не слипаются подписями и не выходят за борт кузова."""
    rear_x, front_x, width = _mini_scale_layout(9.629)

    assert rear_x - width / 2.0 >= 0.0
    assert front_x + width / 2.0 <= 9.629
    gap = (front_x - width / 2.0) - (rear_x + width / 2.0)
    assert gap >= 0.5
    # Обе шкалы сдвинуты влево относительно своих мостов (2.996 и 7.594).
    assert rear_x < 2.996
    assert front_x < 7.594


def _computation(tmp_path: Path):
    return compute(make_case(tmp_path).path)


def test_no_warning_banner(tmp_path: Path) -> None:
    comp = _computation(tmp_path)
    bad = replace(
        comp.result,
        warnings=["Груз сильно смещён вперёд"],
        balance_message="Груз сильно смещён вперёд",
        quality={**comp.result.quality, "status": "critical"},
    )
    fig = _build_wheels_figure(bad, comp.frame, comp.truck, title="тест", outline=None)
    try:
        assert not any("Предупреждения" in text.get_text() for text in fig.texts)
    finally:
        plt.close(fig)


def test_dual_wheel_label_is_half_rear_axle(tmp_path: Path) -> None:
    comp = _computation(tmp_path)
    result = replace(
        comp.result,
        total_mass_kg=164_176.0,
        balance_front_pct=32.25,
        balance_rear_pct=67.75,
        front_right_share=0.5,
        rear_right_share=0.5,
    )
    fig = _build_wheels_figure(result, comp.frame, comp.truck, title="", outline=None)
    try:
        texts = [text.get_text() for text in fig.axes[0].texts]
    finally:
        plt.close(fig)

    assert "33.9%" in texts  # половина задней оси, а не 16.9%
    assert "16.1%" in texts  # переднее колесо целиком


def test_no_mass_units_on_wheels(tmp_path: Path) -> None:
    comp = _computation(tmp_path)
    fig = _build_wheels_figure(
        comp.result, comp.frame, comp.truck, title="", outline=None
    )
    try:
        texts = [text.get_text() for text in fig.axes[0].texts]
    finally:
        plt.close(fig)

    joined = "\n".join(texts)
    assert " кг" not in joined
    assert "ном." not in joined
    assert not any(text.strip().endswith(" т") for text in texts)
    assert any(text.endswith("%") for text in texts)


def test_no_suptitle_by_default(tmp_path: Path) -> None:
    """Пустой title — на схеме колёс нет заголовка «Средний самосвал 90 т»."""
    comp = _computation(tmp_path)
    fig = _build_wheels_figure(
        comp.result, comp.frame, comp.truck, title="", outline=None
    )
    try:
        assert not any(text.get_text() for text in fig.texts)
    finally:
        plt.close(fig)


def test_rear_wheels_sum_to_half_axle(tmp_path: Path) -> None:
    """Две подписи задней пары в сумме дают заднюю ось."""
    comp = _computation(tmp_path)
    result = replace(
        comp.result,
        total_mass_kg=164_176.0,
        balance_front_pct=32.25,
        balance_rear_pct=67.75,
        front_right_share=0.5,
        rear_right_share=0.5,
    )
    fig = _build_wheels_figure(result, comp.frame, comp.truck, title="", outline=None)
    try:
        values = [
            float(text.get_text().rstrip("%"))
            for text in fig.axes[0].texts
            if text.get_text().endswith("%")
        ]
    finally:
        plt.close(fig)
    assert sum(values) == pytest.approx(100.0, abs=0.2)

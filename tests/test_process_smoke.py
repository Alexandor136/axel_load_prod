"""Сквозной smoke-тест: process(case_dir) -> 3 Figure + отчёт по нагрузке."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from axle_load import process, save_jpeg, save_report_json  # noqa: E402

from helpers import make_case


def test_process_returns_three_figures_and_report(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    *figures, payload = process(case.path)

    try:
        assert len(figures) == 3
        assert set(payload) == {"axles", "wheels"}
        assert payload["axles"]["front"]["pct"] + payload["axles"]["rear"]["pct"] == 100.0
        assert list(payload["wheels"]) == ["1", "2", "3", "4"]
        assert payload["wheels"]["1"][0] == "front_left"
        assert payload["wheels"]["3"][0] == "rear_right"

        out = tmp_path / "outputs"
        paths = save_jpeg(tuple(figures), out)
        assert [path.name for path in paths] == [
            "axle_load_1.jpg",
            "axle_load_2.jpg",
            "axle_load_3.jpg",
        ]
        assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
    finally:
        for figure in figures:
            plt.close(figure)


def test_no_title_by_default(tmp_path: Path) -> None:
    """Заголовок «Средний самосвал 90 т» больше не рисуется."""
    case = make_case(tmp_path)
    *figures, _ = process(case.path)
    try:
        for figure in figures:
            assert not any(text.get_text() for text in figure.texts)
    finally:
        for figure in figures:
            plt.close(figure)


def test_save_report_json_roundtrip(tmp_path: Path) -> None:
    payload = {
        "axles": {"front": {"pct": 41.5}, "rear": {"pct": 58.5}},
        "wheels": {"1": ["front_left", 16.1]},
    }
    path = save_report_json(payload, tmp_path / "axle_load_report.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload

"""examples/run_process.py: пример встраивания работает на синтетическом кейсе."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from examples.run_process import main

from helpers import make_case


def test_example_writes_outputs(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    out = tmp_path / "out"

    assert main([str(case.path), str(out)]) == 0

    assert sorted(path.name for path in out.iterdir()) == [
        "axle_load_1.jpg",
        "axle_load_2.jpg",
        "axle_load_3.jpg",
        "axle_load_report.json",
    ]
    # report.json пример не пишет: это опция CLI (--report), а не API.
    assert not (out / "report.json").exists()


def test_example_without_case_returns_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("AXLE_LOAD_CASE", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2


def test_example_respects_slope_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = make_case(tmp_path)
    flat = tmp_path / "flat"
    sloped = tmp_path / "sloped"

    monkeypatch.delenv("AXLE_LOAD_SLOPE_PCT", raising=False)
    assert main([str(case.path), str(flat)]) == 0

    monkeypatch.setenv("AXLE_LOAD_SLOPE_PCT", "10")
    assert main([str(case.path), str(sloped)]) == 0

    flat_payload = json.loads(
        (flat / "axle_load_report.json").read_text(encoding="utf-8")
    )
    sloped_payload = json.loads(
        (sloped / "axle_load_report.json").read_text(encoding="utf-8")
    )
    assert sloped_payload["axles"]["front"]["pct"] < flat_payload["axles"]["front"]["pct"]

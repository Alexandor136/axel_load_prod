"""Схемы и изображения: три Figure и сохранение JPEG."""

from __future__ import annotations

import os
from pathlib import Path

from matplotlib.figure import Figure

from .render_impl import build_dashboard_figures

IMAGE_NAMES = (
    "axle_load_1.jpg",
    "axle_load_2.jpg",
    "axle_load_3.jpg",
)


def save_jpeg(
    figures: tuple[Figure, Figure, Figure],
    output_dir: str | Path,
    *,
    dpi: int = 150,
    quality: int = 90,
) -> tuple[Path, Path, Path]:
    """Сохраняет три фигуры с фиксированными именами и атомарной записью."""
    if len(figures) != len(IMAGE_NAMES):
        raise ValueError("нужно ровно три фигуры")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for figure, name in zip(figures, IMAGE_NAMES, strict=True):
        target = out / name
        tmp = out / f".{name}.tmp"
        try:
            figure.savefig(
                tmp,
                format="jpeg",
                dpi=dpi,
                bbox_inches="tight",
                pil_kwargs={"quality": quality},
            )
            os.replace(tmp, target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        paths.append(target)
    return paths[0], paths[1], paths[2]


__all__ = [
    "IMAGE_NAMES",
    "build_dashboard_figures",
    "save_jpeg",
]

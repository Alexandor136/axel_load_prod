"""PLY: чтение и запись облаков точек (ASCII и binary)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_PLY_TYPES: dict[str, str] = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}


@dataclass(frozen=True)
class PlyCloud:
    """Точечное облако из PLY: координаты и (опционально) цвет."""

    points: np.ndarray  # (N, 3) float64 — XYZ каждой точки
    colors: np.ndarray | None  # (N, 3) uint8 или None, если цвета нет

    def __len__(self) -> int:
        """Количество точек в облаке."""
        return int(self.points.shape[0])

    def select_color(self, rgb: tuple[int, int, int]) -> np.ndarray:
        """Маска точек с указанным цветом (RGB, 0..255)."""
        if self.colors is None:
            raise ValueError("в файле нет цвета")
        # Построчное сравнение трёх каналов → булева маска (N,).
        return np.all(self.colors == np.asarray(rgb, dtype=np.uint8), axis=1)


def read_ply(path: str | Path) -> PlyCloud:
    """Читает PLY (ascii или binary little/big endian) в облако точек.

    Формат PLY подразумевает плотную упаковку свойств без выравнивания,
    поэтому смещения полей считаются вручную.
    """
    path = Path(path)
    with path.open("rb") as fh:
        # Первая строка файла — обязательная сигнатура "ply".
        if fh.readline().strip() != b"ply":
            raise ValueError(f"{path}: это не PLY-файл")

        # Разбор заголовка: формат, число вершин, список свойств.
        fmt: str | None = None
        count = 0
        props: list[tuple[str, str]] = []
        in_vertex_element = False
        seen_element = False

        while True:
            raw = fh.readline()
            if not raw:
                raise ValueError(f"{path}: не найден end_header")
            line = raw.decode("ascii", errors="replace").strip()
            # Пустые строки, комментарии и obj_info — пропускаем.
            if not line or line.startswith("comment") or line.startswith("obj_info"):
                continue
            # "format <ascii|binary_little_endian|binary_big_endian> 1.0"
            if line.startswith("format"):
                fmt = line.split()[1]
                continue
            # "element vertex N" — начало элемента vertex; запоминаем размер.
            if line.startswith("element"):
                _, name, size = line.split()
                in_vertex_element = name == "vertex"
                seen_element = True
                if in_vertex_element:
                    count = int(size)
                continue
            # "property <type> <name>" — свойства; list-свойства не поддерживаются.
            if line.startswith("property"):
                if not seen_element:
                    raise ValueError(f"{path}: property до element")
                if not in_vertex_element:
                    continue
                parts = line.split()
                if parts[1] == "list":
                    raise ValueError(f"{path}: list-свойства не поддерживаются")
                props.append((parts[1], parts[2]))
                continue
            if line == "end_header":
                break

        if count == 0 or not props:
            raise ValueError(f"{path}: пустой vertex-элемент")

        # ASCII: таблица чисел, колонки сопоставляем по именам свойств.
        if fmt == "ascii":
            names = [name for _, name in props]
            data = np.loadtxt(fh, max_rows=count, dtype=np.float64, ndmin=2)
            if data.shape[0] != count or data.shape[1] != len(names):
                raise ValueError(
                    f"{path}: ожидалось {count} строк по {len(names)} колонок, "
                    f"получено {data.shape[0]}×{data.shape[1]}"
                )
            index = {name: i for i, name in enumerate(names)}
            for axis in ("x", "y", "z"):
                if axis not in index:
                    raise ValueError(f"{path}: нет координаты {axis!r}")
            points = data[:, [index["x"], index["y"], index["z"]]]
            rgb: np.ndarray | None = None
            for red, green, blue in (
                ("red", "green", "blue"),
                ("r", "g", "b"),
            ):
                if all(key in index for key in (red, green, blue)):
                    rgb = np.clip(
                        data[:, [index[red], index[green], index[blue]]], 0, 255
                    ).astype(np.uint8)
                    break
            return PlyCloud(points=np.ascontiguousarray(points), colors=rgb)

        # Поддерживается только binary PLY (ASCII обработан выше).
        if fmt not in ("binary_little_endian", "binary_big_endian"):
            raise ValueError(
                f"{path}: неизвестный формат PLY {fmt!r}"
            )

        # Сборка structured dtype: байтовый порядок + смещения без выравнивания.
        endian = "<" if fmt == "binary_little_endian" else ">"
        names: list[str] = []
        formats: list[str] = []
        offsets: list[int] = []
        itemsize = 0
        for type_name, prop_name in props:
            base = _PLY_TYPES.get(type_name)
            if base is None:
                raise ValueError(f"{path}: неизвестный тип {type_name!r}")
            names.append(prop_name)
            formats.append(base)
            offsets.append(itemsize)
            itemsize += np.dtype(base).itemsize

        dtype = np.dtype(
            {
                "names": names,
                "formats": [endian + f for f in formats],
                "offsets": offsets,
                "itemsize": itemsize,
            }
        )
        # Читаем весь payload разом; меньше count * itemsize — файл обрезан.
        payload = fh.read(count * itemsize)
        if len(payload) < count * itemsize:
            raise ValueError(f"{path}: обрезанные данные")

    # Интерпретация байтов как таблицы по собранному dtype.
    table = np.frombuffer(payload, dtype=dtype, count=count)
    for key in ("x", "y", "z"):
        if key not in names:
            raise ValueError(f"{path}: нет координаты {key!r}")
    # Столбцы x,y,z → массив (N, 3) float64.
    points = np.column_stack([table["x"], table["y"], table["z"]]).astype(np.float64)

    # Цвета опциональны: нужны все три канала red/green/blue.
    colors: np.ndarray | None = None
    if all(k in names for k in ("red", "green", "blue")):
        colors = np.column_stack([table["red"], table["green"], table["blue"]]).astype(
            np.uint8
        )

    return PlyCloud(points=points, colors=colors)


def write_ply(
    path: str | Path,
    points: np.ndarray,
    colors: np.ndarray | None = None,
) -> Path:
    """Пишет binary little-endian PLY с координатами (и опционально RGB).

    Запись атомарная: временный файл + os.replace. Пустые облака и NaN/inf
    запрещены — такой файл не нужен для воспроизведения кейса.
    """
    path = Path(path)
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points должен иметь форму (N, 3)")
    if pts.shape[0] == 0:
        raise ValueError("нельзя записать пустое облако")
    if not np.all(np.isfinite(pts)):
        raise ValueError("points содержит NaN или inf")

    cols: np.ndarray | None = None
    if colors is not None:
        raw = np.asarray(colors)
        if raw.shape != pts.shape:
            raise ValueError("colors должен иметь форму (N, 3)")
        if not np.issubdtype(raw.dtype, np.integer):
            raise ValueError("colors должен быть целочисленным RGB")
        if raw.size and (int(raw.min()) < 0 or int(raw.max()) > 255):
            raise ValueError("colors должен быть в диапазоне 0..255")
        cols = raw.astype(np.uint8)

    fields: list[tuple[str, str]] = [
        ("x", "<f8"),
        ("y", "<f8"),
        ("z", "<f8"),
    ]
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {pts.shape[0]}\n"
        "property double x\n"
        "property double y\n"
        "property double z\n"
    )
    if cols is not None:
        fields += [("red", "u1"), ("green", "u1"), ("blue", "u1")]
        header += "property uchar red\nproperty uchar green\nproperty uchar blue\n"
    header += "end_header\n"

    table = np.empty(pts.shape[0], dtype=fields)
    table["x"] = pts[:, 0]
    table["y"] = pts[:, 1]
    table["z"] = pts[:, 2]
    if cols is not None:
        table["red"] = cols[:, 0]
        table["green"] = cols[:, 1]
        table["blue"] = cols[:, 2]

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with tmp.open("wb") as fh:
            fh.write(header.encode("ascii"))
            table.tofile(fh)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return path

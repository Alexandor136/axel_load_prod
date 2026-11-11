# Алгоритм расчёта и встраивание API

Документ описывает, как `axle_load` считает массу груза, центр масс и
распределение нагрузки по осям и колёсам БелАЗ-7558: входные данные, формулы,
конфигурацию, выходные файлы и варианты встраивания в работающую систему.

- Пакет: `prod_version/axle_load/`
- Конфиг: `prod_version/axle_load/config.py` → словарь `AVERAGE_CONFIG`
- Точка входа CLI: `python -m axle_load <путь> [--out <каталог>]`

---

## 1. Назначение

По двум облакам точек восстановить объём и массу груза в кузове, найти центр
масс груза и самосвала, распределить нагрузку по осям и колёсам, сравнить
баланс с целевым `32.25 / 67.75 %` и вернуть три схемы + JSON-отчёт.

Тип самосвала фиксирован: встроенный `AVERAGE_90T_CLASS`. Внешние каталоги
моделей и `model_types.json` не нужны.

## 2. Входные данные

Каталог кейса:

```text
<кейс>/
├── 5_LoadEstimation/0_entire_mass.ply   # сплошной объём груза
└── 4_B2M/result_b2m.ply                 # кузов (красные) + скан (зелёные)
```

| Файл | Формат | Содержимое |
|---|---|---|
| `0_entire_mass.ply` | ASCII PLY, `x y z` | воксели груза; `x, y, z` — **индексы** вокселей 0,04 м |
| `result_b2m.ply` | ASCII PLY, `x y z red green blue` | метры модели; кузов — `(255, 0, 0)`, скан — `(0, 255, 0)` |

Начало воксельной сетки — `(−1, −1, −1)` м по всем осям (проверено по скану:
верх колонок совпадает с зелёными точками у 99,8 % колонок). Именно поэтому
`BodyFrame` собирается вручную, а не через `from_model_bbox`.

Система координат ТЗ: `X` — от заднего борта к кабине, `Y` — поперёк
(`Y > 0` вправо по ходу), `Z` — вверх от земли.

## 3. Конвейер расчёта

1. Проверить наличие обоих файлов кейса, иначе `MissingInputError`.
2. Прочитать `result_b2m.ply`, отобрать красные точки, взять их bbox:
   `width_m = max X`, `rear_y_m = max Y`.
3. Построить `BodyFrame(origin=(−1,−1,−1), voxel=0.04)` и перевести красные
   точки в ТЗ: `X = rear_y − y_model`, `Y = (x_model − width/2)·y_sign`.
4. Прочитать `0_entire_mass.ply`, сгруппировать воксели в колонки `(ix, iy)`:
   `z_floor = min z`, `z_top = max z`.
5. Проверить, что все колонки лежат внутри bbox кузова (`_check_inside_body`).
6. Построить карту высот `H_ij = (z_top − z_floor)·0.04` и координаты центров
   колонок в ТЗ.
7. Посчитать массу, объём, ЦМ, нагрузки, зоны (раздел 4).
8. Собрать три фигуры и JSON-отчёт (раздел 7).

## 4. Формулы

Обозначения:

| Символ | Смысл | Единица |
|---|---|---|
| `ρ` | плотность груза | кг/м³ |
| `dx = dy = 0.04` | размер ячейки | м |
| `H_ij` | высота груза в колонке | м |
| `m_ij` | масса колонки | кг |
| `M_гр`, `M_пуст`, `M_полн` | масса груза / порожнего / полная | кг |
| `a` | задний мост от заднего борта (`rear_axle_from_rear_m`) | м |
| `L` | база (`wheelbase_m`) | м |
| `x_c`, `y_c`, `z_c` | ЦМ груза в ТЗ | м |
| `x_t`, `y_t`, `z_t` | ЦМ полной массы | м |
| `i` | уклон, `i = tg α = slope_pct/100` | — |

### 4.1 Масса и объём

```
m_ij = ρ · dx · dy · H_ij
M_гр = Σ m_ij
V    = Σ H_ij · dx · dy
```

Колонки без днища и с `z_top < z_floor` отбрасываются (счётчики попадают в
`quality`).

### 4.2 Центр масс груза

Вес колонки — её высота: `H_ij` пропорциональна массе при постоянной `ρ`.

```
x_c = Σ(H_ij · x_ij) / ΣH_ij
y_c = Σ(H_ij · y_ij) / ΣH_ij
z_c = Σ(H_ij · (z_floor + H_ij/2)) / ΣH_ij
```

### 4.3 Центр масс полной массы

```
M_полн = M_пуст + M_гр
x_empty = a + p_пуст · L          # p_пуст = empty_front_pct = 0.465
x_t = (M_пуст · x_empty + M_гр · x_c) / M_полн
y_t = (M_пуст · 0 + M_гр · y_c) / M_полн
z_t = (M_пуст · z_empty + M_гр · z_c) / M_полн
```

### 4.4 Нагрузка на оси (только груз)

Рычаг от заднего моста: `d_c = x_c − a − z_c · i`.

```
N_перед = M_гр · d_c / L
N_зад   = M_гр − N_перед
pct     = 100 · N / M_гр
```

Этот блок (`report.json → axle_load`) показывает, как распределился **сам
груз**, без веса самосвала.

### 4.5 Баланс полной массы и зоны

```
d_t = x_t − a − z_t · i
balance_front_pct = 100 · d_t / L
balance_rear_pct  = 100 − balance_front_pct
```

Зоны по `balance_front_pct` (пороги из конфига):

| Условие | Уровень | Сообщение |
|---|---|---|
| `< 28` | `red` | «Груз сильно смещён назад» |
| `> 38` | `red` | «Груз сильно смещён вперёд» |
| `30…36` | `green` | — |
| остальное | `yellow` | «Отклонение от нормы» |

Отклонение от идеала `ideal_front_pct = 32.25`:

```
deviation_pp  = balance_front_pct − 32.25
deviation_pct = 100 · deviation_pp / 32.25
```

### 4.6 Колёса и борта

Доля правой стороны оси — по поперечному рычагу ЦМ груза:

```
share_right = clamp(0.5 + y_c / track, 0, 1)
```

`track` — колея моста (`track_front_m = 4.197`, `track_rear_m = 3.682`).
Доля борта одинакова для обеих осей и берётся один раз из ЦМ груза.

Нагрузка осей полной массы и проценты колёс для отчёта:

```
front_full = M_полн · balance_front_pct / 100
rear_full  = M_полн − front_full
W1 = front_full · (1 − share_front)   # переднее левое
W2 = front_full · share_front         # переднее правое
W3 = rear_full  · share_rear          # заднее правое (сдвоенное)
W4 = rear_full  · (1 − share_rear)    # заднее левое (сдвоенное)
pct_i = 100 · W_i / M_полн
```

Заднее сдвоенное колесо — **половина задней оси**: делить на 2 повторно не
нужно. Сумма `pct_1…pct_4 ≈ 100`.

В `AnalysisResult` поля `front_left_kg`, `front_right_kg`, `rear_left_kg`,
`rear_right_kg` — это нагрузки **только от груза** (как и `axle_load`), а не
`W1…W4` из полной массы.

### 4.7 Перегруз

`W_ном_перед = (M_полн_ном · 32.25/100 − M_пуст · 0.465) / 2`,
`W_ном_зад = (M_полн_ном · 67.75/100 − M_пуст · 0.535) / 2` — номинал колеса
по грузу (`M_полн_ном = 164 176 кг`, `M_пуст = 72 921 кг`).

```
overload_% = 100 · (W_груз / W_ном − 1)
```

`W_груз` — нагрузка колеса только от груза (`front_left_kg` и т.п.).

### 4.8 Уклон дороги

`slope_pct = i · 100`, где `i = tg α`. Положительный уклон — **подъём к
кабине** (перед выше), `0` — ровная площадка (по умолчанию).

Моменты относительно заднего моста: на уклоне плечо ЦМ уменьшается на `h·i`:

```
pct_перед = 100 · (d − h · i) / L
```

где `d` — расстояние ЦМ от заднего моста, `h` — высота ЦМ.
Для блока «только груз» берутся `d_c`, `z_c`; для баланса полной массы —
`d_t`, `z_t`. Масса, объём и координаты ЦМ от уклона не зависят.

Пример на реальном кейсе:

| Уклон | Оси, % | Колёса 1/2/3/4, % |
|---|---|---|
| `0 %` | 41.5 / 58.5 | 23.5 / 18.0 / 24.8 / 33.7 |
| `+10 %` (подъём к кабине) | 35.2 / 64.8 | 19.9 / 15.3 / 27.5 / 37.3 |

Ограничения: `|slope_pct| ≤ 100`, иначе `ValueError`.

### 4.9 Статус и предупреждения

| Условие | `status` |
|---|---|
| масса ≤ `min_load_kg` | `empty` |
| красная зона или `> 120 %` номинала | `critical` |
| `> 100 %` номинала | `overload` |
| жёлтая зона | `warning` |
| иначе | `ok` |

Предупреждения: смещение вперёд/назад, боковое смещение больше
`lateral_limit_m = 0.30` м, ЦМ груза вне кузова, перегруз.

## 5. Конфиг

**Путь:** `prod_version/axle_load/config.py`, словарь `AVERAGE_CONFIG`.

Проценты там записаны **долями** (`0.3225`), кроме `empty_front_pct`, которая
тоже доля. Нормализация в `TruckConfig` (проценты `0…100`) выполняется один раз
в `average_truck_config()`, конфиг проверяется по инвариантам.

| Ключ | Значение | Единица |
|---|---|---|
| `model` | `AVERAGE_90T_CLASS` | — |
| `wheelbase_m` | 4.598 | м |
| `rear_axle_from_rear_m` | 2.996 | м |
| `front_axle_from_rear_m` | 7.594 | м |
| `track_front_m` / `track_rear_m` | 4.197 / 3.682 | м |
| `empty_weight_kg` | 72 921 | кг |
| `payload_kg` | 91 255 | кг |
| `gross_weight_kg` | 164 176 | кг |
| `empty_front_pct` / `empty_rear_pct` | 0.465 / 0.535 | доля |
| `loaded_front_target_pct` / `loaded_rear_target_pct` | 0.3225 / 0.6775 | доля |
| `green_min_pct` / `green_max_pct` | 0.30 / 0.36 | доля |
| `front_min_pct` / `front_max_pct` | 0.28 / 0.38 | доля |
| `payload_max_pct` | 1.20 | доля |
| `min_load_kg` | 1000 | кг |
| `wheel_warn_pct` | 0.10 | доля |
| `lateral_limit_m` | 0.30 | м |
| `empty_com_z_m` | 2.40 | м |
| `x_limit_m` | 9.629 | м |

Справочные `loaded_com_x_m = 6.111` и `payload_com_target_x_m = 6.886` в
расчёте не используются — они противоречат целевым процентам.

Любое значение можно переопределить на вызов, не меняя файл:

```python
from dataclasses import replace
from axle_load import average_truck_config

truck = replace(average_truck_config(), wheelbase_m=4.70, min_load_kg=500.0)
```

## 6. Выходные файлы

```text
<out>/<кейс>/
├── axle_load_report.json   # уклон, оси, колёса
├── axle_load_1.jpg         # продольный разрез
├── axle_load_2.jpg         # поперечный разрез
├── axle_load_3.jpg         # схема колёс
└── report.json             # только с флагом --report
```

`axle_load_report.json`:

```json
{
  "axles": {
    "front": {"pct": 41.5},
    "rear": {"pct": 58.5}
  },
  "wheels": {
    "1": ["front_left", 23.5],
    "2": ["front_right", 18.0],
    "3": ["rear_right", 24.8],
    "4": ["rear_left", 33.7]
  }
}
```

- порядок колёс фиксирован: 1 — переднее левое, 2 — переднее правое,
  3 — заднее правое, 4 — заднее левое;
- проценты осей и колёс — от **полной** массы, сумма ≈ 100;
- округление — 0,1 процентного пункта; при неизвестной массе — `0.0`, а не
  `NaN`;
- уклон дороги в отчёт не входит: он влияет на проценты, но не является
  результатом расчёта. Заданное значение печатается в сводке CLI и попадает
  в `report.json` (`slope_pct` в `AnalysisResult.to_dict()`).

`report.json` (флаг `--report`) — урезанный `AnalysisResult.to_dict()` плюс
`axles` и `wheels`: масса, объём, ЦМ, `axle_load` (только груз), `balance`
(полная масса), предупреждения, `quality`.

## 7. API для встраивания в работающую систему

### 7.1 Что импортировать

```python
from axle_load import (
    compute,            # только числа, без фигур
    process,            # три фигуры + отчёт
    report_payload,     # отчёт из AnalysisResult
    save_jpeg,          # сохранить три JPEG
    save_report_json,   # сохранить axle_load_report.json
    REPORT_NAME,        # "axle_load_report.json"
    AxleLoadError,      # базовое исключение пакета
)
```

### 7.2 Вариант «нужны картинки и JSON»

```python
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # обязательно для серверов без дисплея

from axle_load import process, save_jpeg, save_report_json

CASE = Path("/data/cases/31-10-2026_06_15_35")

fig1, fig2, fig3, report = process(
    CASE,
    density_kg_m3=2600.0,  # плотность груза
    slope_pct=0.0,         # уклон дороги, % (0 — не влияет)
    y_sign=1.0,            # знак Y в системе ТЗ
)

out = Path("/data/out/31-10-2026_06_15_35")
paths = save_jpeg((fig1, fig2, fig3), out)      # axle_load_1..3.jpg
save_report_json(report, out / "axle_load_report.json")

for figure in (fig1, fig2, fig3):
    plt.close(figure)                             # снять фигуру с учёта pyplot
```

`process` не сохраняет и не закрывает фигуры — это ответственность вызывающей
стороны.

### 7.3 Вариант «нужны только числа» (без matplotlib)

```python
from axle_load import compute

comp = compute(
    "/data/cases/31-10-2026_06_15_35",
    density_kg_m3=2600.0,
    slope_pct=4.0,
)

r = comp.result
payload = {
    "cargo_mass_kg": round(r.cargo_mass_kg, 1),
    "cargo_volume_m3": round(r.cargo_volume_m3, 3),
    "com": [round(r.cargo_com_x_m, 3), round(r.cargo_com_y_m, 3)],
    "front_pct": round(r.balance_front_pct, 1),
    "rear_pct": round(r.balance_rear_pct, 1),
    "level": r.balance_level,
    "warnings": r.warnings,
}
```

`compute` дешевле `process`: нет построения фигур и контура для отрисовки.

### 7.4 Обёртка для сервиса

```python
from __future__ import annotations

import logging
from pathlib import Path

from axle_load import (
    AxleLoadError,
    REPORT_NAME,
    process,
    save_jpeg,
    save_report_json,
)

log = logging.getLogger(__name__)


def handle_case(case_dir: str | Path, out_root: str | Path, *, slope_pct: float = 0.0) -> dict:
    """Обрабатывает один кейс и возвращает отчёт; исключения не глотает."""
    case_dir = Path(case_dir)
    out_dir = Path(out_root) / case_dir.name
    try:
        *figures, report = process(case_dir, slope_pct=slope_pct)
    except AxleLoadError as exc:          # нет файлов, пустой кейс, битые PLY
        log.warning("кейс %s пропущен: %s", case_dir.name, exc)
        raise
    try:
        save_jpeg(tuple(figures), out_dir)
        save_report_json(report, out_dir / REPORT_NAME)
    finally:
        for figure in figures:
            plt.close(figure)
    return report
```

Рекомендации для рабочей системы:

1. **Backend matplotlib.** На сервере без дисплея вызывайте
   `matplotlib.use("Agg")` до импорта `axle_load`. Пакет строит фигуры через
   `Figure` + `FigureCanvasAgg`, без глобального состояния `pyplot`, поэтому
   вызовы можно делать из рабочих потоков.
2. **Один кейс — один вызов.** `process` читает два PLY и держит облака в
   памяти; не кэшируйте фигуры между запросами.
3. **Закрывайте фигуры.** Всегда `plt.close(figure)`: `figure.clear()` оставляет
   фигуру в реестре pyplot, и память растёт.
4. **Ошибки.** `MissingInputError` / `InputDataError` / `ConfigError` — все
   наследники `AxleLoadError`; неизвестный тип модели даёт `ConfigError`,
   отсутствие файлов — `MissingInputError`.
5. **Уклон.** Передавайте `slope_pct` из телеметрии (знак: `> 0` — подъём к
   кабине). При `0` результат совпадает с расчётом на ровной площадке.
6. **Плотность.** `density_kg_m3` — свойство материала; при неизвестной
   плотности используйте `2600` (по умолчанию) и фиксируйте это в отчёте.
7. **Файлы не обязательны.** Если нужен только JSON — используйте `compute` +
   `report_payload`, без записи JPEG.
8. **Кодировка.** JSON пишется в UTF-8; читайте с `encoding="utf-8"`.

### 7.5 CLI как интеграция «по расписанию»

```bash
python -m axle_load /data/cases --out /data/out --slope-pct 0
# опционально: --report  (полный report.json), --no-plot, --json <путь>
```

Коды возврата: `0` — обработан хотя бы один кейс, `2` — кейсы не найдены,
`1` — все кейсы упали.

## 8. Дерево проекта

```text
prod_version/
├── ALGORITHM.md              # этот документ: формулы, конфиг, API
├── INSTALL.md                # установка, CLI, контракты, troubleshooting
├── README.md                 # краткое описание и быстрый старт
├── pytest.ini                # pythonpath = ., testpaths = tests
├── requirements.txt          # numpy, matplotlib, Pillow
├── .gitignore                # __pycache__, .pytest_cache, .ruff_cache
├── axle_load/
│   ├── __init__.py           # публичный API и __all__
│   ├── api.py                # process / compute / report_payload / save_report_json
│   ├── config.py             # AVERAGE_CONFIG, average_truck_config, инварианты
│   ├── case.py               # чтение кейса, BodyFrame(origin=−1), проверка bbox
│   ├── clouds.py             # колонки -> HeightMap, контур кузова
│   ├── calc.py               # масса, ЦМ, оси, колёса, уклон, зоны, статус
│   ├── jsonio.py             # чтение/запись PLY (ASCII+binary), типы
│   ├── schemas.py            # dataclass-типы: TruckConfig, BodyFrame, HeightMap…
│   ├── render.py             # build_dashboard_figures, save_jpeg
│   ├── render_impl.py        # внутренняя реализация трёх схем
│   ├── errors.py             # AxleLoadError / ConfigError / InputDataError
│   └── __main__.py           # CLI: обход кейсов, файлы, сводка
├── examples/
│   └── run_process.py        # пример встраивания: кейс -> JPEG + JSON
└── tests/
    ├── helpers.py            # синтетический кейс (ASCII PLY)
    ├── test_average_config.py# единицы конфига и инварианты
    ├── test_ply_ascii.py     # PLY ASCII/binary
    ├── test_case_reader.py   # колонки, bbox, объём
    ├── test_report_json.py   # контракт axle_load_report.json
    ├── test_slope.py         # формулы уклона и нулевой уклон
    ├── test_render_changes.py# нет баннера предупреждений, нет заголовка
    ├── test_process_smoke.py # process -> 3 фигуры + отчёт
    └── test_cli_defaults.py  # дефолты CLI, --report, --slope-pct
```

## 9. Проверка

```bash
cd prod_version
python -m pytest -q        # 52 теста
```

Реальный кейс `31-10-2026_06_15_35.863935+0900-output`:

| Величина | Значение |
|---|---|
| колонок | 6998 |
| объём | 14.4233 м³ |
| масса при 2600 кг/м³ | 37 500.57 кг |
| ЦМ груза | (4.455, −0.277, 3.885) |
| полная масса | 110 421.57 кг |
| баланс | 41.48 / 58.52 % |
| колёса | 23.5 / 18.0 / 24.8 / 33.7 % |

## 10. Ограничения

- Один тип самосвала (`AVERAGE_90T_CLASS`); BELAZ/CAT-модели не используются.
- Груз считается сплошным по колонкам: пустоты внутри не моделируются.
- Уклон — только продольный; поперечный крен не учитывается.
- Плотность постоянна по всему грузу.
- `loaded_com_x_m` / `payload_com_target_x_m` из конфига — справочные, в
  расчёте не участвуют.

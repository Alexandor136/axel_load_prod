# Инструкция по эксплуатации `axle_load` (prod_version)

## 1. Назначение

`prod_version` — набор для развёртывания и встраивания расчёта массы груза,
центра масс и распределения нагрузки на оси самосвала БелАЗ-7558.

Вход — **каталог кейса** с двумя облаками точек (раздел 4).
Выход — три схемы (JPEG) и JSON с нагрузкой по осям и колёсам (раздел 7).

Тип самосвала не выбирается: всегда используется встроенный
`AVERAGE_90T_CLASS` (`axle_load/config.py`). Внешние модели, `models_root`
и `model_types.json` не нужны.

Формулы и встраивание в сервис: [ALGORITHM.md](ALGORITHM.md).

## 2. Требования

- Python 3.10+;
- numpy, matplotlib, Pillow (`requirements.txt`);
- для тестов — pytest;
- никаких внешних каталогов моделей.

## 3. Установка

Из каталога `prod_version`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

На Windows — `.venv\Scripts\pip.exe` и `.venv\Scripts\python.exe`.
Пакет `pyproject.toml` не содержит: запуск идёт из корня `prod_version`
без установки, либо через `PYTHONPATH`.

## 4. Входные данные

### 4.1. Обязательные файлы кейса

Оба файла обязательны. Имена и вложенность жёстко заданы в
`axle_load/case.py` (`ENTIRE_MASS_REL`, `BODY_MODEL_REL`).

```text
<кейс>/
├── 5_LoadEstimation/
│   └── 0_entire_mass.ply     # объём груза
└── 4_B2M/
    └── result_b2m.ply        # модель кузова (красные точки) + скан (зелёные)
```

| Файл | Формат | Единицы | Обязательные свойства | Что используется |
|---|---|---|---|---|
| `5_LoadEstimation/0_entire_mass.ply` | PLY, ASCII или binary | **индексы вокселей** 0,04 м по X/Y/Z | `x`, `y`, `z` | колонки `(ix, iy)`: `min z` — днище, `max z` — верх груза; цвет игнорируется |
| `4_B2M/result_b2m.ply` | PLY, ASCII или binary | метры модели | `x`, `y`, `z`, `red`, `green`, `blue` | только точки `(255, 0, 0)` — модель кузова: bbox и контур для схем |

### 4.2. Как читаются облака

- `0_entire_mass.ply`: если координаты не являются целыми индексами —
  `InputDataError` («координаты X/Y должны быть индексами вокселей»).
  Колонки вне bbox кузова тоже отбрасываются с ошибкой.
- Перевод индексов в метры: `метры = −1 + (индекс + 0,5) · 0,04` по всем осям.
  Начало сетки этого пайплайна — `(−1, −1, −1)`, **не** `bbox_min − 1`
  (проверено по скану: при `origin_z = −1` верх колонок совпадает с зелёными
  точками у 99,8 % колонок).
- Объём груза: `Σ(zmax − zmin) · 0,04³` по всем колонкам.
- `result_b2m.ply`: RGB обязателен; рамка кузова — bbox красных точек,
  `width_m = max X`, `rear_y_m = max Y`. Зелёные точки на расчёт не влияют.
- Если красных точек нет — `InputDataError` («нет красных точек модели кузова»).

### 4.3. Чего на входе быть НЕ должно

| Не нужен | Почему |
|---|---|
| `Postprocessing/log.json`, `DataProcessing/**` | старый формат, не поддерживается |
| `models_root`, `model_types.json` | тип самосвала встроен (`AVERAGE_90T_CLASS`) |
| файлы `body.ply`, `cargo.ply`, `floor.ply` | старый API работы с отдельными облаками |

## 5. Входные параметры

Все параметры, влияющие на расчёт, задаются либо флагами CLI (таблица 5.1),
либо аргументами API (таблица 5.2). Дефолты берутся из `AVERAGE_CONFIG`
(раздел 9), а не дублируются в коде.

### 5.1. Параметры CLI

```bash
python -m axle_load <путь> [флаги]
```

| Флаг | По умолчанию | Единица | Назначение |
|---|---|---|---|
| `<путь>` (позиционный) | `.` | — | каталог кейса либо каталог с кейсами (поиск рекурсивный) |
| `--out` | `./new_result` | каталог | корневой каталог результатов |
| `--json` | — | путь | явный путь к `axle_load_report.json`; рассчитан на один кейс |
| `--density` | `2600` | кг/м³ | плотность груза |
| `--slope-pct` | `0` | % | продольный уклон: `0` — ровно, `> 0` — подъём к кабине, `|значение| ≤ 100` |
| `--y-sign` | `1` | — | `+1` — Y > 0 справа по ходу, `-1` — зеркально |
| `--wheelbase` | `4.598` | м | база (между мостами) |
| `--rear-axle-x` | `2.996` | м | задний мост от заднего борта |
| `--ideal-front` | `32.25` | % | идеальная доля передней оси (задаёт `ideal_front_pct` и зоны) |
| `--green-min` | `30` | % | нижняя граница зелёной зоны |
| `--green-max` | `36` | % | верхняя граница зелёной зоны |
| `--front-min` | `28` | % | нижняя граница красной зоны |
| `--front-max` | `38` | % | верхняя граница красной зоны |
| `--payload-max-pct` | `120` | % | максимум от номинальной грузоподъёмности |
| `--lateral-limit` | `0.30` | м | допустимое смещение ЦМ по Y |
| `--min-load-kg` | `1000` | кг | ниже этой массы груза — «Недостаточно данных» |
| `--empty-com-z` | `2.40` | м | высота ЦМ порожнего самосвала (для разреза) |
| `--no-plot` | выкл. | — | не строить JPEG |
| `--report` | выкл. | — | дополнительно писать полный `report.json` |
| `--save-inputs` | выкл. | — | сохранить копии облаков в `<out>/<кейс>/inputs/` |

Флаги `--wheelbase … --empty-com-z` переопределяют соответствующие поля
`AVERAGE_CONFIG` только для текущего запуска; `--ideal-front` меняет
`ideal_front_pct`, целевая доля груза `loaded_front_target_pct` остаётся
из конфига.

### 5.2. Параметры API

`compute(case, ...)` и `process(case, ...)` принимают одинаковый набор:

| Параметр | По умолчанию | Единица | Назначение |
|---|---|---|---|
| `case` | — | путь или `CaseData` | каталог кейса |
| `truck` | `None` | `TruckConfig` | готовая конфигурация; `None` → `AVERAGE_CONFIG` |
| `density_kg_m3` | `2600` | кг/м³ | плотность груза |
| `cell_size_m` | `0.04` | м | размер вокселя входных облаков |
| `y_sign` | `1.0` | — | `+1` — Y > 0 справа, `-1` — зеркально |
| `validate` | `True` | — | проверки входных данных |
| `slope_pct` | `0.0` | % | уклон дороги (см. 5.1) |
| `title` | `""` | — | заголовок схем; пустая строка — без заголовка |

## 6. Запуск CLI

```bash
.venv/bin/python -m axle_load /data/trips --out /data/new_result
```

- `<путь>` может быть самим кейсом или каталогом с кейсами: CLI рекурсивно
  ищет `result_b2m.ply` и проверяет соседний `5_LoadEstimation/0_entire_mass.ply`.
- Без аргументов обходит текущий каталог, `<out>` по умолчанию `./new_result`.
- При успехе печатается путь каждого файла и строка сводки:
  `масса … т | объём … м3 | оси …/… % | колёса … %` (+ `уклон …`, если задан).

Коды возврата:

| Код | Значение |
|---|---|
| `0` | обработан хотя бы один кейс |
| `2` | кейсы не найдены |
| `1` | все найденные кейсы упали |

## 7. Выходные данные

### 7.1. Файлы результата

Раскладка: `<out>/<имя_кейса>/…` (имя кейса — имя его каталога).

| Файл | Когда создаётся | Содержимое |
|---|---|---|
| `axle_load_report.json` | всегда (или по пути `--json`) | оси и колёса, проценты от полной массы — 7.3 |
| `axle_load_1.jpg` | если не `--no-plot` | продольный разрез: кузов, груз, ЦМ, шкала баланса |
| `axle_load_2.jpg` | если не `--no-plot` | поперечный разрез: кузов, груз, ЦМ, боковое смещение |
| `axle_load_3.jpg` | если не `--no-plot` | схема колёс сверху: проценты, перегруз, мини-шкалы мостов |
| `report.json` | только с `--report` | полный отчёт: массы, объём, ЦМ, оси, колёса, предупреждения — 7.4 |
| `inputs/cargo_top.ply` | только с `--save-inputs` | верх груза (`x`, `y`, `z_floor + h`), binary PLY, метры ТЗ |
| `inputs/body_model.ply` | только с `--save-inputs` | красные точки кузова в метрах ТЗ, binary PLY |

### 7.2. Схемы

| Файл | Что изображено |
|---|---|
| `axle_load_1.jpg` | вид сбоку: контур кузова и дна, груз, идеальный и расчётный ЦМ, шкала баланса передней оси |
| `axle_load_2.jpg` | вид сзади: контур кузова, груз, боковое смещение ЦМ (`ΔY`), полоса допуска |
| `axle_load_3.jpg` | вид сверху: оси и колёса с процентами, цвет по перегрузу, мини-шкалы баланса мостов |

Контур кузова на всех схемах строится по красным точкам `result_b2m.ply`
(бины 0,10 м, сглаживание ~1 м), поэтому зависит от входного облака.

### 7.3. Контракт `axle_load_report.json`

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

- `axles.*.pct` — доля оси от **полной** массы (порожний + груз), %;
- `wheels` — фиксированный порядок: `1` переднее левое, `2` переднее правое,
  `3` заднее правое, `4` заднее левое; значение — % от **полной** массы;
- заднее сдвоенное колесо — половина задней оси (без повторного `/2`);
- уклон в отчёт не входит: он влияет на проценты, но результатом не является;
- при нулевой массе — `0.0`, а не `NaN`;
- проценты округлены до одного знака, сумма ≈ 100.

### 7.4. Контракт `report.json` (только `--report`)

Урезанный `AnalysisResult.to_dict()` плюс `axles` и `wheels`.

| Поле | Единица | Смысл |
|---|---|---|
| `model` | — | всегда `AVERAGE_90T_CLASS` |
| `slope_pct` | % | заданный уклон |
| `cargo_mass_kg` | кг | масса груза |
| `cargo_volume_m3` | м³ | объём груза |
| `cargo_com.x_m/y_m/z_m` | м | ЦМ груза в ТЗ |
| `total_mass_kg` | кг | порожний + груз |
| `total_com.x_m/y_m/z_m` | м | итоговый ЦМ |
| `com_deviation.ideal_x_m/ideal_y_m` | м | идеальный ЦМ |
| `com_deviation.delta_x_m/delta_y_m` | м | отклонение итогового ЦМ |
| `axle_load.front_kg/rear_kg` | кг | нагрузка **только груза** |
| `axle_load.front_pct/rear_pct` | % | доля **только груза** |
| `balance.level` | — | `green` / `yellow` / `red` / `unknown` |
| `balance.message` | — | текст зоны |
| `balance.ideal_front_pct` | % | `32.25` |
| `balance.front_pct/rear_pct` | % | доля **полной** массы |
| `balance.front_deviation_pp` | п.п. | отклонение от идеала |
| `balance.front_deviation_pct` | % | относительное отклонение |
| `wheels` | % | то же, что в `axle_load_report.json` |
| `warnings` | — | список предупреждений |
| `is_within_norm` | — | `true`, если зона зелёная и предупреждений нет |
| `quality.status` | — | `ok` / `warning` / `critical` / `overload` / `empty` |
| `axles` | % | дубль осей из `axle_load_report.json` |

`axle_load.front_pct` (только груз) и `balance.front_pct` (полная масса) —
разные величины, не путать.

### 7.5. Что возвращает API

| Вызов | Результат |
|---|---|
| `process(case, …)` | `(fig1, fig2, fig3, report)` — три `matplotlib.figure.Figure` (продольный, поперечный, колёса) и словарь контракта 7.3 |
| `compute(case, …)` | `Computation`: `result`, `height_map`, `outline`, `frame`, `truck`, `params` — без отрисовки |
| `save_jpeg(figures, dir)` | пути `axle_load_1.jpg … axle_load_3.jpg` |
| `save_report_json(payload, path)` | путь к записанному JSON (UTF-8) |

Фигуры API не сохраняет и не закрывает — это делает вызывающая сторона.

## 8. Встраивание в другой сервис

```python
from axle_load import process, save_jpeg, save_report_json

fig1, fig2, fig3, report = process(
    "/data/trips/кейс",
    density_kg_m3=2600.0,  # плотность груза
    slope_pct=0.0,         # уклон дороги, % (0 — не влияет)
    y_sign=1.0,            # знак Y в системе ТЗ
)

save_jpeg((fig1, fig2, fig3), "/data/out")
save_report_json(report, "/data/out/axle_load_report.json")
```

API не сохраняет и не закрывает фигуры. Это делает вызывающая сторона через
`matplotlib.pyplot.close(figure)`. `figure.clear()` не подходит: фигура
остаётся в реестре pyplot и накапливается при повторных вызовах.

Готовый скрипт-пример: `python examples/run_process.py <кейс> [<out>]` —
пишет три JPEG и `axle_load_report.json`; уклон берётся из `AXLE_LOAD_SLOPE_PCT`.

Развёрнутые примеры (включая обёртку для сервиса и работу без matplotlib) —
в [ALGORITHM.md, раздел 7](ALGORITHM.md#7-api-для-встраивания-в-работающую-систему).

## 9. Встроенный конфиг `AVERAGE_CONFIG`

Проценты в `AVERAGE_CONFIG` записаны **долями** (`0.3225`), а в `TruckConfig`
— процентами (`32.25`). Нормализация выполняется один раз в
`average_truck_config()`; конфиг проверяется по инвариантам.

Путь: `prod_version/axle_load/config.py` → `AVERAGE_CONFIG`.

| Ключ `AVERAGE_CONFIG` | Значение | В `TruckConfig` | Единица |
|---|---|---|---|
| `model` | `AVERAGE_90T_CLASS` | `model` | str |
| `wheelbase_m` | 4.598 | `wheelbase_m` | м |
| `rear_axle_from_rear_m` | 2.996 | `rear_axle_from_rear_m` | м |
| `track_front_m` | 4.197 | `track_front_m` | м |
| `track_rear_m` | 3.682 | `track_rear_m` | м |
| `empty_weight_kg` | 72 921 | `empty_weight_kg` | кг |
| `payload_kg` | 91 255 | `payload_kg` | кг |
| `gross_weight_kg` | 164 176 | — (проверка) | кг |
| `empty_front_pct` | 0.465 | `empty_front_pct` | доля 0..1 |
| `loaded_front_target_pct` | 0.3225 | `loaded_front_target_pct`, `ideal_front_pct` | % |
| `loaded_rear_target_pct` | 0.6775 | — (проверка) | доля |
| `green_min_pct` | 0.30 | `green_min_pct` | % |
| `green_max_pct` | 0.36 | `green_max_pct` | % |
| `front_min_pct` | 0.28 | `front_min_pct` | % |
| `front_max_pct` | 0.38 | `front_max_pct` | % |
| `payload_max_pct` | 1.20 | `payload_max_pct` | % |
| `min_load_kg` | 1000 | `min_load_kg` | кг |
| `wheel_warn_pct` | 0.10 | `wheel_warn_pct` | % |
| `lateral_limit_m` | 0.30 | `lateral_limit_m` | м |
| `empty_com_z_m` | 2.40 | `empty_com_z_m` | м |
| `x_limit_m` | 9.629 | `x_limit_m` | м |

Идеальная загрузка — `32.25 / 67.75` % по осям. Справочные
`loaded_com_x_m = 6.111` и `payload_com_target_x_m = 6.886` в расчёте
**не используются**: они противоречат процентным целям.

Уклон в конфиге не хранится: это условие рейса, передаётся параметром
`slope_pct` / `--slope-pct` (по умолчанию `0`).

## 10. Дерево файлов

```text
prod_version/
├── ALGORITHM.md               # формулы, конфиг, встраивание API
├── INSTALL.md                 # эта инструкция
├── README.md                  # краткое описание и быстрый старт
├── pytest.ini                 # pythonpath = ., testpaths = tests
├── requirements.txt           # numpy, matplotlib, Pillow
├── .gitignore                 # __pycache__, .pytest_cache, .ruff_cache
├── axle_load/
│   ├── __init__.py            # публичный API
│   ├── api.py                 # process / compute / report_payload
│   ├── config.py              # AVERAGE_CONFIG, average_truck_config
│   ├── case.py                # чтение кейса: 0_entire_mass + result_b2m
│   ├── schemas.py             # dataclass-типы, TruckConfig, BodyFrame
│   ├── jsonio.py              # PLY: чтение/запись (ASCII и binary)
│   ├── clouds.py              # колонки -> HeightMap, контур кузова
│   ├── calc.py                # масса, ЦМ, оси, колёса, уклон, зоны
│   ├── render.py              # публичный рендеринг: build_figures/save_jpeg
│   ├── render_impl.py         # реализация отрисовки
│   ├── errors.py              # ConfigError / InputDataError
│   └── __main__.py            # CLI
├── examples/
│   └── run_process.py         # пример встраивания
├── result/                    # пример результата на реальном кейсе
└── tests/
    ├── helpers.py             # синтетический кейс
    └── test_*.py              # 52 теста
```

## 11. Ошибки

- `MissingInputError` — нет одного из двух файлов кейса;
- `InputDataError` — нет красных точек кузова, координаты X/Y в
  `0_entire_mass.ply` не являются индексами, колонки выходят за bbox кузова,
  нулевой объём;
- `ConfigError` — рассогласованный `AVERAGE_CONFIG`;
- `ValueError` — уклон вне диапазона `−100…100 %` или не конечное число.

## 12. Тесты

Из каталога `prod_version`:

```bash
python -m pytest -q
```

52 теста. Тест на реальном кейсе (`test_real_case_volume`) пропускается,
если в репозитории нет `data_new/` с кейсом.

## 13. Troubleshooting

| Симптом | Причина | Решение |
|---|---|---|
| `кейсы не найдены` (код 2) | нет `5_LoadEstimation/0_entire_mass.ply` или `4_B2M/result_b2m.ply` | проверить структуру кейса |
| `координаты X/Y должны быть индексами вокселей` | подан старый формат или метры | использовать `0_entire_mass.ply` из нового пайплайна |
| `колонки груза выходят за bbox кузова` | неверное начало воксельной сетки | сетка начинается в `(−1, −1, −1)` |
| `нет красных точек модели кузова` | в `result_b2m.ply` нет RGB или цвет другой | проверить `property uchar red/green/blue` |
| нет JPEG | `--no-plot` или ошибка кейса | смотреть stderr |
| нет `report.json` | он пишется только с `--report` | добавить флаг |
| `slope_pct должен быть в диапазоне` | уклон больше 100 % | проверить телеметрию уклона |

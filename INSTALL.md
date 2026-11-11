# Инструкция по эксплуатации `axle_load` (prod_version)

## 1. Назначение

`prod_version` — набор для развёртывания и встраивания расчёта массы груза,
центра масс и распределения нагрузки на оси самосвала БелАЗ-7558.

Вход — **каталог кейса** с двумя облаками точек:

- `5_LoadEstimation/0_entire_mass.ply` — сплошной объём груза;
- `4_B2M/result_b2m.ply` — выровненная сцена: красные точки `(255, 0, 0)` —
  модель кузова, зелёные `(0, 255, 0)` — скан.

Тип самосвала не выбирается: всегда используется встроенный
`AVERAGE_90T_CLASS` (`axle_load/config.py`). Внешние модели, `models_root`
и `model_types.json` не нужны.

Выход:

- три объекта `matplotlib.figure.Figure`:
  1. продольный разрез;
  2. поперечный разрез;
  3. схема колёс;
- словарь/файл `axle_load_report.json` с уклоном, процентами по осям и колёсам;
- опционально `report.json` (флаг `--report`).

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

## 4. Структура кейса

```text
<кейс>/
├── 5_LoadEstimation/
│   └── 0_entire_mass.ply
└── 4_B2M/
    └── result_b2m.ply
```

`0_entire_mass.ply` — ASCII PLY, координаты X/Y — **индексы вокселей**
(0,04 м), Z — тоже индекс. В каждой колонке `(ix, iy)` несколько вокселей:
минимум по Z — днище, максимум — верх груза. Объём считается как
`Σ(zmax − zmin) · 0,04³`.

Перевод индексов в метры: `метры = −1 + (индекс + 0,5) · 0,04` по всем осям.
Начало сетки в этом пайплайне — `(−1, −1, −1)`, **не** `bbox_min − 1`
(проверено по скану: при `origin_z = −1` верх колонок совпадает с зелёными
точками у 99,8 % колонок).

`result_b2m.ply` — метры модели, RGB обязателен. Рамка кузова берётся по bbox
красных точек: `width_m = max X`, `rear_y_m = max Y`.

## 5. Запуск CLI

```bash
.venv/bin/python -m axle_load <путь> [--out <каталог>]
```

`<путь>` — каталог кейса либо каталог с кейсами (поиск рекурсивный).
По умолчанию `<out>` = `./new_result`.

Результат:

```text
<out>/<кейс>/axle_load_report.json
<out>/<кейс>/axle_load_1.jpg
<out>/<кейс>/axle_load_2.jpg
<out>/<кейс>/axle_load_3.jpg
<out>/<кейс>/report.json          # только с --report
```

Полезные флаги:

| Флаг | По умолчанию | Назначение |
|---|---|---|
| `--out` | `./new_result` | корневой каталог результатов |
| `--json` | — | явный путь к `axle_load_report.json` (один кейс) |
| `--density` | `2600` | плотность груза, кг/м³ |
| `--slope-pct` | `0` | продольный уклон дороги, %: `0` — ровно, `> 0` — подъём к кабине |
| `--y-sign` | `1` | `+1` — Y > 0 справа, `-1` — зеркально |
| `--ideal-front` | `32.25` | идеальная доля передней оси, % |
| `--green-min`, `--green-max` | `30`, `36` | границы зелёной зоны, % |
| `--front-min`, `--front-max` | `28`, `38` | границы красной зоны, % |
| `--report` | выкл. | дополнительно писать полный `report.json` |
| `--no-plot` | — | не строить JPEG |
| `--save-inputs` | — | сохранить `inputs/cargo_top.ply`, `inputs/body_model.ply` |

Коды возврата: `0` — обработан хотя бы один кейс, `2` — кейсы не найдены,
`1` — все кейсы упали.

## 6. Встраивание в другой сервис

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

## 7. Встроенный конфиг `AVERAGE_CONFIG`

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

## 8. Формат `axle_load_report.json`

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

- порядок: 1 — переднее левое, 2 — переднее правое, 3 — заднее правое,
  4 — заднее левое;
- проценты осей и колёс — от **полной** массы (порожний + груз), сумма ≈ 100;
- заднее сдвоенное колесо — половина задней оси (без повторного `/2`);
- уклон дороги в отчёт не входит — он влияет на сами проценты, но не является
  результатом; заданное значение видно в сводке CLI и в `report.json`;
- при нулевой массе — `0.0`, а не `NaN`.

## 9. `report.json` (только с `--report`)

Урезанный `AnalysisResult.to_dict()` плюс `axles` и `wheels`: масса, объём,
ЦМ, `axle_load` (только груз), `balance` (полная масса), предупреждения.

- `axle_load.front_pct` — доля **только груза** на переднюю ось;
- `balance.front_pct` — доля **полной массы** (порожний + груз), по ней
  считаются зоны и отклонение от идеала `32.25 %`.

Не путать эти два поля.

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
│   ├── jsonio.py              # JSON, ASCII/binary PLY
│   ├── clouds.py              # колонки -> HeightMap, контур кузова
│   ├── calc.py                # масса, ЦМ, оси, колёса, уклон, зоны
│   ├── render.py              # публичный рендеринг: build_figures/save_jpeg
│   ├── render_impl.py         # реализация отрисовки
│   ├── errors.py              # ConfigError / InputDataError
│   └── __main__.py            # CLI
├── examples/
│   └── run_process.py         # пример встраивания
└── tests/
    ├── helpers.py             # синтетический кейс
    └── test_*.py              # 52 теста
```

## 11. Ошибки

- `MissingInputError` — нет одного из двух файлов кейса;
- `InputDataError` — нет красных точек кузова, координаты X/Y в
  `0_entire_mass.ply` не являются индексами, колонки выходят за bbox кузова,
  нулевой объём;
- `ConfigError` — рассогласованный `AVERAGE_CONFIG`, неизвестный тип модели;
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

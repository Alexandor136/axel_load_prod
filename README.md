# axle_load — prod_version

Расчёт массы груза, центра масс и распределения нагрузки на оси самосвала
**БелАЗ-7558** по облакам точек нового пайплайна. Тип самосвала фиксирован:
встроенный `AVERAGE_90T_CLASS` (`AVERAGE_CONFIG`), внешние модели и
`model_types.json` не нужны.

Подробно: формулы, конфиг и встраивание — [ALGORITHM.md](ALGORITHM.md).

## Вход

Один каталог кейса с двумя файлами:

```text
<кейс>/
├── 5_LoadEstimation/0_entire_mass.ply   # сплошной объём груза (индексы вокселей)
└── 4_B2M/result_b2m.ply                 # кузов (красные) + скан (зелёные), метры
```

Координаты в `0_entire_mass.ply` — **индексы вокселей** 0,04 м с началом
в `(−1, −1, −1)`. Файл `result_b2m.ply` — в метрах; рамка кузова берётся по
красным точкам `(255, 0, 0)`.

Старый формат (`DataProcessing/` + `Postprocessing/log.json`) не поддерживается.

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m axle_load /data/trips --out /data/new_result
```

На Windows — `.venv\Scripts\python.exe`. Без аргументов CLI рекурсивно ищет
кейсы в текущем каталоге.

Результат по кейсу:

```text
/data/new_result/<кейс>/axle_load_report.json  # уклон, оси, колёса
/data/new_result/<кейс>/axle_load_1.jpg        # продольный разрез
/data/new_result/<кейс>/axle_load_2.jpg        # поперечный разрез
/data/new_result/<кейс>/axle_load_3.jpg        # схема колёс
```

`report.json` (массы, ЦМ, предупреждения) создаётся только с флагом `--report`.
Заголовок «Средний самосвал 90 т» на схемах не рисуется.

Уклон дороги задаётся флагом `--slope-pct` (в процентах, `> 0` — подъём к
кабине). По умолчанию `0` — на расчёт не влияет.

## Встраивание

```python
from axle_load import process, save_jpeg, save_report_json

fig1, fig2, fig3, report = process("/data/trips/мои_кейс", slope_pct=0.0)
save_jpeg((fig1, fig2, fig3), "/data/out")
save_report_json(report, "/data/out/axle_load_report.json")
```

`process` возвращает три `matplotlib.figure.Figure` (продольный разрез,
поперечный разрез, схема колёс) и словарь с нагрузкой по осям и колёсам.
Фигуры не сохраняются и не закрываются — это делает вызывающая сторона.

Формат `axle_load_report.json`:

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

Порядок фиксирован: 1 — переднее левое, 2 — переднее правое,
3 — заднее правое, 4 — заднее левое. Проценты — от **полной** массы
(порожний + груз). Заднее сдвоенное колесо — половина задней оси,
без повторного деления.

## Тесты

```bash
cd prod_version
python -m pytest -q
```

Полная инструкция: [INSTALL.md](INSTALL.md).

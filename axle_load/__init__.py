"""Пакет расчёта распределения нагрузки на оси по облакам нового формата."""

# Публичный API: расчёт (calc), конфиг (config), чтение кейса (case),
# типы (schemas), PLY IO (jsonio), облака (clouds), рендеринг (render), API.
from .api import (
    REPORT_NAME,
    WHEEL_ORDER,
    compute,
    process,
    report_payload,
    save_report_json,
)
from .calc import AnalysisResult, analyze
from .case import CaseData, case_files, is_case_dir, read_case
from .clouds import body_outline_from_cloud, build_height_map_from_columns
from .config import (
    AVERAGE_CONFIG,
    AVERAGE_MODEL_TYPE,
    average_truck_config,
)
from .errors import AxleLoadError, ConfigError, InputDataError, MissingInputError
from .jsonio import (
    PlyCloud,
    read_ply,
    write_ply,
)
from .render import build_dashboard_figures, save_jpeg
from .schemas import (
    BodyFrame,
    BodyOutline,
    Columns,
    Computation,
    HeightMap,
    ProcessParams,
    TruckConfig,
)

# Явный список экспортируемых имён (для from axle_load import * и линтеров).
__all__ = [
    "AVERAGE_CONFIG",
    "AVERAGE_MODEL_TYPE",
    "AnalysisResult",
    "AxleLoadError",
    "BodyFrame",
    "BodyOutline",
    "CaseData",
    "Columns",
    "Computation",
    "ConfigError",
    "HeightMap",
    "InputDataError",
    "MissingInputError",
    "PlyCloud",
    "ProcessParams",
    "REPORT_NAME",
    "TruckConfig",
    "WHEEL_ORDER",
    "analyze",
    "average_truck_config",
    "body_outline_from_cloud",
    "build_dashboard_figures",
    "build_height_map_from_columns",
    "case_files",
    "compute",
    "is_case_dir",
    "process",
    "read_case",
    "read_ply",
    "report_payload",
    "save_jpeg",
    "save_report_json",
    "write_ply",
]

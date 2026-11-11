"""Исключения публичного API."""

from __future__ import annotations


class AxleLoadError(Exception):
    """Базовое исключение пакета."""


class ConfigError(AxleLoadError):
    """Ошибка параметров, JSON или выбора модели."""


class InputDataError(AxleLoadError):
    """Ошибка входных облаков."""


class MissingInputError(InputDataError):
    """Не найден обязательный входной файл рейса."""

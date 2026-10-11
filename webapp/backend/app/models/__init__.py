"""Anomaly model registry. Any AnomalyModel subclass defined in a module in
this package is registered under its `name` automatically."""

import importlib
import pkgutil

from .base import AnomalyModel

_SKIP = {"base", "evaluate"}


def get_registry() -> dict[str, type[AnomalyModel]]:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name not in _SKIP:
            importlib.import_module(f"{__name__}.{mod.name}")
    return {cls.name: cls for cls in AnomalyModel.__subclasses__() if cls.name}

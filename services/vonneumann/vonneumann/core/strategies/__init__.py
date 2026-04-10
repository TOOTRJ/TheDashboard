"""Auto-discovery registry for evolution strategies."""

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from .base import EvolutionResult, EvolutionStrategy

__all__ = ["EvolutionStrategy", "EvolutionResult", "get_strategy", "list_strategies"]

_registry: dict[str, type[EvolutionStrategy]] = {}
_metadata_cache: dict[str, dict] = {}
_discovered = False
_logger = logging.getLogger(__name__)


def _discover() -> None:
    """Scan this package for EvolutionStrategy subclasses. Called once on first access."""
    global _discovered
    if _discovered:
        return
    _discovered = True

    package_dir = Path(__file__).parent
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name == "base":
            continue
        try:
            module = importlib.import_module(f".{module_info.name}", __package__)
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, EvolutionStrategy)
                    and obj is not EvolutionStrategy
                    and not inspect.isabstract(obj)
                ):
                    instance = obj()
                    _registry[instance.name] = obj
                    _metadata_cache[instance.name] = instance.to_dict()
        except Exception:
            _logger.exception("Failed to load strategy module: %s", module_info.name)


def get_strategy(name: str) -> EvolutionStrategy:
    """Instantiate a strategy by name. Raises KeyError if not found."""
    _discover()
    if name not in _registry:
        raise KeyError(
            f"Unknown strategy '{name}'. Available: {list(_registry.keys())}"
        )
    return _registry[name]()


def list_strategies() -> list[dict]:
    """Return metadata for all discovered strategies (cached)."""
    _discover()
    return list(_metadata_cache.values())

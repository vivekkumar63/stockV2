import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from .base import SpecialBaseStrategy

logger = logging.getLogger(__name__)


def _discover() -> list[SpecialBaseStrategy]:
    found: dict[str, SpecialBaseStrategy] = {}
    pkg_dir = Path(__file__).parent / "strategies"
    for mi in pkgutil.iter_modules([str(pkg_dir)]):
        if mi.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"domains.special_strategies.strategies.{mi.name}")
        except Exception as e:
            logger.warning("[special_discover] import failed — %s: %s", mi.name, e)
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, SpecialBaseStrategy)
                and cls is not SpecialBaseStrategy
                and getattr(cls, "name", "")
                and cls.name not in found
            ):
                try:
                    found[cls.name] = cls()
                except Exception as e:
                    logger.warning("[special_discover] instantiation failed — %s: %s", cls.__name__, e)
    strategies = sorted(found.values(), key=lambda s: s.name)
    logger.info("[special_discover] %d special strategies loaded: %s", len(strategies), [s.name for s in strategies])
    return strategies


ALL_SPECIAL_STRATEGIES: list[SpecialBaseStrategy] = _discover()

"""Top-level policy package with automatic discovery of researcher policy files."""

import importlib
import inspect
from pathlib import Path
import pkgutil
from typing import Any

from .fifo import FIFOPolicy
from .sjf import SJFPolicy


def discover_policies() -> dict[str, type[Any]]:
    """Scans policies/ for all classes that implement select_next_job."""
    registry: dict[str, type[Any]] = {}
    package_dir = Path(__file__).parent

    for _, module_name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if is_pkg or module_name.startswith("_"):
            continue

        module = importlib.import_module(f".{module_name}", package=__name__)
        for attr_name, attr_val in inspect.getmembers(module, inspect.isclass):
            if (
                getattr(attr_val, "__module__", None) == module.__name__
                and hasattr(attr_val, "select_next_job")
            ):
                registry[module_name.lower()] = attr_val
                registry[attr_name.lower()] = attr_val

    return registry


def get_policy(name: str, **kwargs: Any) -> Any:
    """Instantiates a policy by its file name or class name."""
    registry = discover_policies()
    key = name.lower().replace("-", "_")

    if key not in registry:
        available = sorted({k for k in registry if not k.endswith("policy")})
        raise ValueError(f"Unknown policy '{name}'. Available policies: {available}")

    policy_cls = registry[key]
    return policy_cls(**kwargs)


__all__ = ["FIFOPolicy", "SJFPolicy", "discover_policies", "get_policy"]

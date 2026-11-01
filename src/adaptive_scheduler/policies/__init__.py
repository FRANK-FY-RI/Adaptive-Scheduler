"""Top-level policy package with automatic discovery and explicit registration (UC-S04)."""

import importlib
import inspect
from pathlib import Path
import pkgutil
from typing import Any

from .adaptive import AdaptivePolicy
from .easy_backfill import EASYBackfillPolicy
from .fifo import FIFOPolicy
from .sjf import SJFPolicy

_CUSTOM_REGISTRY: dict[str, type[Any]] = {}


def discover_policies() -> dict[str, type[Any]]:
    """Scans policies/ for all classes that implement select_next_job and merges registered policies."""
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

    registry.update(_CUSTOM_REGISTRY)
    return registry


def register_policy(name: str, policy_cls: type[Any]) -> None:
    """Explicitly registers a custom policy class under a unique identifier (UC-S04, Section 9)."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Policy name must be a non-empty string.")
    if not inspect.isclass(policy_cls) or not hasattr(policy_cls, "select_next_job"):
        raise ValueError("Registered policy must be a class implementing select_next_job.")

    key = name.strip().lower().replace("-", "_")
    existing = discover_policies()
    if key in existing:
        raise ValueError(f"Duplicate policy registration for identifier '{name}'.")

    _CUSTOM_REGISTRY[key] = policy_cls


def get_policy(name: str, **kwargs: Any) -> Any:
    """Instantiates a policy by its file name, class name, or registered identifier."""
    registry = discover_policies()
    key = name.strip().lower().replace("-", "_")

    # Support convenient non-blocking baseline aliases out of the box
    if key == "fifo_nonblocking" and "strict_head_of_line" not in kwargs:
        return FIFOPolicy(strict_head_of_line=False, **kwargs)
    if key == "sjf_nonblocking" and "strict_head_of_line" not in kwargs:
        return SJFPolicy(strict_head_of_line=False, **kwargs)

    if key not in registry:
        available = sorted({k for k in registry if not k.endswith("policy")})
        raise ValueError(f"Unknown policy '{name}'. Available policies: {available}")

    policy_cls = registry[key]
    return policy_cls(**kwargs)


__all__ = [
    "AdaptivePolicy",
    "EASYBackfillPolicy",
    "FIFOPolicy",
    "SJFPolicy",
    "discover_policies",
    "get_policy",
    "register_policy",
]

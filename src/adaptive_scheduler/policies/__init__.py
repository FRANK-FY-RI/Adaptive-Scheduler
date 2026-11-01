"""Built-in and researcher-defined scheduling policies."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
import pkgutil
from typing import Any

from .adaptive import AdaptivePolicy
from .easy_backfill import EASYBackfillPolicy
from .fifo import FIFOPolicy
from .registry import _CUSTOM_REGISTRY, register_policy
from .sjf import SJFPolicy

# Preserve compatibility with the preemption extension when srtf.py is present.
try:
    from .srtf import SRTFPolicy
except ImportError:  # The non-preemption policy package can be used independently.
    SRTFPolicy = None  # type: ignore[assignment,misc]


def discover_policies() -> dict[str, type[Any]]:
    """Return built-in and explicitly registered policy classes by normalized name."""
    registry: dict[str, type[Any]] = {}
    package_dir = Path(__file__).parent

    for _, module_name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if is_pkg or module_name.startswith("_") or module_name == "registry":
            continue
        module = importlib.import_module(f".{module_name}", package=__name__)
        for class_name, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                candidate.__module__ == module.__name__
                and callable(getattr(candidate, "select_next_job", None))
            ):
                registry[module_name.lower().replace("-", "_")] = candidate
                registry[class_name.lower().replace("-", "_")] = candidate
                policy_name = getattr(candidate, "name", None)
                if isinstance(policy_name, str) and policy_name.strip():
                    registry[policy_name.lower().replace("-", "_").replace(" ", "_")] = candidate

    # Explicit registrations should be discoverable and take precedence only
    # for their own custom keys (built-in collisions are rejected below).
    registry.update(_CUSTOM_REGISTRY)
    return registry


def get_policy(name: str, **kwargs: Any) -> Any:
    """Instantiate a built-in or registered policy by name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Unknown policy: policy name must be a non-empty string.")
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    policies = discover_policies()
    policy_cls = policies.get(key)
    if policy_cls is None:
        raise ValueError(f"Unknown policy '{name}'. Available policies: {sorted(policies)}")
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

if SRTFPolicy is not None:
    __all__.append("SRTFPolicy")

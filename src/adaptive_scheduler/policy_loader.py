"""Load researcher-defined scheduling policies from standalone Python files."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.interfaces import SchedulingPolicy


def _import_policy_module(path: Path) -> ModuleType:
    """Import ``path`` under a private module name without changing sys.path."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise ConfigurationError(f"Cannot access policy file '{path}': {exc}") from exc

    identity = f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8")
    module_suffix = hashlib.sha256(identity).hexdigest()[:16]
    module_name = f"_adaptive_scheduler_user_policy_{module_suffix}"

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"Could not create an import loader for policy file '{path}'.")

    module = importlib.util.module_from_spec(spec)
    # Register before execution. This is required by features such as dataclasses
    # and postponed annotations that look the module up in sys.modules.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ConfigurationError(
            f"Could not import policy file '{path}': {type(exc).__name__}: {exc}"
        ) from exc

    return module


def _is_policy_class(candidate: object, module: ModuleType) -> bool:
    """Return whether candidate is a policy class defined in the loaded file."""
    return (
        inspect.isclass(candidate)
        and getattr(candidate, "__module__", None) == module.__name__
        and callable(getattr(candidate, "select_next_job", None))
    )


def load_policy_from_file(
    file_path: str | Path,
    class_name: str | None = None,
) -> SchedulingPolicy:
    """Load and instantiate a researcher policy from a standalone ``.py`` file.

    The selected class must be defined in the supplied file, implement the
    ``SchedulingPolicy`` protocol, and have a zero-argument constructor. If
    ``class_name`` is omitted, the file must define exactly one policy class.

    Note:
        Policy files are executable Python code. Only load files you trust.
    """
    path = Path(file_path).expanduser()
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise ConfigurationError(f"Policy file does not exist or cannot be accessed: '{path}'.") from exc

    if not path.is_file():
        raise ConfigurationError(f"Policy path is not a file: '{path}'.")
    if path.suffix.lower() != ".py":
        raise ConfigurationError(f"Policy file must be a Python .py file: '{path}'.")

    module = _import_policy_module(path)

    if class_name is not None:
        policy_class = getattr(module, class_name, None)
        if not inspect.isclass(policy_class):
            raise ConfigurationError(
                f"Class '{class_name}' was not found in policy file '{path}'."
            )
        if getattr(policy_class, "__module__", None) != module.__name__:
            raise ConfigurationError(
                f"Class '{class_name}' must be defined in '{path}', not imported from another module."
            )
        if not callable(getattr(policy_class, "select_next_job", None)):
            raise ConfigurationError(
                f"Class '{class_name}' does not implement select_next_job(context)."
            )
    else:
        candidates = [
            value
            for _, value in inspect.getmembers(module, inspect.isclass)
            if _is_policy_class(value, module)
        ]
        if not candidates:
            raise ConfigurationError(
                f"No scheduling policy class found in '{path}'. Define a class with "
                "a select_next_job(context) method."
            )
        if len(candidates) > 1:
            names = ", ".join(sorted(candidate.__name__ for candidate in candidates))
            raise ConfigurationError(
                f"Multiple scheduling policy classes found in '{path}': {names}. "
                "Specify one with --policy-class."
            )
        policy_class = candidates[0]

    try:
        policy = policy_class()
    except Exception as exc:
        raise ConfigurationError(
            f"Could not instantiate policy class '{policy_class.__name__}' from '{path}'. "
            "Custom policy classes must currently have a zero-argument constructor. "
            f"Cause: {type(exc).__name__}: {exc}"
        ) from exc

    if not isinstance(policy, SchedulingPolicy):
        raise ConfigurationError(
            f"Instance of '{policy_class.__name__}' does not satisfy SchedulingPolicy "
            "(it must provide a callable select_next_job(context) method)."
        )

    return policy


__all__ = ["load_policy_from_file"]

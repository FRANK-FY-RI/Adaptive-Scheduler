"""Explicit custom scheduling-policy registration."""

from __future__ import annotations

from typing import Any, TypeVar, overload

PolicyClass = TypeVar("PolicyClass", bound=type[Any])
_CUSTOM_REGISTRY: dict[str, type[Any]] = {}


def _normalize_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Policy name must be a non-empty string.")
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def register_policy(name: str | type[Any], policy_cls: type[Any] | None = None):
    """Register a custom policy by name, or use as a class decorator.

    Supported forms::

        register_policy("my-policy", MyPolicy)

        @register_policy("my-policy")
        class MyPolicy: ...

        @register_policy
        class MyPolicy: ...
    """
    if isinstance(name, type) and policy_cls is None:
        cls = name
        key = _normalize_name(cls.__name__)
        return _register(key, cls)

    key = _normalize_name(name) if isinstance(name, str) else None
    if key is None:
        raise TypeError("register_policy expects a policy name and class.")

    if policy_cls is None:
        return lambda cls: _register(key, cls)

    return _register(key, policy_cls)


def _register(key: str, policy_cls: type[Any]) -> type[Any]:
    if not isinstance(policy_cls, type):
        raise TypeError("policy_cls must be a class.")
    if not callable(getattr(policy_cls, "select_next_job", None)):
        raise TypeError("A registered policy must implement select_next_job(context).")
    if key in _CUSTOM_REGISTRY:
        raise ValueError(f"Duplicate policy registration: '{key}'.")
    _CUSTOM_REGISTRY[key] = policy_cls
    return policy_cls

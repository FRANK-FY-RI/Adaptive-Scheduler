"""Public API for the AdaptiveSched simulation engine package (ENG-NFR-07)."""

from .engine import SimulationEngine
from .exceptions import (
    ConfigurationError,
    InvalidSchedulingDecisionError,
    InvariantViolationError,
    SimulationError,
    SimulationStalledError,
)
from .interfaces import SchedulingPolicy
from .models import (
    ClusterConfig,
    EventType,
    ExecutionRecord,
    JobId,
    JobLifecycleState,
    JobSpec,
    ReservationInfo,
    RunningJobView,
    SchedulerContext,
    SimulationEvent,
    SimulationProfile,
    SimulationResult,
    SimulationSettings,
    validate_cluster_config,
    validate_workload,
)

__all__ = [
    "ClusterConfig",
    "ConfigurationError",
    "EventType",
    "ExecutionRecord",
    "InvalidSchedulingDecisionError",
    "InvariantViolationError",
    "JobId",
    "JobLifecycleState",
    "JobSpec",
    "ReservationInfo",
    "RunningJobView",
    "SchedulerContext",
    "SchedulingPolicy",
    "SimulationEngine",
    "SimulationError",
    "SimulationEvent",
    "SimulationProfile",
    "SimulationResult",
    "SimulationSettings",
    "SimulationStalledError",
    "validate_cluster_config",
    "validate_workload",
]

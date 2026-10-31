"""Domain exceptions for the AdaptiveSched simulation engine (AS-REQ-ENG-001)."""


class SimulationError(Exception):
    """Base exception for all simulation engine errors."""


class ConfigurationError(SimulationError):
    """Raised when cluster configuration or workload specifications are invalid."""


class InvalidSchedulingDecisionError(SimulationError):
    """Raised when a scheduling policy proposes an invalid or infeasible job start."""


class SimulationStalledError(SimulationError):
    """Raised when the simulation cannot make progress or encounters a stalled state."""


class InvariantViolationError(SimulationError):
    """Raised when an internal engine state or resource invariant is violated."""
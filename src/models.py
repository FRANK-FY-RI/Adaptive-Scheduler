"""Data models, input/output contracts, and internal event structures (AS-REQ-ENG-001)."""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Iterable, Union

from .exceptions import ConfigurationError

JobId = Union[str, int]


class JobLifecycleState(Enum):
    """Mutually exclusive lifecycle states for a job (ENG-FR-05, Invariant 9)."""
    PENDING_ARRIVAL = "PENDING_ARRIVAL"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"


class EventType(IntEnum):
    """Internal discrete event types ordered by same-timestamp priority (Section 8).

    COMPLETION (0) is processed before ARRIVAL (1) at identical timestamps so
    that freed cores are available before new arrivals and policy dispatch.
    """
    COMPLETION = 0
    ARRIVAL = 1


@dataclass(frozen=True)
class ClusterConfig:
    """Validated cluster resource configuration (UC-E01, Section 3, Section 10)."""
    total_cores: int

    def __post_init__(self) -> None:
        validate_cluster_config(self.total_cores)


@dataclass(frozen=True)
class SimulationSettings:
    """Optional simulation engine settings (Section 10, ENG-FR-19).

    Attributes:
        enable_profiling: Collect wall-clock and event/dispatch counters (ENG-FR-19).
        check_invariants: Verify all 10 Section 7 invariants after each event batch and dispatch.
        max_consecutive_idle_skips: Maximum number of timestamps a policy may leave runnable
            waiting jobs unscheduled while the cluster is completely idle before raising
            SimulationStalledError (ENG-FR-15, Section 11).
    """
    enable_profiling: bool = False
    check_invariants: bool = True
    max_consecutive_idle_skips: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.enable_profiling, bool):
            raise ConfigurationError("enable_profiling must be a boolean.")
        if not isinstance(self.check_invariants, bool):
            raise ConfigurationError("check_invariants must be a boolean.")
        if (
            not isinstance(self.max_consecutive_idle_skips, int)
            or isinstance(self.max_consecutive_idle_skips, bool)
            or self.max_consecutive_idle_skips < 0
        ):
            raise ConfigurationError("max_consecutive_idle_skips must be a non-negative integer.")


@dataclass(frozen=True)
class JobSpec:
    """Validated input specification for a single job (Section 3, Section 10)."""
    job_id: JobId
    arrival_time: int
    runtime: int
    required_cores: int


@dataclass(frozen=True)
class RunningJobView:
    """Read-only snapshot of a currently executing job exposed to policies."""
    job: JobSpec
    start_time: int
    expected_finish_time: int


@dataclass(frozen=True)
class ReservationInfo:
    """Read-only reservation record for future backfilling extensions (ENG-FR-18)."""
    job_id: JobId
    reserved_start_time: int
    reserved_finish_time: int
    reserved_cores: int


@dataclass(frozen=True)
class SchedulerContext:
    """Immutable simulation state snapshot passed to scheduling strategies (ENG-FR-12, ENG-FR-16).

    Policies inspect this context to propose decisions without mutating engine state.
    """
    current_time: int
    total_cores: int
    available_cores: int
    allocated_cores: int
    waiting_jobs: tuple[JobSpec, ...]
    running_jobs: tuple[RunningJobView, ...]
    reservations: tuple[ReservationInfo, ...] = ()

    def earliest_available_time(self, required_cores: int) -> int:
        """Calculates the earliest timestamp >= current_time when `required_cores` will be free.

        Assists future backfilling strategies (ENG-FR-18) using only read-only running job views.
        """
        if required_cores <= 0 or required_cores > self.total_cores:
            raise ValueError(
                f"required_cores ({required_cores}) must be in 1..{self.total_cores}."
            )
        if required_cores <= self.available_cores:
            return self.current_time

        freed_by_time: dict[int, int] = {}
        for rjob in self.running_jobs:
            freed_by_time[rjob.expected_finish_time] = (
                freed_by_time.get(rjob.expected_finish_time, 0) + rjob.job.required_cores
            )

        projected_available = self.available_cores
        for finish_time in sorted(freed_by_time):
            projected_available += freed_by_time[finish_time]
            if projected_available >= required_cores:
                return finish_time

        return self.current_time


@dataclass(frozen=True)
class ExecutionRecord:
    """Immutable execution record produced for each completed job (UC-E06, Section 10)."""
    job_id: JobId
    arrival_time: int
    start_time: int
    finish_time: int
    runtime: int
    waiting_time: int
    required_cores: int


@dataclass(frozen=True)
class SimulationProfile:
    """Optional runtime instrumentation statistics (ENG-FR-19)."""
    total_events_processed: int
    arrival_events_processed: int
    completion_events_processed: int
    timestamps_visited: int
    scheduler_invocations: int
    jobs_completed: int
    peak_event_queue_size: int
    peak_waiting_jobs: int
    peak_running_jobs: int
    wall_time_seconds: float
    scheduler_wall_time_seconds: float


@dataclass(frozen=True)
class SimulationResult:
    """Read-only container returned upon simulation completion (UC-E06, Section 10)."""
    total_cores: int
    final_time: int
    execution_records: tuple[ExecutionRecord, ...]
    profile: SimulationProfile | None = None


@dataclass(order=True, frozen=True)
class SimulationEvent:
    """Internal discrete event ordered deterministically for heapq (ENG-FR-11, ENG-FR-17).

    Sorting key hierarchy:
    1. timestamp: earliest simulated time first.
    2. event_type: EventType.COMPLETION (0) before EventType.ARRIVAL (1).
    3. job_sort_key: deterministic type-safe representation of job_id.
    4. sequence_number: monotonic insertion counter as final tie-breaker.
    """
    timestamp: int
    event_type: EventType
    job_sort_key: tuple[int, str]
    sequence_number: int
    job_id: JobId


def make_job_sort_key(job_id: JobId) -> tuple[int, str]:
    """Produces a deterministic, type-safe comparison key for int or str job IDs."""
    if isinstance(job_id, int) and not isinstance(job_id, bool):
        return (0, f"{job_id:+021d}")
    return (1, str(job_id))


def validate_cluster_config(total_cores: int) -> None:
    """Validates cluster CPU capacity (Section 3, Section 11)."""
    if not isinstance(total_cores, int) or isinstance(total_cores, bool) or total_cores <= 0:
        raise ConfigurationError(
            f"Cluster total_cores must be a positive integer; got {total_cores!r}."
        )


def validate_workload(jobs: Iterable[JobSpec], total_cores: int) -> tuple[JobSpec, ...]:
    """Validates a collection of JobSpec records against cluster capacity (UC-E01, Section 11)."""
    validate_cluster_config(total_cores)
    validated: list[JobSpec] = []
    seen_ids: set[JobId] = set()

    for spec in jobs:
        if not isinstance(spec, JobSpec):
            raise ConfigurationError(f"Expected JobSpec instance, got {type(spec).__name__}.")
        if (
            spec.job_id is None
            or isinstance(spec.job_id, bool)
            or not isinstance(spec.job_id, (int, str))
            or (isinstance(spec.job_id, str) and not spec.job_id.strip())
        ):
            raise ConfigurationError(
                f"Job ID must be a non-empty string or integer; got {spec.job_id!r}."
            )
        if spec.job_id in seen_ids:
            raise ConfigurationError(f"Duplicate job_id detected: {spec.job_id!r}.")
        if (
            not isinstance(spec.arrival_time, int)
            or isinstance(spec.arrival_time, bool)
            or spec.arrival_time < 0
        ):
            raise ConfigurationError(
                f"Job {spec.job_id!r} has invalid arrival_time {spec.arrival_time!r}; "
                "must be a non-negative integer."
            )
        if (
            not isinstance(spec.runtime, int)
            or isinstance(spec.runtime, bool)
            or spec.runtime <= 0
        ):
            raise ConfigurationError(
                f"Job {spec.job_id!r} has invalid runtime {spec.runtime!r}; "
                "must be a positive integer."
            )
        if (
            not isinstance(spec.required_cores, int)
            or isinstance(spec.required_cores, bool)
            or spec.required_cores <= 0
        ):
            raise ConfigurationError(
                f"Job {spec.job_id!r} has invalid required_cores {spec.required_cores!r}; "
                "must be a positive integer."
            )
        if spec.required_cores > total_cores:
            raise ConfigurationError(
                f"Job {spec.job_id!r} requests {spec.required_cores} cores, "
                f"exceeding cluster capacity of {total_cores} cores."
            )

        seen_ids.add(spec.job_id)
        validated.append(spec)

    return tuple(validated)

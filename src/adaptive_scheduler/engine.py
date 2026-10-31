"""Authoritative discrete-event simulation engine (AS-REQ-ENG-001)."""

from dataclasses import dataclass
import heapq
import time
from typing import Iterable

from adaptive_scheduler.exceptions import (
    ConfigurationError,
    InvalidSchedulingDecisionError,
    InvariantViolationError,
    SimulationError,
    SimulationStalledError,
)
from adaptive_scheduler.interfaces import SchedulingPolicy
from adaptive_scheduler.models import (
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
    make_job_sort_key,
    validate_cluster_config,
    validate_workload,
)


@dataclass
class _InternalJobState:
    """Mutable job tracking record strictly private to SimulationEngine."""
    spec: JobSpec
    state: JobLifecycleState = JobLifecycleState.PENDING_ARRIVAL
    start_time: int | None = None
    finish_time: int | None = None
    start_count: int = 0
    completion_count: int = 0


class SimulationEngine:
    """Discrete-event cluster scheduling simulation engine (AS-REQ-ENG-001).

    Simulation Assumptions (Section 3):
    1. One cluster with a fixed number of CPU cores.
    2. Jobs with known arrival time, runtime, and core requirement.
    3. Non-preemptive execution.
    4. Deterministic completion at `start_time + runtime`.
    5. No failures, cancellations, or runtime estimation errors.
    6. Nonnegative integer simulation time.
    7. CPU cores as the only resource type.

    Event Ordering & Dispatch Semantics (Section 8):
    1. Advance to the earliest event timestamp.
    2. Process all completion events at that timestamp, releasing resources.
    3. Process all arrival events at that timestamp, adding jobs to the waiting set.
    4. Request scheduling decisions using the resulting state.
    5. Continue processing while policy semantics and available resources permit starts.
    """

    def __init__(
        self,
        total_cores: int | ClusterConfig,
        jobs: Iterable[JobSpec],
        policy: SchedulingPolicy,
        settings: SimulationSettings | None = None,
        *,
        enable_profiling: bool | None = None,
        check_invariants: bool | None = None,
    ) -> None:
        if isinstance(total_cores, ClusterConfig):
            resolved_cores = total_cores.total_cores
        else:
            validate_cluster_config(total_cores)
            resolved_cores = total_cores

        if not isinstance(policy, SchedulingPolicy):
            raise ConfigurationError(
                "Provided policy must implement the SchedulingPolicy interface (select_next_job)."
            )

        base_settings = settings or SimulationSettings()
        self._settings = SimulationSettings(
            enable_profiling=(
                enable_profiling
                if enable_profiling is not None
                else base_settings.enable_profiling
            ),
            check_invariants=(
                check_invariants
                if check_invariants is not None
                else base_settings.check_invariants
            ),
            max_consecutive_idle_skips=base_settings.max_consecutive_idle_skips,
        )

        self._total_cores: int = resolved_cores
        self._available_cores: int = resolved_cores
        self._allocated_cores: int = 0
        self._policy: SchedulingPolicy = policy

        # Simulation clock (ENG-FR-02)
        self._current_time: int = 0

        # Event queue and monotonic sequence counter (ENG-FR-03, ENG-FR-17)
        self._event_queue: list[SimulationEvent] = []
        self._event_seq: int = 0

        # Authoritative lifecycle partitions (ENG-FR-05, Invariant 9)
        self._job_states: dict[JobId, _InternalJobState] = {}
        self._pending_ids: set[JobId] = set()
        self._waiting_ids: set[JobId] = set()
        self._running_ids: set[JobId] = set()
        self._completed_ids: set[JobId] = set()

        # Active completion event tracking per running job (Invariant 3)
        self._active_completion_events: dict[JobId, SimulationEvent] = {}

        # Completed execution records (ENG-FR-09, ENG-FR-16)
        self._execution_records: list[ExecutionRecord] = []

        # Reservation records for future backfilling (ENG-FR-18)
        self._reservations: list[ReservationInfo] = []

        # Stall tracking (ENG-FR-15, Section 11)
        self._consecutive_idle_skips: int = 0

        # Instrumentation counters (ENG-FR-19)
        self._total_events_processed: int = 0
        self._arrival_events_processed: int = 0
        self._completion_events_processed: int = 0
        self._timestamps_visited: int = 0
        self._scheduler_invocations: int = 0
        self._peak_event_queue_size: int = 0
        self._peak_waiting_jobs: int = 0
        self._peak_running_jobs: int = 0
        self._wall_time_seconds: float = 0.0
        self._scheduler_wall_time_seconds: float = 0.0

        self._initialize_workload(jobs)
        if self._settings.check_invariants:
            self._assert_invariants()

    # ------------------------------------------------------------------
    # Read-Only State & Inspection Properties (UC-E06, ENG-FR-16)
    # ------------------------------------------------------------------

    @property
    def current_time(self) -> int:
        return self._current_time

    @property
    def total_cores(self) -> int:
        return self._total_cores

    @property
    def available_cores(self) -> int:
        return self._available_cores

    @property
    def allocated_cores(self) -> int:
        return self._allocated_cores

    @property
    def is_complete(self) -> bool:
        """Returns True when all jobs in the workload have completed (ENG-FR-14)."""
        return len(self._completed_ids) == len(self._job_states)

    @property
    def waiting_jobs(self) -> tuple[JobSpec, ...]:
        """Returns a deterministic, read-only tuple of currently waiting jobs."""
        return tuple(
            self._job_states[jid].spec
            for jid in sorted(
                self._waiting_ids,
                key=lambda jid: (
                    self._job_states[jid].spec.arrival_time,
                    make_job_sort_key(jid),
                ),
            )
        )

    @property
    def running_jobs(self) -> tuple[RunningJobView, ...]:
        """Returns a deterministic, read-only tuple of currently running jobs."""
        return tuple(
            RunningJobView(
                job=self._job_states[jid].spec,
                start_time=self._job_states[jid].start_time,  # type: ignore[arg-type]
                expected_finish_time=(
                    self._job_states[jid].start_time  # type: ignore[operator]
                    + self._job_states[jid].spec.runtime
                ),
            )
            for jid in sorted(self._running_ids, key=make_job_sort_key)
        )

    @property
    def completed_jobs(self) -> tuple[JobSpec, ...]:
        """Returns a deterministic, read-only tuple of completed job specifications."""
        return tuple(
            self._job_states[rec.job_id].spec for rec in self._execution_records
        )

    @property
    def reservations(self) -> tuple[ReservationInfo, ...]:
        """Exposes read-only reservation records for future backfilling (ENG-FR-18)."""
        return tuple(self._reservations)

    @property
    def execution_records(self) -> tuple[ExecutionRecord, ...]:
        """Exposes read-only execution records in deterministic completion order (UC-E06)."""
        return tuple(self._execution_records)

    def get_job_lifecycle_state(self, job_id: JobId) -> JobLifecycleState:
        """Returns the current lifecycle state of a known job ID."""
        if job_id not in self._job_states:
            raise KeyError(f"Unknown job_id: {job_id!r}")
        return self._job_states[job_id].state

    # ------------------------------------------------------------------
    # Reservation Management Hook for Future Backfilling (ENG-FR-18)
    # ------------------------------------------------------------------

    def set_reservations(self, reservations: Iterable[ReservationInfo]) -> None:
        """Validates and updates active reservations exposed in SchedulerContext (ENG-FR-18)."""
        validated: list[ReservationInfo] = []
        for res in reservations:
            if not isinstance(res, ReservationInfo):
                raise InvalidSchedulingDecisionError(
                    f"Expected ReservationInfo, got {type(res).__name__}."
                )
            if res.job_id not in self._job_states:
                raise InvalidSchedulingDecisionError(
                    f"Reservation references unknown job_id {res.job_id!r}."
                )
            if self._job_states[res.job_id].state != JobLifecycleState.WAITING:
                raise InvalidSchedulingDecisionError(
                    f"Reservation job {res.job_id!r} must be in WAITING state."
                )
            if res.reserved_start_time < self._current_time:
                raise InvalidSchedulingDecisionError(
                    f"Reservation for job {res.job_id!r} has reserved_start_time "
                    f"({res.reserved_start_time}) < current_time ({self._current_time})."
                )
            expected_finish = (
                res.reserved_start_time + self._job_states[res.job_id].spec.runtime
            )
            if res.reserved_finish_time != expected_finish:
                raise InvalidSchedulingDecisionError(
                    f"Reservation for job {res.job_id!r} has reserved_finish_time "
                    f"({res.reserved_finish_time}) != reserved_start_time + runtime ({expected_finish})."
                )
            if res.reserved_cores != self._job_states[res.job_id].spec.required_cores:
                raise InvalidSchedulingDecisionError(
                    f"Reservation for job {res.job_id!r} has reserved_cores "
                    f"({res.reserved_cores}) != required_cores "
                    f"({self._job_states[res.job_id].spec.required_cores})."
                )
            validated.append(res)
        self._reservations = validated

    def clear_reservations(self) -> None:
        """Clears all active job reservations."""
        self._reservations.clear()

    # ------------------------------------------------------------------
    # Initialization & Event Scheduling (UC-E01)
    # ------------------------------------------------------------------

    def _initialize_workload(self, jobs: Iterable[JobSpec]) -> None:
        validated_specs = validate_workload(jobs, self._total_cores)
        for spec in validated_specs:
            self._job_states[spec.job_id] = _InternalJobState(spec=spec)
            self._pending_ids.add(spec.job_id)
            self._schedule_event(
                timestamp=spec.arrival_time,
                event_type=EventType.ARRIVAL,
                job_id=spec.job_id,
            )

    def _schedule_event(
        self, timestamp: int, event_type: EventType, job_id: JobId
    ) -> SimulationEvent:
        if timestamp < self._current_time:
            raise InvariantViolationError(
                f"Cannot schedule event at timestamp {timestamp} earlier than "
                f"current_time {self._current_time}."
            )
        self._event_seq += 1
        event = SimulationEvent(
            timestamp=timestamp,
            event_type=event_type,
            job_sort_key=make_job_sort_key(job_id),
            sequence_number=self._event_seq,
            job_id=job_id,
        )
        heapq.heappush(self._event_queue, event)
        if len(self._event_queue) > self._peak_event_queue_size:
            self._peak_event_queue_size = len(self._event_queue)
        return event

    # ------------------------------------------------------------------
    # Event Processing Loop (UC-E02, Section 8)
    # ------------------------------------------------------------------

    def step(self) -> bool:
        """Processes the next earliest event timestamp batch and invokes dispatch (UC-E02).

        Returns:
            True if an event timestamp batch was processed, or False if the simulation
            is already complete.
        """
        if self.is_complete:
            return False

        step_start = time.perf_counter()

        if not self._event_queue:
            unfinished = len(self._job_states) - len(self._completed_ids)
            raise SimulationStalledError(
                f"Event queue is empty while {unfinished} job(s) remain unfinished "
                f"(waiting={len(self._waiting_ids)}, running={len(self._running_ids)}, "
                f"pending={len(self._pending_ids)})."
            )

        # Verify every running job still has its completion event scheduled (Section 11)
        if len(self._active_completion_events) != len(self._running_ids):
            raise InvariantViolationError(
                "Missing or inconsistent completion events for running jobs."
            )

        # Step 1: Advance simulated time directly to the earliest event timestamp (ENG-FR-04)
        next_timestamp = self._event_queue[0].timestamp
        if next_timestamp < self._current_time:
            raise InvariantViolationError(
                f"Simulated clock regression detected: {next_timestamp} < {self._current_time}."
            )
        self._current_time = next_timestamp
        self._timestamps_visited += 1

        # Step 2 & 3: Process all events at `self._current_time` in documented order:
        # EventType.COMPLETION (0) before EventType.ARRIVAL (1), tie-broken deterministically.
        while self._event_queue and self._event_queue[0].timestamp == self._current_time:
            event = heapq.heappop(self._event_queue)
            self._total_events_processed += 1
            if event.event_type == EventType.COMPLETION:
                self._process_completion(event)
                self._completion_events_processed += 1
            elif event.event_type == EventType.ARRIVAL:
                self._process_arrival(event)
                self._arrival_events_processed += 1
            else:
                raise SimulationError(f"Unsupported event type: {event.event_type!r}")

        if len(self._waiting_ids) > self._peak_waiting_jobs:
            self._peak_waiting_jobs = len(self._waiting_ids)

        if self._settings.check_invariants:
            self._assert_invariants()

        # Step 4 & 5: Request scheduling decisions using the resulting state
        self._dispatch_jobs()

        if len(self._running_ids) > self._peak_running_jobs:
            self._peak_running_jobs = len(self._running_ids)

        if self._settings.check_invariants:
            self._assert_invariants()

        self._wall_time_seconds += time.perf_counter() - step_start
        return True

    def run(self) -> SimulationResult:
        """Executes the simulation until all jobs complete and returns read-only results."""
        while not self.is_complete:
            self.step()

        profile = (
            SimulationProfile(
                total_events_processed=self._total_events_processed,
                arrival_events_processed=self._arrival_events_processed,
                completion_events_processed=self._completion_events_processed,
                timestamps_visited=self._timestamps_visited,
                scheduler_invocations=self._scheduler_invocations,
                jobs_completed=len(self._completed_ids),
                peak_event_queue_size=self._peak_event_queue_size,
                peak_waiting_jobs=self._peak_waiting_jobs,
                peak_running_jobs=self._peak_running_jobs,
                wall_time_seconds=self._wall_time_seconds,
                scheduler_wall_time_seconds=self._scheduler_wall_time_seconds,
            )
            if self._settings.enable_profiling
            else None
        )

        return SimulationResult(
            total_cores=self._total_cores,
            final_time=self._current_time,
            execution_records=tuple(self._execution_records),
            profile=profile,
        )

    # ------------------------------------------------------------------
    # Event Handlers & Job Lifecycle Transitions (UC-E03, UC-E04, UC-E05)
    # ------------------------------------------------------------------

    def _process_arrival(self, event: SimulationEvent) -> None:
        job_state = self._job_states.get(event.job_id)
        if job_state is None:
            raise InvariantViolationError(f"Arrival event for unknown job {event.job_id!r}.")
        if job_state.state != JobLifecycleState.PENDING_ARRIVAL:
            raise InvariantViolationError(
                f"Job {event.job_id!r} arrived in invalid state {job_state.state}."
            )
        if event.timestamp != job_state.spec.arrival_time:
            raise InvariantViolationError(
                f"Job {event.job_id!r} arrival timestamp {event.timestamp} != "
                f"spec.arrival_time {job_state.spec.arrival_time}."
            )

        self._pending_ids.remove(event.job_id)
        job_state.state = JobLifecycleState.WAITING
        self._waiting_ids.add(event.job_id)

    def _process_completion(self, event: SimulationEvent) -> None:
        """Completes a running job and releases its resources (UC-E04, ENG-FR-08)."""
        job_id = event.job_id
        job_state = self._job_states.get(job_id)
        if job_state is None:
            raise InvariantViolationError(f"Completion event for unknown job {job_id!r}.")
        if job_state.state != JobLifecycleState.RUNNING or job_id not in self._running_ids:
            raise InvariantViolationError(
                f"Completion event for job {job_id!r} which is not RUNNING "
                f"(current state: {job_state.state})."
            )

        active_event = self._active_completion_events.get(job_id)
        if active_event != event:
            raise InvariantViolationError(
                f"Missing or inconsistent completion event for job {job_id!r}."
            )

        if job_state.start_time is None:
            raise InvariantViolationError(f"Running job {job_id!r} is missing start_time.")

        expected_finish = job_state.start_time + job_state.spec.runtime
        if self._current_time != expected_finish:
            raise InvariantViolationError(
                f"Job {job_id!r} completed at {self._current_time}, "
                f"expected {expected_finish}."
            )

        # Update lifecycle state
        del self._active_completion_events[job_id]
        self._running_ids.remove(job_id)
        job_state.state = JobLifecycleState.COMPLETED
        job_state.finish_time = self._current_time
        job_state.completion_count += 1
        self._completed_ids.add(job_id)

        # Release cores exactly once (ENG-FR-08)
        cores = job_state.spec.required_cores
        self._allocated_cores -= cores
        self._available_cores += cores

        # Finalize immutable execution record (ENG-FR-09)
        waiting_time = job_state.start_time - job_state.spec.arrival_time
        self._execution_records.append(
            ExecutionRecord(
                job_id=job_id,
                arrival_time=job_state.spec.arrival_time,
                start_time=job_state.start_time,
                finish_time=job_state.finish_time,
                runtime=job_state.spec.runtime,
                waiting_time=waiting_time,
                required_cores=cores,
            )
        )

    def _dispatch_jobs(self) -> None:
        """Invokes the scheduling policy while policy semantics and resources permit starts."""
        started_in_batch = 0
        max_possible_starts = len(self._waiting_ids) + 1

        while self._waiting_ids:
            if started_in_batch > max_possible_starts:
                raise SimulationStalledError(
                    f"Dispatch loop exceeded maximum possible starts ({max_possible_starts}) "
                    f"at time {self._current_time}."
                )

            context = self._build_scheduler_context()
            self._scheduler_invocations += 1

            sched_start = time.perf_counter()
            proposed_job_id = self._policy.select_next_job(context)
            self._scheduler_wall_time_seconds += time.perf_counter() - sched_start

            if proposed_job_id is None:
                break

            self._validate_and_start_job(proposed_job_id)
            started_in_batch += 1

            # Once cluster cores are exhausted, no further jobs can start in this batch
            if self._available_cores == 0:
                break

        # Stall and non-progress detection (ENG-FR-15, Section 11):
        if self._waiting_ids and not self._running_ids:
            runnable_jobs = [
                jid
                for jid in sorted(self._waiting_ids, key=make_job_sort_key)
                if self._job_states[jid].spec.required_cores <= self._available_cores
            ]
            if runnable_jobs:
                self._consecutive_idle_skips += 1
                if (
                    not self._event_queue
                    or self._consecutive_idle_skips > self._settings.max_consecutive_idle_skips
                ):
                    raise SimulationStalledError(
                        f"Policy failed to make progress when runnable work exists: "
                        f"waiting job(s) {runnable_jobs!r} fit within idle cluster "
                        f"({self._available_cores}/{self._total_cores} cores available) "
                        f"at time {self._current_time}, but policy returned None."
                    )
        else:
            self._consecutive_idle_skips = 0 

    def validate_proposal(self, proposed_job_id: JobId) -> JobSpec:
        """Validates a proposed job selection without mutating engine state (UC-E05, ENG-FR-13).

        Returns:
            The validated `JobSpec` if the proposal is legal at `self._current_time`.

        Raises:
            InvalidSchedulingDecisionError: If the job ID is unknown, has not arrived,
                is already running/completed, or requires more cores than available.
        """
        if (
            proposed_job_id is None
            or isinstance(proposed_job_id, bool)
            or proposed_job_id not in self._job_states
        ):
            raise InvalidSchedulingDecisionError(
                f"Policy proposed unknown job_id {proposed_job_id!r}."
            )

        job_state = self._job_states[proposed_job_id]
        spec = job_state.spec

        if (
            job_state.state == JobLifecycleState.PENDING_ARRIVAL
            or spec.arrival_time > self._current_time
        ):
            raise InvalidSchedulingDecisionError(
                f"Policy proposed job {proposed_job_id!r} at time {self._current_time} "
                f"before its arrival_time {spec.arrival_time}."
            )

        if job_state.state == JobLifecycleState.RUNNING:
            raise InvalidSchedulingDecisionError(
                f"Policy proposed job {proposed_job_id!r} which is already RUNNING."
            )

        if job_state.state == JobLifecycleState.COMPLETED:
            raise InvalidSchedulingDecisionError(
                f"Policy proposed job {proposed_job_id!r} which has already COMPLETED."
            )

        if (
            job_state.state != JobLifecycleState.WAITING
            or proposed_job_id not in self._waiting_ids
        ):
            raise InvalidSchedulingDecisionError(
                f"Policy proposed job {proposed_job_id!r} which is not in WAITING state."
            )

        if spec.required_cores > self._available_cores:
            raise InvalidSchedulingDecisionError(
                f"Policy proposed job {proposed_job_id!r} requiring {spec.required_cores} cores, "
                f"but only {self._available_cores} core(s) are available at time {self._current_time}."
            )

        return spec

    def _validate_and_start_job(self, proposed_job_id: JobId) -> None:
        """Validates a proposed job selection and transitions it to RUNNING (UC-E03, UC-E05)."""
        spec = self.validate_proposal(proposed_job_id)
        job_state = self._job_states[proposed_job_id]

        # Remove any existing reservation for this job once it starts
        if self._reservations:
            self._reservations = [
                r for r in self._reservations if r.job_id != proposed_job_id
            ]

        # Mutate state atomically after all checks pass (UC-E03)
        self._waiting_ids.remove(proposed_job_id)
        job_state.state = JobLifecycleState.RUNNING
        job_state.start_time = self._current_time
        job_state.start_count += 1
        self._running_ids.add(proposed_job_id)

        self._available_cores -= spec.required_cores
        self._allocated_cores += spec.required_cores

        completion_time = self._current_time + spec.runtime
        completion_event = self._schedule_event(
            timestamp=completion_time,
            event_type=EventType.COMPLETION,
            job_id=proposed_job_id,
        )
        self._active_completion_events[proposed_job_id] = completion_event

    def _build_scheduler_context(self) -> SchedulerContext:
        """Builds an immutable snapshot of current simulation state for policies."""
        return SchedulerContext(
            current_time=self._current_time,
            total_cores=self._total_cores,
            available_cores=self._available_cores,
            allocated_cores=self._allocated_cores,
            waiting_jobs=self.waiting_jobs,
            running_jobs=self.running_jobs,
            reservations=self.reservations,
        )

    # ------------------------------------------------------------------
    # State and Invariant Verification (Section 7)
    # ------------------------------------------------------------------

    def _assert_invariants(self) -> None:
        """Verifies all 10 engine invariants defined in Section 7."""
        # Invariant 1: 0 <= available_cores <= total_cores
        if not (0 <= self._available_cores <= self._total_cores):
            raise InvariantViolationError(
                f"Invariant 1 violated: available_cores={self._available_cores}, "
                f"total_cores={self._total_cores}."
            )

        # Invariant 2: available_cores + allocated_cores == total_cores
        if self._available_cores + self._allocated_cores != self._total_cores:
            raise InvariantViolationError(
                f"Invariant 2 violated: available ({self._available_cores}) + "
                f"allocated ({self._allocated_cores}) != total ({self._total_cores})."
            )

        running_cores_sum = sum(
            self._job_states[jid].spec.required_cores for jid in self._running_ids
        )
        if self._allocated_cores != running_cores_sum:
            raise InvariantViolationError(
                f"Allocated cores ({self._allocated_cores}) != sum of running job cores "
                f"({running_cores_sum})."
            )

        # Invariant 3: Every running job has exactly one active completion event
        if set(self._active_completion_events.keys()) != self._running_ids:
            raise InvariantViolationError(
                "Invariant 3 violated: mismatch between running_ids and active_completion_events."
            )

        # Verify active completion events actually exist in the event queue
        queued_completion_events = {
            ev.job_id: ev
            for ev in self._event_queue
            if ev.event_type == EventType.COMPLETION
        }
        if queued_completion_events != self._active_completion_events:
            raise InvariantViolationError(
                "Invariant 3 violated: active completion events do not match queued completion events."
            )

        # Invariant 9: A job cannot appear in multiple lifecycle states simultaneously
        total_partition_count = (
            len(self._pending_ids)
            + len(self._waiting_ids)
            + len(self._running_ids)
            + len(self._completed_ids)
        )
        if total_partition_count != len(self._job_states):
            raise InvariantViolationError(
                "Invariant 9 violated: lifecycle sets do not form a strict partition of jobs."
            )
        if (
            (self._pending_ids & self._waiting_ids)
            or (self._pending_ids & self._running_ids)
            or (self._pending_ids & self._completed_ids)
            or (self._waiting_ids & self._running_ids)
            or (self._waiting_ids & self._completed_ids)
            or (self._running_ids & self._completed_ids)
        ):
            raise InvariantViolationError(
                "Invariant 9 violated: a job appears in multiple lifecycle sets simultaneously."
            )

        # Per-job lifecycle invariants (Invariants 4, 5, 6, 7, 8)
        for jid, jstate in self._job_states.items():
            spec = jstate.spec
            # Invariant 8
            if not (0 < spec.required_cores <= self._total_cores):
                raise InvariantViolationError(
                    f"Invariant 8 violated for job {jid!r}: required_cores={spec.required_cores}."
                )
            # Invariant 4
            if jstate.start_count > 1:
                raise InvariantViolationError(
                    f"Invariant 4 violated for job {jid!r}: started {jstate.start_count} times."
                )
            # Invariant 5
            if jstate.completion_count > 1:
                raise InvariantViolationError(
                    f"Invariant 5 violated for job {jid!r}: completed {jstate.completion_count} times."
                )
            # Invariant 6
            if jstate.start_time is not None and jstate.start_time < spec.arrival_time:
                raise InvariantViolationError(
                    f"Invariant 6 violated for job {jid!r}: start_time ({jstate.start_time}) < "
                    f"arrival_time ({spec.arrival_time})."
                )
            # Invariant 7
            if jstate.state == JobLifecycleState.COMPLETED:
                if (
                    jstate.start_time is None
                    or jstate.finish_time is None
                    or jstate.finish_time != jstate.start_time + spec.runtime
                ):
                    raise InvariantViolationError(
                        f"Invariant 7 violated for job {jid!r}: finish_time ({jstate.finish_time}) "
                        f"!= start_time ({jstate.start_time}) + runtime ({spec.runtime})."
                    )

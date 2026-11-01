"""Tests for loading user-defined scheduling policy files."""

from pathlib import Path
import tempfile
import textwrap
import unittest

from adaptive_scheduler.exceptions import ConfigurationError
from adaptive_scheduler.policy_loader import load_policy_from_file
from adaptive_scheduler.interfaces import SchedulingPolicy


class PolicyLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def write_policy(self, source: str, filename: str = "researcher_policy.py") -> Path:
        path = self.directory / filename
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return path

    def test_loads_single_policy_class_without_class_name(self) -> None:
        path = self.write_policy(
            """
            from adaptive_scheduler import JobId, SchedulerContext

            class TestPolicy:
                def select_next_job(self, context: SchedulerContext) -> JobId | None:
                    return None
            """
        )

        policy = load_policy_from_file(path)

        self.assertIsInstance(policy, SchedulingPolicy)
        self.assertEqual(type(policy).__name__, "TestPolicy")

    def test_loads_explicit_class_when_file_contains_multiple_policies(self) -> None:
        path = self.write_policy(
            """
            class FirstPolicy:
                def select_next_job(self, context):
                    return None

            class SecondPolicy:
                def select_next_job(self, context):
                    return None
            """
        )

        policy = load_policy_from_file(path, "SecondPolicy")

        self.assertEqual(type(policy).__name__, "SecondPolicy")

    def test_rejects_ambiguous_policy_file(self) -> None:
        path = self.write_policy(
            """
            class FirstPolicy:
                def select_next_job(self, context):
                    return None

            class SecondPolicy:
                def select_next_job(self, context):
                    return None
            """
        )

        with self.assertRaisesRegex(ConfigurationError, "Multiple scheduling policy classes"):
            load_policy_from_file(path)

    def test_rejects_file_without_policy_class(self) -> None:
        path = self.write_policy("VALUE = 123\n")

        with self.assertRaisesRegex(ConfigurationError, "No scheduling policy class"):
            load_policy_from_file(path)

    def test_rejects_missing_class_name(self) -> None:
        path = self.write_policy(
            """
            class TestPolicy:
                def select_next_job(self, context):
                    return None
            """
        )

        with self.assertRaisesRegex(ConfigurationError, "was not found"):
            load_policy_from_file(path, "MissingPolicy")

    def test_rejects_class_without_required_method(self) -> None:
        path = self.write_policy("class NotAPolicy:\n    pass\n")

        with self.assertRaisesRegex(ConfigurationError, "No scheduling policy class"):
            load_policy_from_file(path)

    def test_rejects_constructor_that_requires_arguments(self) -> None:
        path = self.write_policy(
            """
            class NeedsArgument:
                def __init__(self, value):
                    self.value = value

                def select_next_job(self, context):
                    return None
            """
        )

        with self.assertRaisesRegex(ConfigurationError, "zero-argument constructor"):
            load_policy_from_file(path)

    def test_reports_import_errors(self) -> None:
        path = self.write_policy("raise RuntimeError('broken researcher policy')\n")

        with self.assertRaisesRegex(ConfigurationError, "broken researcher policy"):
            load_policy_from_file(path)

    def test_rejects_non_python_file(self) -> None:
        path = self.directory / "policy.txt"
        path.write_text("not python", encoding="utf-8")

        with self.assertRaisesRegex(ConfigurationError, "must be a Python .py file"):
            load_policy_from_file(path)


if __name__ == "__main__":
    unittest.main()

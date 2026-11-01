"""Run every test from the project root, wherever pytest is started (e.g. the team repo's root).

Test configs name files relative to the project root (tests/workloads/hol_block.csv), like the CLI.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # this checkout's adaptivesched, even when it is not pip-installed


@pytest.fixture(autouse=True, scope="session")
def _run_from_project_root():
    # session scope: module-scoped fixtures (e.g. batch_dir in test_analysis) also need it
    old = os.getcwd()
    os.chdir(ROOT)
    yield
    os.chdir(old)

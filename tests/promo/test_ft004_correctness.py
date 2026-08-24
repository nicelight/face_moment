from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.skip(
    reason=(
        "The real controlled 20-Attempt pilot corpus and authorized manual "
        "evaluator record are external evidence and are unavailable in this workspace."
    )
)
def test_ft004_controlled_twenty_attempt_server_correctness_review() -> None:
    """The final 19/20 pilot claim must be supplied by the authorized evaluator."""

    artifact = Path(".tasks/TASK-075-T3-FT-004-W5/controlled-20-attempt-review.json")
    assert artifact.is_file()

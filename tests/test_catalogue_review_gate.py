"""The review gate: no unreviewed datasheet record may be merged into the catalogue.

This test is meant to be red in a catalogue pull request until the owner has compared every value
with the datasheet and set ``reviewed_by`` / ``review_date`` in the record.
"""

from __future__ import annotations

import pytest

from catalogue_helpers import REAL_RECORDS
from pvsld.catalogue import load_records
from pvsld.cli import main


def test_catalogue_review_gate(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["catalogue", "validate", str(REAL_RECORDS), "--require-reviewed"])
    capsys.readouterr()
    pending = [
        record.path.relative_to(REAL_RECORDS).as_posix()
        for record in load_records(REAL_RECORDS)
        if not record.family.source.reviewed
    ]
    assert not pending, f"records pending owner review: {', '.join(pending)}"
    assert code == 0

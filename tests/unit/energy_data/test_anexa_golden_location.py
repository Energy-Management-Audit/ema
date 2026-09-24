"""The Anexa golden rejects a correct value attributed to the wrong row."""

import pytest
from tests.golden.anexa_location import _field_location
from tests.golden.test_s4_anexa_complete import _same_source

from ema.core.office.sheets import CellRef
from ema.energy_data.source import Located


def test_identity_value_one_row_off_fails_location_check() -> None:
    sheets = {"Date generale": [["Denumirea unităţii", "same"], ["CUI", "same"]]}
    wrong = Located("same", CellRef("Date generale", 2, 2))

    _same_source(sheets, wrong)
    with pytest.raises(AssertionError, match="name"):
        _field_location(sheets, "name", wrong)

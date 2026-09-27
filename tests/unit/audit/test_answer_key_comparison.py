"""The panel answer key permits extra readings but requires every human value."""

from tests.golden.test_s15a_readings_answer_key import _compare


def test_panel_values_and_ranges() -> None:
    expected = {
        "values": [{"quantity": "frequency", "phase": "total", "value": "50,00", "unit": "Hz"}],
        "ranges": [
            {"quantity": "voltage_ln", "phase": "l1", "min": "220", "max": "240", "unit": "V"}
        ],
    }
    assert _compare(
        expected,
        {
            ("frequency", "total", "50.00", "Hz"),
            ("voltage_ln", "l1", "230", "V"),
            ("current", "l1", "10", "A"),
        },
    ) == (2, 0, 1)
    assert _compare(expected, {("frequency", "total", "49.99", "Hz")}) == (0, 2, 1)

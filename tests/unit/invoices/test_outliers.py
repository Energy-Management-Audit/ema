from decimal import Decimal

from ema.invoices.outliers import OUTLIER_RATIO, outliers


def test_outliers_with_two_one_and_no_neighbours() -> None:
    assert Decimal("1.30") == OUTLIER_RATIO
    marked = outliers(
        {
            "2026-01": Decimal(100),
            "2026-02": Decimal(130),
            "2026-03": Decimal(100),
            "2026-05": Decimal(500),
        }
    )
    assert marked["2026-02"] == (Decimal("1.30"), Decimal(100))
    assert "2026-05" not in marked
    assert "2026-01" not in marked
    assert "2026-02" not in outliers({"2026-01": Decimal(100), "2026-02": Decimal(129)})


def test_one_neighbour_and_no_neighbour() -> None:
    assert outliers({"2026-01": Decimal(100), "2026-02": Decimal(140)})["2026-02"] == (
        Decimal("1.4"),
        Decimal(100),
    )
    assert outliers({"2026-01": Decimal(100)}) == {}

from ema.invoices.months import invoice_month, missing_months, month_from_value


def test_month_formats_end_date_and_fallbacks() -> None:
    assert month_from_value("01.01.2026 - 28.02.2026") == "2026-02"
    assert month_from_value("01/01/2026–31/03/2026") == "2026-03"
    assert month_from_value("2026-04-01 – 2026-04-30") == "2026-04"
    assert month_from_value("31.02.2026") is None
    assert (
        invoice_month(
            {
                "consumption_period": {"value": "unreadable"},
                "billing_period": {"value": "01/05/2026–31/05/2026"},
                "invoice_date": {"value": "2026-06-01"},
            }
        )
        == "2026-05"
    )
    assert invoice_month({"invoice_date": {"value": "2026-06-01"}}) == "2026-06"
    assert invoice_month({"invoice_date": {"value": "wrong"}}) is None


def test_missing_months_are_only_between_present_months() -> None:
    assert missing_months({"2025-12", "2026-03"}) == ["2026-01", "2026-02"]
    assert missing_months({"2026-01"}) == []

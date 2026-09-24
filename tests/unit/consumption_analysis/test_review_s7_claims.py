"""Synthetic review cases for claims that require more than a trend direction."""

from ema.consumption_analysis import phrases


def test_trend_does_not_assert_unsupported_largest_share(monkeypatch) -> None:
    pattern = phrases.Phrase(
        "audit-01",
        1,
        "growth",
        "Conform figurii numărul {figure_number}, motorina are ponderea cea mai mare "
        "și consumul ei este în creștere în {year}.",
    )
    monkeypatch.setattr(phrases, "phrase_bank", lambda: (pattern,))

    # Direction alone says nothing about which fuel has the largest share.
    assert (
        phrases.trend_phrase(
            "audit",
            "motorina",
            "growth",
            "4.1",
            2025,
            source_document="audit-01",
            source_paragraph=1,
        )
        is None
    )

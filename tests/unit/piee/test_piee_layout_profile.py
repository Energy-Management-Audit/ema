"""A delivered caption list selects optional PIEE figure groups."""

from ema.energy_data.carriers import Carrier
from ema.piee.layout import LayoutProfile, _layout_from_captions, delivered_layout


def test_base_layout_is_explicit() -> None:
    assert delivered_layout(None) == LayoutProfile()


def test_delivered_layout_matches_caption_kinds_without_case_or_diacritics() -> None:
    layout = _layout_from_captions(
        (
            "Fig. nr. 1 Consumul LUNAR de APĂ industrială",
            "Fig. nr. 2 Evoluția cantității totale de energie ECHIVALENTĂ",
            "Fig. nr. 3 Consumul specific de GAZ natural",
            "Fig. nr. 4 Consumul specific de COCS",
            "Fig. nr. 5 Ponderea consumului specific anual echivalent de energie",
            "Fig. nr. 6 Trendul ponderii energiei în valoarea totală a producției",
            "Fig. nr. 7 Ponderea energiei electrice FOTOVOLTAICE",
            "Fig. nr. 8 Consumul anual de carburant",
            "Fig. nr. 9 Consumul anual de carburant pe tipuri",
        )
    )
    assert layout == LayoutProfile(
        water_monthly=True,
        total_energy_figure=True,
        specific_carriers=frozenset({Carrier.natural_gas, Carrier.coke}),
        separate_pv_figures=True,
        annual_fuel_by_type=True,
        specific_mix_pies=True,
        energy_share_figure=True,
    )

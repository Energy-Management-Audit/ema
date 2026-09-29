"""Romanian meter labels, following the measurement sheet's phase notation."""

QUANTITIES = {
    "frequency": "Frecvența",
    "voltage_ln": "Tensiunea de fază",
    "voltage_ll": "Tensiunea între faze",
    "current": "Curentul",
    "thd_u": "Distorsiunea armonică totală a tensiunii",
    "thd_i": "Distorsiunea armonică totală a curentului",
    "power_active": "Puterea activă",
    "power_reactive": "Puterea reactivă",
    "power_apparent": "Puterea aparentă",
    "power_factor": "Factorul de putere",
    "energy_active": "Energia activă",
    "energy_reactive": "Energia reactivă",
}
PHASES = {
    "l1": "Faza 1",
    "l2": "Faza 2",
    "l3": "Faza 3",
    "n": "Neutru/Rezidual",
    "l12": "Faza 1 - Faza 2",
    "l23": "Faza 2 - Faza 3",
    "l31": "Faza 3 - Faza 1",
    "total": "Total",
    "avg": "Medie",
}
READING_LABELS = {
    (quantity, phase): f"{label} ({PHASES[phase]})"
    for quantity, label in QUANTITIES.items()
    for phase in PHASES
}
READING_LABELS.update(
    {("voltage_ll", phase): f"U {phase[1:]} ({PHASES[phase]})" for phase in ("l12", "l23", "l31")}
)
for phase in ("l1", "l2", "l3"):
    index = phase[1:]
    READING_LABELS["current", phase] = f"I{index} (Curentul pe {PHASES[phase]})"
    READING_LABELS["thd_u", phase] = f"V{index} Total HD ({PHASES[phase]})"
    READING_LABELS["thd_i", phase] = f"I{index} Total HD ({PHASES[phase]})"
READING_LABELS["thd_u", "n"] = "V4 Total HD (Neutru/Rezidual)"

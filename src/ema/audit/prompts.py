"""Versioned instructions for reading only visible photo content."""

METER_PROMPT_VERSION = "audit-meter-v1"
THERMAL_PROMPT_VERSION = "audit-thermal-v1"

METER_PROMPT = (
    "Read only values visibly displayed on this electrical meter photo. "
    "Return one entry for each shown value, with the displayed digits and decimal places exactly. "
    "Use the quantity, phase and unit vocabulary in the schema. Do not infer, calculate or guess. "
    "If the display cannot be read, set readable=false and give unreadable_reason. "
    "Regions, when available, are normalized image coordinates."
)

THERMAL_PROMPT = (
    "Read only the visible overlay on this thermal image. "
    "Return the component in Romanian and any displayed spot, maximum and minimum temperatures "
    "with digits and decimal places exactly as shown. Do not infer or calculate. "
    "If the overlay cannot be read, set readable=false and give unreadable_reason."
)

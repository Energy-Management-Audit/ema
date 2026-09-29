"""Keep the reviewed Romanian display wording byte-for-byte."""

import json
from pathlib import Path


def test_display_copy_keeps_original_diacritics() -> None:
    root = Path(__file__).resolve().parents[2]
    frontend = (root / "frontend/src/audit/readings.ts").read_bytes()
    assert "return 'Ecranul afişat'".encode() in frontend

    resource = (root / "resources/audit/measurement_phrases.json").read_bytes()
    overview = next(item for item in json.loads(resource) if item["id"] == "overview")
    assert overview["template"].encode() == "Valorile afișate".encode()

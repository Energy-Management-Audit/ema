"""Base approval binds the exact classified map, not just the source DOCX."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ema.piee.compose import load_approved_base


def test_changed_map_needs_new_human_approval(tmp_path: Path) -> None:
    map_path = tmp_path / "base-map.json"
    map_path.write_text(json.dumps({"base_sha": "base", "elements": []}), encoding="utf-8")
    (tmp_path / "approval.json").write_text(
        json.dumps(
            {"base_sha": "base", "map_sha": hashlib.sha256(map_path.read_bytes()).hexdigest()}
        ),
        encoding="utf-8",
    )
    assert load_approved_base(tmp_path).base_sha == "base"

    map_path.write_text(
        json.dumps({"base_sha": "base", "elements": []}, indent=2), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not been approved"):
        load_approved_base(tmp_path)

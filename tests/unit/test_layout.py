"""The package layout is part of the architecture, so it is checked, not assumed.

`.importlinter` guards the direction of imports between these modules; this guards
that they exist at all and that the version has one source. See docs/PLAN.md §5.1–§5.2.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

import ema

CORE = "ema.core"
DOMAIN = ["ema.clients", "ema.energy_data", "ema.consumption_analysis"]
WORKFLOWS = ["ema.invoices", "ema.piee", "ema.audit", "ema.reporting"]
INTERFACES = ["ema.api", "ema.cli", "ema.mcp"]


@pytest.mark.parametrize("name", [CORE, *DOMAIN, *WORKFLOWS, *INTERFACES])
def test_module_exists(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_version_has_one_source() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert ema.__version__ == declared

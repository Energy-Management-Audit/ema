"""Write the audit base's identity terms to a local JSON file (EMA_AUDIT_BASE_IDENTITY).

Usage: uv run python scripts/audit_base_identity.py <base.docx> <out.json>
The output names a real client: keep it outside git, next to the base itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ema.audit.base_identity import derive_identity


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    base, out = (Path(item) for item in argv)
    terms = derive_identity(base)
    out.write_text(json.dumps(list(terms), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(terms)} terms written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

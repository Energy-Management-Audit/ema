"""Single-tile locality map with source attribution and explicit fallback."""

from __future__ import annotations

import json
import math
import re
from urllib.parse import quote

from ema.audit.research_web import OutboundGuard, fetch
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


def locality_map(
    ws: Workspace, job: str, guard: OutboundGuard, locality: str, county: str = ""
) -> dict[str, str]:
    if not locality.strip() or len(locality) > 100:
        raise EmaError("map_locality", "Localitatea este invalidă.", "")
    try:
        place = locality.strip().split(",", 1)[0]
        place = re.sub(
            r"^(?:municipiul|orașul|orasul|comuna|satul)\s+", "", place, flags=re.IGNORECASE
        )
        query = quote(
            ", ".join(part for part in (place, county.strip(), "Romania") if part), safe=""
        )
        geocode = fetch(
            ws,
            job,
            guard,
            f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1",
        )
        rows = json.loads(geocode.text)
        if not rows:
            return {"status": "later: map", "reason": "Localitatea nu a fost găsită în OSM."}
        lat, lon = float(rows[0]["lat"]), float(rows[0]["lon"])
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("invalid coordinates")
        zoom = 10
        x = int((lon + 180) / 360 * 2**zoom)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2**zoom)
        tile = fetch(ws, job, guard, f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png")
        return {
            "status": "rendered",
            "snapshot_sha": tile.sha,
            "url": tile.url,
            "attribution": "© OpenStreetMap contributors",
            "retrieved_at": tile.retrieved_at.isoformat(),
        }
    except EmaError as exc:
        return {"status": "later: map", "reason": f"OSM indisponibil: {exc.code}"}
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        return {"status": "later: map", "reason": f"Date OSM invalide: {type(exc).__name__}"}

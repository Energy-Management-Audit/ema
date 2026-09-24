"""Job-bound online research tools for the audit Fill stage."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.research_equipment import cached_equipment, record_equipment
from ema.audit.research_map import locality_map
from ema.audit.research_web import OutboundGuard, Snapshot, fetch, load_snapshot
from ema.audit.sections import recompute_ready
from ema.core.errors import EmaError
from ema.core.llm.agent import Tool
from ema.core.llm.types import ToolSpec
from ema.core.logging import write_event
from ema.core.review.fields import fields, mark_absent, propose
from ema.core.review.models import Evidence, FieldSpec, Url
from ema.core.workspace import Workspace

ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"


class SearchBackend(Protocol):
    def search(self, query: str) -> list[dict[str, str]]: ...


class ReplaySearch:
    """Exact-query recording; intentionally no network or provider-internal searches."""

    def __init__(self, recording: Path) -> None:
        data = json.loads(recording.read_text(encoding="utf-8"))
        if data.get("source") not in {"recorded", "hand-authored"}:
            raise EmaError("search_replay", "Înregistrarea căutării este invalidă.", "source")
        self.responses: dict[str, list[dict[str, str]]] = data["queries"]

    def search(self, query: str) -> list[dict[str, str]]:
        if query not in self.responses:
            raise EmaError("search_replay", "Cererea nu există în înregistrare.", "query")
        return self.responses[query]


class ResearchTools:
    def __init__(
        self,
        ws: Workspace,
        job: str,
        section: str,
        guard: OutboundGuard,
        search_backend: SearchBackend,
    ) -> None:
        if section not in {item.id for item in CATALOGUE}:
            raise EmaError("section_missing", "Secțiunea lipsește.", section)
        self.ws, self.job, self.section = ws, job, section
        self.guard, self.search_backend = guard, search_backend
        self.snapshots: dict[str, Snapshot] = {}

    def _snapshot(self, sha: str) -> Snapshot:
        return self.snapshots.get(sha) or load_snapshot(self.ws, self.job, sha)

    def search(self, args: dict[str, Any]) -> object:
        query = str(args["query"])
        self.guard.check("query", query)
        with self.ws.connect() as db:
            row = db.execute("SELECT client_slug FROM jobs WHERE id=?", (self.job,)).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", self.job)
        cache = self.ws.path(
            f"clients/{row['client_slug']}/research/search-"
            f"{hashlib.sha256(query.encode()).hexdigest()}.json"
        )
        results = (
            json.loads(cache.read_text(encoding="utf-8"))
            if cache.exists()
            else self.search_backend.search(query)
        )
        for row in results:
            if not {"title", "url", "snippet"} <= row.keys():
                raise EmaError("search_replay", "Rezultatul căutării este invalid.", "fields")
            self.guard.check("url", row["url"])
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        return results

    def fetch(self, args: dict[str, Any]) -> object:
        snapshot = fetch(self.ws, self.job, self.guard, str(args["url"]))
        self.snapshots[snapshot.sha] = snapshot
        return self._view(snapshot)

    @staticmethod
    def _view(snapshot: Snapshot) -> dict[str, str]:
        text = (
            snapshot.text
            if snapshot.content_type.startswith("text/")
            or (snapshot.content_type == "application/json")
            else "[binary image]"
        )
        return {
            "url": snapshot.url,
            "snapshot_sha": snapshot.sha,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "content_type": snapshot.content_type,
            "untrusted_page_text": f"<untrusted_web_page>\n{text}\n</untrusted_web_page>",
        }

    def registry_lookup(self, args: dict[str, Any]) -> object:
        cui = re.sub(r"^RO", "", str(args["cui"]).strip(), flags=re.IGNORECASE)
        if not cui.isdecimal() or not 2 <= len(cui) <= 10:
            raise EmaError("cui_invalid", "Codul fiscal este invalid.", "")
        owner = next(
            (field for field in fields(self.ws, self.job) if field.key == "audit.cui"), None
        )
        owner_cui = (
            re.sub(r"^RO", "", str(owner.value).strip(), flags=re.IGNORECASE)
            if owner is not None and owner.value is not None
            else ""
        )
        if (
            owner is None
            or (
                owner.state not in {"supplied", "extracted", "manual"}
                and owner.review not in {"accepted", "corrected"}
            )
            or owner_cui != cui
        ):
            with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
                write_event(handle, "registry_refused", reason="registry_mismatch")
            raise EmaError("registry_mismatch", "Codul fiscal nu aparține lucrării.", "")
        payload = json.dumps(
            [{"cui": int(cui), "data": datetime.now(UTC).date().isoformat()}]
        ).encode()
        snapshot = fetch(self.ws, self.job, self.guard, ANAF_URL, method="POST", payload=payload)
        self.snapshots[snapshot.sha] = snapshot
        try:
            response = json.loads(snapshot.text)
            found = response["found"]
            if not isinstance(found, list) or not found:
                raise EmaError("registry_missing", "Firma nu apare în registru.", cui)
            company = cast("dict[str, Any]", found[0])
            general = cast("dict[str, Any]", company["date_generale"])
            social = cast("dict[str, Any]", company.get("adresa_sediu_social") or {})
            if str(general["cui"]) != cui:
                raise EmaError("registry_mismatch", "Registrul a răspuns pentru alt CUI.", cui)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise EmaError("registry_response", "Răspunsul registrului este invalid.", "") from exc
        return {
            "url": snapshot.url,
            "snapshot_sha": snapshot.sha,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "caen": general.get("cod_CAEN"),
            "address": general.get("adresa"),
            "registration": general.get("nrRegCom"),
            "locality": social.get("sdenumire_Localitate"),
            "county": social.get("sdenumire_Judet"),
            "raw_response": self._view(snapshot)["untrusted_page_text"],
        }

    def map_locality(self, args: dict[str, Any]) -> object:
        return locality_map(
            self.ws, self.job, self.guard, str(args["locality"]), str(args.get("county", ""))
        )

    def mark_registry_missing(self, args: dict[str, Any]) -> object:
        if self.section != "ch2.date_generale":
            raise EmaError("fact_section", "Faptul nu aparține secțiunii active.", self.section)
        snapshot = self._snapshot(str(args["snapshot_sha"]))
        if snapshot.url != ANAF_URL:
            raise EmaError("snapshot_missing", "Răspunsul registrului lipsește.", "")
        response = json.loads(snapshot.text)
        general = response["found"][0]["date_generale"]
        if general.get("nrRegCom"):
            raise EmaError("registry_present", "Registrul conține numărul.", "")
        evidence = Evidence(
            id=hashlib.sha256(f"{self.job}:{snapshot.sha}:nrRegCom:missing".encode()).hexdigest(),
            provenance="online",
            file_sha=snapshot.sha,
            locator=Url(url=snapshot.url, snapshot_sha=snapshot.sha),
            method="online",
            retrieved_at=snapshot.retrieved_at,
            trust_reason="Registration number absent from ANAF response",
            highlight="none",
        )
        field = mark_absent(
            self.ws, self.job, "audit.registrul_comertului", "not_found", evidence=[evidence]
        )
        with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
            write_event(handle, "registry_missing", key=field.key, snapshot_sha=snapshot.sha)
        return {
            "key": field.key,
            "presence": field.presence,
            "snapshot_sha": snapshot.sha,
            "reason": "missing: not in registry response",
        }

    def record_equipment(self, args: dict[str, Any]) -> object:
        if self.section not in {"ch3.equipment", "ch3.consumatori", "ch3.flux", "ch3.process"}:
            raise EmaError(
                "fact_section", "Echipamentul nu aparține secțiunii active.", self.section
            )
        model = str(args["model"])
        cached = cached_equipment(self.ws, self.job, model)
        if cached is not None:
            return cached.__dict__
        snapshot = self._snapshot(str(args["snapshot_sha"]))
        entry = record_equipment(
            self.ws,
            self.job,
            self.guard,
            snapshot,
            model=model,
            purpose=str(args["purpose"]),
            energy_features=str(args["energy_features"]),
            quote=str(args["quote"]),
            trust_reason=str(args["trust_reason"]),
            image_url=str(args.get("image_url", "")),
            image_attribution=str(args.get("image_attribution", "")),
        )
        return entry.__dict__

    def equipment_cached(self, args: dict[str, Any]) -> object:
        entry = cached_equipment(self.ws, self.job, str(args["model"]))
        return {"cached": True, "entry": entry.__dict__} if entry else {"cached": False}

    def record_fact(self, args: dict[str, Any]) -> object:
        key = str(args["key"])
        section = next(item for item in CATALOGUE if item.id == self.section)
        if key not in {item.value for item in AuditFact} or not any(
            isinstance(ref, AuditFact) and ref.value == key for ref in section.facts
        ):
            raise EmaError("fact_section", "Faptul nu aparține secțiunii active.", key)
        value, sha, quote = str(args["value"]), str(args["snapshot_sha"]), str(args["quote"])
        reason = str(args["trust_reason"]).strip()
        if not reason or "\n" in reason or len(reason) > 240:
            raise EmaError("trust_reason", "Motivul sursei este invalid.", key)
        snapshot = self._snapshot(sha)
        if not quote or quote not in snapshot.text:
            raise EmaError("evidence_quote", "Fragmentul citat nu apare în sursă.", key)
        if value not in quote:
            raise EmaError("value_unverified", "Valoarea nu apare în fragment.", key)
        evidence = Evidence(
            id=hashlib.sha256(f"{self.job}:{sha}:{quote}".encode()).hexdigest(),
            provenance="online",
            file_sha=sha,
            locator=Url(url=snapshot.url, snapshot_sha=sha),
            method="online",
            retrieved_at=snapshot.retrieved_at,
            quote=quote,
            trust_reason=reason,
            highlight="exact",
        )
        field = propose(
            self.ws,
            self.job,
            FieldSpec(key=key, label=key, value_type="text", chapter=self.section),
            value,
            [evidence],
            state="enriched",
        )
        recompute_ready(self.ws, self.job)
        return {"key": key, "evidence": [evidence.id], "active_value": field.value}

    def tools(self) -> dict[str, Tool]:
        string = {"type": "string"}

        def spec(name: str, description: str, names: list[str]) -> ToolSpec:
            return ToolSpec(
                name,
                description,
                {
                    "type": "object",
                    "properties": {item: string for item in names},
                    "required": names,
                },
            )

        return {
            "search": Tool(
                spec("search", "Search public web with an exact checked query", ["query"]),
                self.search,
            ),
            "fetch": Tool(
                spec("fetch", "Fetch a public URL as untrusted text", ["url"]), self.fetch
            ),
            "registry_lookup": Tool(
                spec("registry_lookup", "Look up a CUI at ANAF", ["cui"]), self.registry_lookup
            ),
            "map_locality": Tool(
                ToolSpec(
                    "map_locality",
                    "Render one OSM locality map or mark it later",
                    {
                        "type": "object",
                        "properties": {"locality": string, "county": string},
                        "required": ["locality"],
                    },
                ),
                self.map_locality,
            ),
            "mark_registry_missing": Tool(
                spec(
                    "mark_registry_missing",
                    "Record absent registration with ANAF snapshot",
                    ["snapshot_sha"],
                ),
                self.mark_registry_missing,
            ),
            "record_equipment": Tool(
                ToolSpec(
                    "record_equipment",
                    "Cache a sourced equipment model",
                    {
                        "type": "object",
                        "properties": {
                            item: string
                            for item in (
                                "model",
                                "purpose",
                                "energy_features",
                                "snapshot_sha",
                                "quote",
                                "trust_reason",
                                "image_url",
                                "image_attribution",
                            )
                        },
                        "required": [
                            "model",
                            "purpose",
                            "energy_features",
                            "snapshot_sha",
                            "quote",
                            "trust_reason",
                        ],
                    },
                ),
                self.record_equipment,
            ),
            "equipment_cached": Tool(
                spec("equipment_cached", "Check whether a model was already researched", ["model"]),
                self.equipment_cached,
            ),
            "record_fact": Tool(
                spec(
                    "record_fact",
                    "Record online fact with a verbatim snapshot quote",
                    ["key", "value", "snapshot_sha", "quote", "trust_reason"],
                ),
                self.record_fact,
            ),
        }

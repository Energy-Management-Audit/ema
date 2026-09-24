"""Evidence-backed proposal for one invoice batch client."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ema.clients import KnownClient, check_conflicts, find_by_cui, find_by_pod
from ema.core.errors import EmaError
from ema.core.jobs import latest_ready_run
from ema.core.review import fields, mark_absent, propose
from ema.core.review.models import Evidence, Field, FieldSpec, Manual, PdfText
from ema.core.workspace import Workspace
from ema.invoices.models import normalize_client_name, normalize_client_tax_id

KEY = "invoice.batch_client"
SPEC = FieldSpec(key=KEY, label="Clientul lotului de facturi", value_type="text", required=True)
_LEGAL_SUFFIX = re.compile(r"(?:S\.?R\.?L\.?|S\.?A\.?)\s*$", re.I)


@dataclass(frozen=True)
class BatchClient:
    run_id: str
    name: str
    tax_id: str | None
    pods: tuple[str, ...]
    candidates: tuple[dict[str, Any], ...]
    disagreements: tuple[str, ...]
    pod_fill: tuple[dict[str, Any], ...]
    memory: tuple[dict[str, str], ...]

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_field(cls, field: Field) -> BatchClient:
        data = json.loads(str(field.value))
        return cls(
            str(data["run_id"]),
            str(data["name"]),
            data["tax_id"],
            tuple(data["pods"]),
            tuple(data["candidates"]),
            tuple(data["disagreements"]),
            tuple(data["pod_fill"]),
            tuple(data["memory"]),
        )


def _source_hashes(ws: Workspace, job: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for slot in ws.list_slots(job, "invoices"):
        versions = ws.list_versions(job, slot)
        if versions:
            active = versions[-1]
            mapping[active.origin] = active.file_sha
    return mapping


def _names(field: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    if field.get("value"):
        result.append((str(field["value"]), field["evidence"][0] if field["evidence"] else {}))
    if field.get("status") == "ambiguous":
        for evidence in field.get("evidence", []):
            snippet = str(evidence["snippet"])
            candidate = snippet.split(":", 1)[-1].strip()
            if candidate:
                result.append((candidate, evidence))
    return result


def _choose_name(names: list[str]) -> str | None:
    if not names:
        return None
    counts = Counter(names)
    return max(counts, key=lambda name: (bool(_LEGAL_SUFFIX.search(name)), counts[name], len(name)))


def _memory(ws: Workspace, tax_id: str | None, pods: set[str]) -> list[KnownClient]:
    entries = [item for pod in pods for item in find_by_pod(ws, pod)]
    if tax_id:
        entries.extend(find_by_cui(ws, tax_id))
    return list({(item.kind, item.identifier, item.decision_id): item for item in entries}.values())


def build(  # noqa: C901
    ws: Workspace, job: str, rows: list[dict[str, Any]]
) -> tuple[BatchClient, list[Evidence]] | None:
    names: list[str] = []
    taxes: list[str] = []
    pods: set[str] = set()
    candidates: list[dict[str, Any]] = []
    proof: list[Evidence] = []
    sha_by_name = _source_hashes(ws, job)
    supplier_pods: dict[str, set[str]] = defaultdict(set)
    missing_pods: dict[str, list[str]] = defaultdict(list)
    pod_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        filename = str(row["source_path"])
        for draft in row.get("drafts", []):
            supplier = str(draft.get("supplier") or "")
            data = draft["fields"]
            name_fields = _names(data.get("client_name", {}))
            tax_field = data.get("client_tax_id", {})
            pod_field = data.get("location_identifier", {})
            printed_tax = str(tax_field["value"]) if tax_field.get("value") else None
            if printed_tax:
                taxes.append(printed_tax)
            printed_pod = str(pod_field.get("value") or "")
            if printed_pod:
                pods.add(printed_pod)
                supplier_pods[supplier].add(printed_pod)
                pod_sources[printed_pod].extend(
                    [
                        {"file": filename, "page": item["page_number"], "snippet": item["snippet"]}
                        for item in pod_field.get("evidence", [])
                    ]
                )
            elif row["status"] not in {"incompatible", "failed", "duplicate"}:
                missing_pods[supplier].append(filename)
            candidates.append(
                {
                    "file": filename,
                    "supplier": supplier,
                    "names": [name for name, _ in name_fields],
                    "tax_id": printed_tax,
                    "pod": printed_pod or None,
                    "evidence": [
                        {"field": key, "page": item["page_number"], "snippet": item["snippet"]}
                        for key, source in (
                            ("client_name", data.get("client_name", {})),
                            ("client_tax_id", tax_field),
                            ("location_identifier", pod_field),
                        )
                        for item in source.get("evidence", [])
                    ],
                }
            )
            for name, _ in name_fields:
                names.append(name)
            for source_field in (data.get("client_name", {}), tax_field, pod_field):
                for item in source_field.get("evidence", []):
                    if filename not in sha_by_name:
                        continue
                    snippet = str(item["snippet"])
                    proof.append(
                        Evidence(
                            id=uuid.uuid4().hex,
                            provenance="document",
                            file_sha=sha_by_name[filename],
                            locator=PdfText(page=int(item["page_number"]), span=snippet),
                            method="invoice",
                            retrieved_at=datetime.now(UTC),
                            quote=snippet,
                            highlight="page",
                        )
                    )
    tax_id = Counter(taxes).most_common(1)[0][0] if taxes else None
    remembered = _memory(ws, tax_id, pods)
    memory_names = {item.legal_name for item in remembered}
    memory_taxes = {item.tax_id for item in remembered if item.tax_id}
    if (
        len(memory_names) > 1
        or len(memory_taxes) > 1
        or (
            tax_id
            and memory_taxes
            and normalize_client_tax_id(tax_id)
            not in {normalize_client_tax_id(item) for item in memory_taxes}
        )
    ):
        raise EmaError(
            "client_memory_conflict", "Identitatea clientului intră în conflict cu memoria.", job
        )
    name = next(iter(memory_names), None) or _choose_name(names)
    if name is None:
        return None
    tax_id = tax_id or next(iter(memory_taxes), None)
    with ws.connect() as db:
        check_conflicts(db, tax_id=tax_id, pods=pods, name=name)
    for item in remembered:
        proof.append(
            Evidence(
                id=uuid.uuid4().hex,
                provenance="manual",
                locator=Manual(who="ema", note=f"Memory decision {item.decision_id}"),
                method="manual",
                retrieved_at=datetime.now(UTC),
                quote=f"Confirmed in job {item.job_id}, decision {item.decision_id}",
                highlight="none",
            )
        )
    chosen = normalize_client_name(name)
    disagreements = tuple(
        sorted(
            {
                str(item["file"])
                for item in candidates
                if (
                    item["names"]
                    and all(normalize_client_name(str(value)) != chosen for value in item["names"])
                )
                or (
                    item["tax_id"]
                    and tax_id
                    and normalize_client_tax_id(item["tax_id"]) != normalize_client_tax_id(tax_id)
                )
            }
        )
    )
    fills = tuple(
        {
            "supplier": supplier,
            "pod": next(iter(supplier_pods[supplier])),
            "files": sorted(set(filenames)),
            "sources": pod_sources[next(iter(supplier_pods[supplier]))],
        }
        for supplier, filenames in missing_pods.items()
        if len(supplier_pods[supplier]) == 1
    )
    return BatchClient(
        str(latest_ready_run(ws, job, "invoices")),
        name,
        tax_id,
        tuple(sorted(pods)),
        tuple(candidates),
        disagreements,
        fills,
        tuple(
            {
                "kind": item.kind,
                "identifier": item.identifier,
                "job": item.job_id,
                "decision": item.decision_id,
            }
            for item in remembered
        ),
    ), proof


def proposal(ws: Workspace, job: str, rows: list[dict[str, Any]]) -> Field:
    existing = next((item for item in fields(ws, job) if item.key == KEY), None)
    run = latest_ready_run(ws, job, "invoices")
    if (
        existing is not None
        and existing.value is not None
        and BatchClient.from_field(existing).run_id == run
    ):
        return existing
    built = build(ws, job, rows)
    if built is None:
        return mark_absent(ws, job, SPEC, "not_found")
    data, evidence = built
    return propose(ws, job, SPEC, data.to_json(), evidence, state="enriched")

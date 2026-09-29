"""Invoice identity HTTP views over a single batch snapshot."""

from typing import Any, cast

from ema.core.jobs import JobId
from ema.core.workspace import Workspace
from ema.invoices.identity_review import BatchSnapshot, batch_snapshot, matches_name
from ema.invoices.models import normalize_client_tax_id


def identity_view(ws: Workspace, job: JobId) -> dict[str, Any]:
    return identity_from_snapshot(batch_snapshot(ws, job))


def identity_from_snapshot(snapshot: BatchSnapshot) -> dict[str, Any]:
    field, client, outcomes = snapshot.field, snapshot.client, snapshot.rows
    printed = 0
    other_client = 0
    if client is not None:
        for outcome in outcomes:
            for draft in outcome["drafts"]:
                values = cast("dict[str, Any]", draft["fields"])
                name = cast("dict[str, Any]", values.get("client_name") or {})
                tax = cast("dict[str, Any]", values.get("client_tax_id") or {})
                if name.get("value") and matches_name(name, client.name):
                    printed += 1
                if (name.get("value") and not matches_name(name, client.name)) or (
                    client.tax_id
                    and tax.get("value")
                    and normalize_client_tax_id(str(tax["value"]))
                    != normalize_client_tax_id(client.tax_id)
                ):
                    other_client += 1
    candidate = (
        {
            "client_id": snapshot.client_slug,
            "cui": client.tax_id,
            "pod": client.pods[0] if client.pods else None,
        }
        if client is not None
        else None
    )
    return {
        "batch_id": snapshot.run_id,
        "candidate": candidate,
        "confirmed": field.review in {"accepted", "corrected"},
        "evidence_ids": field.evidence,
        "revision": field.revision,
        "name": client.name if client else None,
        "reasons": {
            "printed": printed,
            "pods": list(client.pods) if client else [],
            "other_client": other_client,
        },
        "pod_fill": [
            {
                "pod": str(item["pod"]),
                "files": list(item["files"]),
                "source_count": len(
                    {source.get("sha") or source["file"] for source in item["sources"]}
                ),
            }
            for item in (client.pod_fill if client is not None else ())
        ],
        "memory": list(client.memory) if client else [],
        "files_total": len(outcomes),
        "client_cui": snapshot.client_cui,
    }

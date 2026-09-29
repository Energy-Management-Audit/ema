"""Cross-workflow job summaries and their finalized rule."""

from typing import Any

from ema.core.jobs import activity
from ema.core.workspace import Workspace


def job_overview(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        db.execute("BEGIN")
        updated = activity(db)
        rows = db.execute(
            "SELECT j.id,j.type,j.client_slug,c.name AS client_name,j.year,j.state,"
            "j.revision,j.created_at,"
            "(SELECT MAX(a.at) FROM approvals a WHERE a.job_id=j.id) AS approved_at,"
            "(SELECT COUNT(*) FROM outputs o WHERE o.job_id=j.id AND o.kind='final') "
            "AS final_outputs FROM jobs j LEFT JOIN clients c ON c.id=j.client_slug "
            "WHERE j.deleted=0 AND j.type!='reporting'"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["updated_at"] = updated.get(str(item["id"]), str(item["created_at"]))
        final_outputs = item.pop("final_outputs")
        item["finalized"] = item["approved_at"] is not None or (
            item["type"] == "invoices" and final_outputs > 0
        )
        result.append(item)
    return sorted(result, key=lambda item: item["updated_at"], reverse=True)

"""Export integrity regressions."""

import time
from pathlib import Path

from ema.core.jobs import StageOutcome, create_job, run_stage, status
from ema.core.review import export
from ema.core.review.models import Readiness
from ema.core.workspace import Workspace


class InterleavedWorkflow:
    def readiness(self, ws: Workspace, job: str) -> Readiness:
        return Readiness(draft_ok=True, final_ok=False, blocking=[], next=[])

    def render(self, ws: Workspace, job: str, kind: str) -> str:
        def stage(ctx):  # type: ignore[no-untyped-def]
            source = ctx.artifact_dir() / f"{kind}.txt"
            source.write_text(kind)
            ctx.save_output(source, source.name, kind=kind)
            return StageOutcome()

        run_stage(ws, job, "render", stage)
        for _ in range(200):
            if status(ws, job).state != "running":
                break
            time.sleep(0.01)
        with ws.connect() as db:
            row = db.execute(
                "SELECT id FROM outputs WHERE job_id=? ORDER BY seq DESC LIMIT 1", (job,)
            ).fetchone()
        output_id = str(row[0])
        if kind == "draft":
            self.render(ws, job, "final")
        return output_id

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]:
        return {}


def test_draft_export_uses_rendered_id_when_final_interleaves(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    destination = tmp_path / "draft.txt"
    assert (
        export(ws, job, InterleavedWorkflow(), final=False, dest=destination, actor="user")
        == destination
    )
    assert destination.read_text() == "draft"

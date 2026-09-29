"""Online research trust boundary without network or client material."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit import research_web
from ema.audit.research_equipment import record_equipment
from ema.audit.research_tools import ANAF_URL, ResearchTools
from ema.audit.research_web import OutboundGuard, Snapshot
from ema.core.errors import EmaError
from ema.core.review.fields import fields, propose
from ema.core.review.models import Evidence, FieldSpec, Manual
from ema.core.workspace import Workspace


class Search:
    def search(self, query: str) -> list[dict[str, str]]:
        return [{"title": query, "url": "https://example.org/e", "snippet": "public"}]


def setup(tmp_path: Path) -> tuple[ResearchTools, Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    guard = OutboundGuard(ws, job, ("Contact: secret@example.org",))
    return ResearchTools(ws, job, "ch2.date_generale", guard, Search()), ws, job


def test_private_query_refused_and_logged(tmp_path: Path) -> None:
    tools, ws, job = setup(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.search({"query": "secret@example.org company"})
    assert error.value.code == "outbound_refused"
    with ws.connect() as db:
        log = (ws.job_path(db, job) / "log.jsonl").read_text(encoding="utf-8")
    assert '"verdict": "private_value"' in log
    assert "secret@example.org" not in log
    with pytest.raises(EmaError) as encoded:
        tools.guard.check("url", "https://example.org/?q=secret%40example.org")
    assert encoded.value.code == "outbound_refused"


def test_dataset_decimal_is_private(tmp_path: Path) -> None:
    _, ws, job = setup(tmp_path)
    propose(
        ws,
        job,
        FieldSpec(key="audit.energy_cost", label="Cost", value_type="number"),
        Decimal("1234.56"),
        [],
        state="extracted",
    )
    guard = OutboundGuard(ws, job)
    with pytest.raises(EmaError) as error:
        guard.check("query", "company energy cost 1.234,56")
    assert error.value.code == "outbound_refused"


def test_local_address_and_redirect_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools, _, _ = setup(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.fetch({"url": "http://127.0.0.1/admin"})

    assert error.value.code == "web_private"

    request = research_web._request

    def redirect(
        url: str, method: str, payload: bytes | None
    ) -> tuple[int, str, bytes, str | None]:
        if url == "https://example.org/start":
            return 302, "text/html", b"", "http://127.0.0.1/admin"
        return request(url, method, payload)

    monkeypatch.setattr(research_web, "_request", redirect)
    with pytest.raises(EmaError) as error:
        tools.fetch({"url": "https://example.org/start"})
    assert error.value.code == "web_private"


def test_online_quote_and_supplied_first(tmp_path: Path) -> None:
    tools, ws, job = setup(tmp_path)
    evidence = Evidence(
        id="manual",
        provenance="manual",
        locator=Manual(who="user"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="none",
    )
    propose(
        ws,
        job,
        FieldSpec(key="audit.address", label="Address", value_type="text"),
        "Supplied address",
        [evidence],
        state="supplied",
    )
    tools.snapshots["sha"] = Snapshot(
        "https://example.org/company",
        "sha",
        datetime.now(UTC),
        "text/plain",
        b"Registered address: Online address",
    )
    with pytest.raises(EmaError) as error:
        tools.record_fact(
            {
                "key": "audit.address",
                "value": "Online address",
                "snapshot_sha": "sha",
                "quote": "Invented address",
                "trust_reason": "Official register",
            }
        )
    assert error.value.code == "evidence_quote"
    result = tools.record_fact(
        {
            "key": "audit.address",
            "value": "Online address",
            "snapshot_sha": "sha",
            "quote": "Registered address: Online address",
            "trust_reason": "Official register",
        }
    )
    field = next(field for field in fields(ws, job) if field.key == "audit.address")
    assert result["active_value"] == "Supplied address"
    assert field.value == "Supplied address"
    assert any(candidate.value == "Online address" for candidate in field.alternatives)


def test_equipment_model_cached_with_source(tmp_path: Path) -> None:
    tools, ws, job = setup(tmp_path)
    page = tmp_path / "page.txt"
    page.write_text("Example Motor X pumps water with variable speed.", encoding="utf-8")
    sha = ws.add_file("synthetic", page)
    snapshot = Snapshot(
        "https://example.org/motor", sha, datetime.now(UTC), "text/plain", page.read_bytes()
    )
    with pytest.raises(EmaError) as error:
        record_equipment(
            ws,
            job,
            tools.guard,
            snapshot,
            model="Example Motor X",
            purpose="pumps water",
            energy_features="variable speed",
            quote="fabricated",
            trust_reason="Synthetic manufacturer page",
        )
    assert error.value.code == "evidence_quote"
    first = record_equipment(
        ws,
        job,
        tools.guard,
        snapshot,
        model="Example Motor X",
        purpose="pumps water",
        energy_features="variable speed",
        quote=snapshot.text,
        trust_reason="Synthetic manufacturer page",
    )
    second = record_equipment(
        ws,
        job,
        tools.guard,
        snapshot,
        model="Example Motor X",
        purpose="ignored",
        energy_features="ignored",
        quote="ignored",
        trust_reason="Synthetic manufacturer page",
    )
    assert first == second
    assert first.image_status == "later: visit photo"
    assert tools.equipment_cached({"model": "Example Motor X"})["cached"] is True
    assert any(field.key.startswith("audit.equipment.") for field in fields(ws, job))
    next_job = create_job(ws, "audit", "synthetic", 2027)
    next_tools = ResearchTools(ws, next_job, "ch3.equipment", OutboundGuard(ws, next_job), Search())
    assert next_tools.equipment_cached({"model": "Example Motor X"})["cached"] is True
    assert any(field.key.startswith("audit.equipment.") for field in fields(ws, next_job))


def test_snapshot_survives_new_tool_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools, ws, job = setup(tmp_path)

    def page(url: str, method: str, payload: bytes | None) -> tuple[int, str, bytes, None]:
        del url, method, payload
        return 200, "text/plain", b"Exampleville is fictional.", None

    monkeypatch.setattr(research_web, "_request", page)
    view = tools.fetch({"url": "https://example.org/place"})
    second = ResearchTools(ws, job, "ch2.localizare", tools.guard, Search())
    record = second.record_fact(
        {
            "key": "audit.location",
            "value": "Exampleville",
            "snapshot_sha": view["snapshot_sha"],
            "quote": "Exampleville is fictional.",
            "trust_reason": "Synthetic page",
        }
    )
    assert record["evidence"]


def test_registry_absence_keeps_snapshot_evidence(tmp_path: Path) -> None:
    tools, ws, job = setup(tmp_path)
    snapshot = Snapshot(
        ANAF_URL,
        "sha",
        datetime.now(UTC),
        "application/json",
        b'{"found":[{"date_generale":{"nrRegCom":null}}]}',
    )
    tools.snapshots["sha"] = snapshot
    result = tools.mark_registry_missing({"snapshot_sha": "sha"})
    assert result["presence"] == "not_found"
    field = next(field for field in fields(ws, job) if field.key == "audit.registrul_comertului")
    assert field.evidence


def test_search_cache_reused_for_client(tmp_path: Path) -> None:
    tools, ws, _ = setup(tmp_path)
    first = tools.search({"query": "Exampleville location"})
    second_job = create_job(ws, "audit", "synthetic", 2027)

    class NoSearch:
        def search(self, query: str) -> list[dict[str, str]]:
            raise AssertionError(f"backend called for cached query: {query}")

    repeated = ResearchTools(
        ws, second_job, "ch2.localizare", OutboundGuard(ws, second_job), NoSearch()
    )
    assert repeated.search({"query": "Exampleville location"}) == first

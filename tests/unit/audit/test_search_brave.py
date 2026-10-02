import httpx
import pytest
from pydantic import SecretStr

from ema.audit.research_tools import ReplaySearch
from ema.audit.search_brave import BRAVE_URL, BraveSearch, select_search_backend
from ema.core.config import Settings
from ema.core.errors import EmaError

KEY = "synthetic-brave-key"


def _search(handler: httpx.MockTransport | None, seen: list[httpx.Request] | None = None):
    def respond(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        assert handler is not None
        return handler.handler(request)

    return BraveSearch(SecretStr(KEY), httpx.Client(transport=httpx.MockTransport(respond)))


def test_request_shape_and_response_mapping() -> None:
    seen: list[httpx.Request] = []
    body = {
        "web": {
            "results": [
                {
                    "title": "Pump <b>X1</b>",
                    "url": "https://a.example/x1",
                    "description": "<strong>5 kW</strong> &amp; more",
                },
                {"title": "Other", "url": "https://b.example/"},
            ]
        }
    }
    backend = _search(httpx.MockTransport(lambda r: httpx.Response(200, json=body)), seen)

    results = backend.search("pump x1 datasheet")

    assert results == [
        {"title": "Pump X1", "url": "https://a.example/x1", "snippet": "5 kW & more"},
        {"title": "Other", "url": "https://b.example/", "snippet": ""},
    ]
    (request,) = seen
    assert str(request.url).startswith(BRAVE_URL + "?")
    assert request.url.params["q"] == "pump x1 datasheet"
    assert request.headers["X-Subscription-Token"] == KEY
    assert request.method == "GET"


def test_no_web_section_is_an_empty_result() -> None:
    backend = _search(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    assert backend.search("q") == []


@pytest.mark.parametrize("status", [401, 429, 500])
def test_error_status_surfaces_without_the_key(status: int) -> None:
    backend = _search(httpx.MockTransport(lambda r: httpx.Response(status, text="no")))
    with pytest.raises(EmaError) as raised:
        backend.search("q")
    assert raised.value.code == "search_status"
    assert KEY not in repr(raised.value.__dict__)
    assert str(status) in repr(raised.value.__dict__)


def test_transport_failure_and_malformed_body_are_errors() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    with pytest.raises(EmaError) as down:
        _search(httpx.MockTransport(refuse)).search("q")
    assert down.value.code == "search_unavailable"
    bad = _search(
        httpx.MockTransport(
            lambda r: httpx.Response(200, json={"web": {"results": [{"title": "t"}]}})
        )
    )
    with pytest.raises(EmaError) as malformed:
        bad.search("q")
    assert malformed.value.code == "search_response"


def test_selection_is_live_only_with_key_and_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr("ema.core.config.keyring.get_password", lambda s, n: store.get((s, n)))
    monkeypatch.delenv("EMA_BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("EMA_RESEARCH_LIVE", raising=False)
    recording = tmp_path / "r.json"
    recording.write_text('{"source": "hand-authored", "queries": {}}', encoding="utf-8")
    replay = ReplaySearch(recording)

    assert select_search_backend(Settings(), replay) is replay
    store[("Ema", "brave_api_key")] = KEY
    assert select_search_backend(Settings(), replay) is replay
    live = select_search_backend(Settings(research_live=True), replay)
    assert isinstance(live, BraveSearch)
    store.clear()
    assert select_search_backend(Settings(research_live=True), replay) is replay
    monkeypatch.setenv("EMA_BRAVE_API_KEY", "env-key")
    assert isinstance(select_search_backend(Settings(research_live=True), replay), BraveSearch)

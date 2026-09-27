"""Public release parsing without outbound traffic."""

import json
from http.client import HTTPException

import pytest

from ema.core import web
from ema.core.errors import EmaError
from ema.core.updates import RELEASES_URL, check_update


def _fetch(release: dict[str, object]):
    def fetch(url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        assert (url, allowed_host) == (RELEASES_URL, "api.github.com")
        return url, "application/json", json.dumps(release).encode()

    return fetch


def _release(tag: str, **changes: object) -> dict[str, object]:
    return {
        "tag_name": tag,
        "body": "Notes",
        "html_url": f"https://github.com/Energy-Management-Audit/ema-releases/releases/tag/{tag}",
        "assets": [
            {
                "name": f"Ema-Setup-{tag[1:]}.exe",
                "browser_download_url": f"https://github.com/Energy-Management-Audit/ema-releases/releases/download/{tag}/Ema-Setup-{tag[1:]}.exe",
            }
        ],
        **changes,
    }


def test_newer_equal_and_older() -> None:
    for tag, newer in (("v1.2.4", True), ("v1.2.3", False), ("v1.2.2", False)):
        result = check_update("1.2.3", fetch=_fetch(_release(tag)))
        assert (result.state, result.latest, result.newer, result.notes) == (
            "ok",
            tag[1:],
            newer,
            "Notes",
        )
        assert result.download_url is not None
        assert result.checked_at.endswith("+00:00")


def test_404_and_network_error() -> None:
    def missing(_url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        raise EmaError("web_status", "synthetic", "404")

    def offline(_url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        raise EmaError("web_dns", "synthetic", "")

    assert check_update("1.2.3", fetch=missing).state == "no_release"
    assert check_update("1.2.3", fetch=offline).state == "unavailable"


@pytest.mark.parametrize("error", [HTTPException("synthetic"), OSError("synthetic")])
def test_transport_error_is_unavailable(error: Exception) -> None:
    def broken(_url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        raise error

    result = check_update("1.2.3", fetch=broken)
    assert (result.state, result.newer, result.latest) == ("unavailable", False, None)


def test_bad_json_tag_and_untrusted_urls() -> None:
    def bad_json(_url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        return "", "application/json", b"{invalid"

    assert check_update("1.2.3", fetch=bad_json).state == "unavailable"
    assert check_update("1.2.3", fetch=_fetch(_release("1.2.4"))).state == "unavailable"
    release = _release("v1.2.4", body="x" * 4100, html_url="https://example.com/unsafe")
    release["assets"] = [
        {
            "name": "Ema-Setup-1.2.4.exe",
            "browser_download_url": "https://example.com/unsafe.exe",
        }
    ]
    result = check_update("1.2.3", fetch=_fetch(release))
    assert result.notes == "x" * 4000
    assert result.download_url is None
    assert result.page_url == (
        "https://github.com/Energy-Management-Audit/ema-releases/releases/tag/v1.2.4"
    )
    assert result.newer is True


def test_malformed_tag_never_produces_fallback() -> None:
    result = check_update("1.2.3", fetch=_fetch(_release("v1.2.4/unsafe")))
    assert (result.state, result.newer, result.page_url) == ("unavailable", False, None)


def test_non_ascii_version_digits_are_rejected() -> None:
    tag = check_update("1.2.3", fetch=_fetch(_release("v١.2.4")))
    current = check_update("١.2.3", fetch=_fetch(_release("v1.2.4")))
    assert (tag.state, tag.newer, tag.page_url) == ("unavailable", False, None)
    assert (current.state, current.newer, current.page_url) == ("unavailable", False, None)


def test_update_request_has_only_fixed_public_url_and_plain_headers(monkeypatch) -> None:
    sent: list[tuple[str, str, bytes | None, dict[str, str]]] = []
    sent_body = [False]

    class Response:
        status = 200
        length = None

        def getheader(self, name: str, default: str = "") -> str:
            return "application/json" if name == "Content-Type" else default

        def read(self, _size: int) -> bytes:
            if sent_body[0]:
                return b""
            sent_body[0] = True
            return json.dumps(_release("v0.2.0")).encode()

    class Connection:
        sock = None

        def __init__(self, _host: str, _port: int, _ip: str, _timeout: float) -> None:
            pass

        def request(
            self, method: str, target: str, *, body: bytes | None, headers: dict[str, str]
        ) -> None:
            sent.append((method, target, body, headers))

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(web, "_public_ip", lambda _host, _port: "192.0.2.1")
    monkeypatch.setattr(web, "_PinnedHTTPS", Connection)
    assert check_update("0.1.0").newer is True
    assert sent == [
        (
            "GET",
            "/repos/Energy-Management-Audit/ema-releases/releases/latest",
            None,
            {
                "Host": "api.github.com",
                "User-Agent": "EmaResearch/1",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        )
    ]

"""Bounded outbound HTTP transport with DNS pinning and redirect checks."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from ema.core.errors import EmaError

MAX_BODY = 2_000_000
_ALLOWED_TYPES = ("text/html", "text/plain", "application/json", "image/png", "image/jpeg")


def _public_ip(host: str, port: int) -> str:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise EmaError("web_dns", "Adresa sursei nu poate fi rezolvată.", host) from exc
    ips = {item[4][0] for item in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise EmaError("web_private", "Sursa online nu este publică.", host)
    return str(sorted(ips)[0])


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self.ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self.ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip
        self.tls_context = ssl.create_default_context()

    def connect(self) -> None:
        raw = socket.create_connection((self.ip, self.port), self.timeout)
        self.sock = self.tls_context.wrap_socket(raw, server_hostname=self.host)


def _read_body(
    response: http.client.HTTPResponse,
    connection: http.client.HTTPConnection,
    deadline: float,
    url: str,
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EmaError("web_timeout", "Sursa online a depăşit timpul permis.", url)
        if connection.sock is not None:
            connection.sock.settimeout(remaining)
        chunk = response.read(min(65536, MAX_BODY + 1 - size))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_BODY:
            raise EmaError("web_size", "Sursa online este prea mare.", url)


def request(url: str, method: str, payload: bytes | None) -> tuple[int, str, bytes, str | None]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise EmaError("web_url", "Adresa sursei este invalidă.", url)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise EmaError("web_url", "Adresa sursei este invalidă.", url) from exc
    if port not in {80, 443}:
        raise EmaError("web_port", "Portul sursei nu este permis.", url)
    ip = _public_ip(parsed.hostname, port)
    connection = (
        _PinnedHTTPS(parsed.hostname, port, ip, 8)
        if parsed.scheme == "https"
        else _PinnedHTTP(parsed.hostname, port, ip, 8)
    )
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    try:
        deadline = time.monotonic() + 10
        connection.request(
            method,
            target,
            body=payload,
            headers={
                "Host": parsed.netloc,
                "User-Agent": "EmaResearch/1",
                "Content-Type": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise EmaError("web_encoding", "Codarea sursei nu este acceptată.", url)
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].lower()
        if response.status not in {301, 302, 303, 307, 308} and content_type not in _ALLOWED_TYPES:
            raise EmaError("web_type", "Tipul sursei nu este acceptat.", content_type)
        if response.length is not None and response.length > MAX_BODY:
            raise EmaError("web_size", "Sursa online este prea mare.", url)
        body = _read_body(response, connection, deadline, url)
        return response.status, content_type, body, response.getheader("Location")
    except (OSError, TimeoutError) as exc:
        raise EmaError(
            "web_unavailable", "Sursa online nu este disponibilă.", type(exc).__name__
        ) from exc
    finally:
        connection.close()


def fetch_bytes(
    url: str,
    *,
    method: str = "GET",
    payload: bytes | None = None,
    allowed_host: str | None = None,
    check_url: Callable[[str], None] | None = None,
    request: Callable[[str, str, bytes | None], tuple[int, str, bytes, str | None]] = request,
) -> tuple[str, str, bytes]:
    current = url
    for _ in range(6):
        if allowed_host is not None and (
            urlsplit(current).scheme != "https" or urlsplit(current).hostname != allowed_host
        ):
            raise EmaError("web_url", "Adresa sursei este invalidă.", "")
        if check_url is not None:
            check_url(current)
        status, content_type, body, redirect = request(current, method, payload)
        if status in {301, 302, 303, 307, 308}:
            if not redirect:
                raise EmaError("web_redirect", "Redirecţionarea nu are destinaţie.", "")
            current = urljoin(current, redirect)
            if status == 303:
                method, payload = "GET", None
            continue
        if status >= 400:
            raise EmaError("web_status", "Sursa online a răspuns cu eroare.", str(status))
        return current, content_type, body
    raise EmaError("web_redirect", "Prea multe redirecţionări.", "")

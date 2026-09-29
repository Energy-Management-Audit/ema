"""Reject private terms anywhere in commits about to be pushed."""

from __future__ import annotations

import os
import subprocess

from scripts.check_private_terms import load_guard, scan, scan_bytes


def _git(*args: str) -> bytes:
    return subprocess.check_output(("git", *args))


def outgoing_matches(
    from_ref: str, to_ref: str, terms: list[str], allowed: list[str] | None = None
) -> list[str]:
    """Scan every outgoing commit message, tracked path, and tracked blob."""
    revisions = _git("rev-list", "--reverse", f"{from_ref}..{to_ref}").decode().splitlines()
    matches: list[str] = []
    blob_cache: dict[str, bytes] = {}
    for revision in revisions:
        label = revision[:12]
        message = _git("show", "-s", "--format=%B", revision).decode("utf-8", errors="ignore")
        matches.extend(scan(f"{label}:commit-message", message, terms, allowed))
        tree = _git("ls-tree", "-r", "-z", revision)
        for entry in filter(None, tree.split(b"\0")):
            metadata, raw_path = entry.split(b"\t", 1)
            _, kind, object_id = metadata.decode().split(" ")
            if kind != "blob":
                continue
            path = raw_path.decode("utf-8", errors="replace")
            blob = blob_cache.get(object_id)
            if blob is None:
                blob = _git("cat-file", "blob", object_id)
                blob_cache[object_id] = blob
            matches.extend(scan_bytes(f"{label}:{path}", blob, terms, allowed))
    return matches


def main() -> int:
    try:
        guard = load_guard()
    except FileNotFoundError as error:
        print(error)
        return 1
    if guard is None:
        return 0
    from_ref = os.environ.get("PRE_COMMIT_FROM_REF")
    to_ref = os.environ.get("PRE_COMMIT_TO_REF")
    if not from_ref or not to_ref:
        print("private-term outgoing guard requires pre-push refs")
        return 1
    terms, allowed = guard
    matches = outgoing_matches(from_ref, to_ref, terms, allowed)
    for name in ("PRE_COMMIT_LOCAL_BRANCH", "PRE_COMMIT_REMOTE_BRANCH"):
        if branch := os.environ.get(name):
            matches.extend(scan(name, branch, terms, allowed))
    for match in matches:
        print(match)
    print(f"private-term outgoing guard: {len(matches)} matches across outgoing commits")
    return bool(matches)


if __name__ == "__main__":
    raise SystemExit(main())

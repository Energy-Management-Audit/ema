"""Audit section state and allowed §5.9 transitions, shared with undo."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, cast

from ema.core.errors import EmaError
from ema.core.review.models import Actor


class Status(StrEnum):
    MISSING = "missing"
    READY = "ready"
    DRAFTED = "drafted"
    DONE = "done"
    LATER = "later"
    NA = "n/a"
    NA_PROPOSED = "n/a proposed"


@dataclass(frozen=True)
class SectionState:
    section_id: str
    status: Status = Status.MISSING
    revision: int = 0
    stale: bool = False
    reason: str | None = None
    fingerprint: tuple[str, ...] = ()
    fact_revisions: dict[str, int | None] | None = None
    material_inputs: dict[str, tuple[bool, str] | None] | None = None
    changed_input: str | None = None
    na_applicable: bool | None = None
    applicability: bool | None = None
    applicability_reason: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "status": self.status.value,
            "revision": self.revision,
            "stale": self.stale,
            "reason": self.reason,
            "fingerprint": list(self.fingerprint),
            "fact_revisions": self.fact_revisions,
            "material_inputs": self.material_inputs,
            "changed_input": self.changed_input,
            "na_applicable": self.na_applicable,
            "applicability": self.applicability,
            "applicability_reason": self.applicability_reason,
        }

    @classmethod
    def parse(cls, data: str | dict[str, object]) -> SectionState:
        value = cast(dict[str, Any], json.loads(data) if isinstance(data, str) else data)
        return cls(
            section_id=str(value["section_id"]),
            status=Status(str(value["status"])),
            revision=int(value["revision"]),
            stale=bool(value["stale"]),
            reason=str(value["reason"]) if value.get("reason") is not None else None,
            fingerprint=tuple(str(item) for item in value.get("fingerprint", [])),
            fact_revisions=value.get("fact_revisions"),
            material_inputs={
                str(key): (bool(item[0]), str(item[1])) if item is not None else None
                for key, item in value["material_inputs"].items()
            }
            if value.get("material_inputs") is not None
            else None,
            changed_input=str(value["changed_input"])
            if value.get("changed_input") is not None
            else None,
            na_applicable=value.get("na_applicable"),
            applicability=value.get("applicability"),
            applicability_reason=value.get("applicability_reason"),
        )


def _forbidden(current: SectionState, to: Status, actor: Actor) -> EmaError:
    return EmaError(
        "transition_forbidden",
        "Tranziţia secţiunii este interzisă.",
        f"{current.status.value} -> {to.value} by {actor}",
    )


def transition(  # noqa: C901, PLR0913, PLR0911, PLR0912
    current: SectionState,
    to: Status,
    actor: Actor,
    reason: str | None = None,
    *,
    auto_later: bool = False,
    awaited_arrived: bool = False,
    computed: Status = Status.MISSING,
    input_changed: bool = False,
    compensation: bool = False,
) -> SectionState:
    """Apply only the §5.9 edges; callers supply material and fact outcomes."""
    source = current.status
    if to == Status.NA_PROPOSED and actor in ("ema", "agent") and reason:
        return replace(current, status=to, stale=False, reason=reason, changed_input=None)
    if to == Status.NA and actor == "user":
        return replace(current, status=to, stale=False, reason=reason, changed_input=None)
    if (
        to == Status.LATER
        and reason
        and (actor in ("user", "agent") or (actor == "ema" and auto_later))
    ):
        return replace(current, status=to, stale=False, reason=reason, changed_input=None)
    if source == Status.NA and actor == "user" and to == computed:
        return replace(
            current,
            status=to,
            reason=None,
            na_applicable=None,
            stale=current.stale if to == Status.DRAFTED else False,
        )
    if source == Status.NA_PROPOSED and actor == "user" and to == computed:
        return replace(
            current,
            status=to,
            reason=None,
            na_applicable=None,
            stale=current.stale if to == Status.DRAFTED else False,
        )
    if (
        source == Status.LATER
        and to == computed
        and (actor == "user" or (actor == "ema" and awaited_arrived))
    ):
        return replace(current, status=to, reason=None)
    if (
        source in (Status.MISSING, Status.READY, Status.NA_PROPOSED)
        and to in (Status.MISSING, Status.READY)
        and actor == "ema"
    ):
        return replace(current, status=to)
    if source == Status.READY and to == Status.DRAFTED and actor in ("ema", "agent"):
        return replace(current, status=to, stale=False)
    if (
        source == Status.DRAFTED
        and current.stale
        and to == Status.DRAFTED
        and actor in ("ema", "agent")
        and reason is None
        and not input_changed
    ):
        return replace(current, stale=False, changed_input=None)
    if source == Status.DRAFTED and not current.stale and to == Status.DONE and actor == "user":
        return replace(current, status=to)
    if source == Status.DONE and to == Status.DRAFTED and actor == "user" and compensation:
        return replace(
            current,
            status=to,
            stale=current.stale or input_changed,
            changed_input=reason if input_changed else current.changed_input,
        )
    if (
        source == Status.DRAFTED
        and to == Status.DRAFTED
        and actor == "ema"
        and current.stale
        and (reason is not None or input_changed)
    ):
        return current
    if (
        source == Status.DRAFTED
        and to == Status.DRAFTED
        and actor == "ema"
        and (reason in current.fingerprint or input_changed)
    ):
        return replace(current, stale=True, changed_input=reason)
    if (
        source == Status.DONE
        and to == Status.DRAFTED
        and actor == "ema"
        and (reason in current.fingerprint or input_changed)
    ):
        return replace(current, status=to, stale=True, changed_input=reason)
    raise _forbidden(current, to, actor)

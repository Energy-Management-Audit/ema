"""Errors safe to expose at an interface boundary."""

from dataclasses import dataclass


@dataclass(eq=False)
class EmaError(Exception):
    code: str
    user_message_ro: str
    detail: str

    def __str__(self) -> str:
        return self.detail

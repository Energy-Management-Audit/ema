"""Errors safe to expose at an interface boundary."""

from dataclasses import dataclass


@dataclass(eq=False)
class EmaError(Exception):
    code: str
    user_message_ro: str
    detail: str

    def __post_init__(self) -> None:
        # UI messages follow the handoff; document text has its own convention.
        self.user_message_ro = self.user_message_ro.translate(str.maketrans("șțȘȚ", "şţŞŢ"))

    def __str__(self) -> str:
        return self.detail

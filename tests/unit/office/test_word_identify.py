"""Word process scanning considers identity and launch provenance."""

from ema.core.office.word_child import identify_word


def test_identify_word_cases() -> None:
    class Process:
        def __init__(self, pid: int, name: str, command: list[str], created: float = 10) -> None:
            self.pid, self._name, self._command, self._created = pid, name, command, created

        def name(self) -> str:
            return self._name

        def create_time(self) -> float:
            return self._created

        def cmdline(self) -> list[str]:
            return self._command

    good = Process(2, "WINWORD.EXE", ["WINWORD.EXE", "/Automation"])
    assert identify_word([2], 9, processes=lambda: [good]) is None
    assert identify_word([], 11, processes=lambda: [good]) is None
    assert identify_word([], 9, processes=lambda: [good]) == 2
    assert identify_word([], 9, processes=lambda: [good, good]) is None
    assert identify_word([], 9, processes=lambda: [Process(3, "other", ["/Automation"])]) is None
    assert identify_word([], 9, processes=lambda: [Process(3, "WINWORD.EXE", [])]) is None

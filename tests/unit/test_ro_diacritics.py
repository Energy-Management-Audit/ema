"""Romanian user messages use one convention: ş ţ with cedilla, as the design files do (B10)."""

from __future__ import annotations

import ast
from pathlib import Path

COMMA_BELOW = {"Ș", "ș", "Ț", "ț"}
# S19 (#40) messages merged from dev as written; converting them is dev's call.
FROM_DEV = {
    "Redactarea pe documente reale așteaptă aprobarea.",
    "Secțiunea de redactare lipsește.",
    "Redactarea secțiunii a eșuat.",
    "Fișierul este în afara directoarelor de import.",
    "Fișierul nu există.",
    "Generarea PIEE a eșuat.",
    "Ciorna PIEE lipsește.",
}


def _messages(tree: ast.AST) -> list[ast.expr]:
    found: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name == "EmaError" and len(node.args) >= 2:
                found.append(node.args[1])
            if name == "progress" and len(node.args) >= 3:
                found.append(node.args[2])
            if name == "Issue":
                found.extend(kw.value for kw in node.keywords if kw.arg == "message")
    return found


def _strings(expr: ast.expr) -> list[str]:
    return [
        node.value
        for node in ast.walk(expr)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_user_messages_use_cedilla_diacritics() -> None:
    offenders: list[str] = []
    for path in sorted(Path("src/ema").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for expr in _messages(tree):
            for text in _strings(expr):
                if COMMA_BELOW & set(text) and text not in FROM_DEV:
                    offenders.append(f"{path}:{expr.lineno}: {text}")
    assert offenders == []


def test_problem_titles_and_route_literals_use_cedilla_diacritics() -> None:
    for name in ("errors.py", "routes.py"):
        tree = ast.parse(Path("src/ema/api", name).read_text(encoding="utf-8"))
        texts = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert not [text for text in texts if COMMA_BELOW & set(text)], name
    assert "Etapa a eşuat." in Path("src/ema/api/routes.py").read_text(encoding="utf-8")

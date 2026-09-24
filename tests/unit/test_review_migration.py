"""The S1b migration preserves explicit decision order."""

import sqlite3
from pathlib import Path

from ema.core.workspace import schema as workspace_schema


def test_schema_three_preserves_decision_order(tmp_path: Path) -> None:
    database = tmp_path / "old.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE outputs (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE decisions (id TEXT PRIMARY KEY, data TEXT)")
        db.execute("INSERT INTO outputs VALUES ('old-output')")
        db.execute("INSERT INTO decisions VALUES ('z', '{}')")
        db.execute("INSERT INTO decisions VALUES ('a', '{}')")
        db.execute("PRAGMA user_version = 3")
        db.commit()
        workspace_schema.migrate(db)
        assert db.execute("PRAGMA user_version").fetchone()[0] == workspace_schema.SCHEMA_VERSION
        assert db.execute("SELECT id FROM decisions ORDER BY seq").fetchall() == [("z",), ("a",)]
        db.execute("DELETE FROM decisions WHERE id='z'")
        db.commit()
        db.execute("VACUUM")
        assert db.execute("SELECT seq FROM decisions WHERE id='a'").fetchone()[0] == 2
        assert "kind" in {row[1] for row in db.execute("PRAGMA table_info(outputs)")}
        assert db.execute("SELECT seq FROM outputs WHERE id='old-output'").fetchone()[0] == 1
        assert "section_states" in {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

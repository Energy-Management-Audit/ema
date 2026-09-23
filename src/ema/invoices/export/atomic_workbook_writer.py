from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from openpyxl import Workbook

from ema.invoices.export.errors import (
    WorkbookCleanupError,
    WorkbookCommitError,
    WorkbookExportError,
    WorkbookVerificationError,
    WorkbookWriteError,
)

WorkbookVerifier = Callable[[Path], None]


def save_workbook_atomically(
    workbook: Workbook,
    destination: Path,
    verify: WorkbookVerifier,
) -> Path:
    """Write, verify, and atomically replace a workbook destination."""
    temporary_path = _create_temporary_sibling(destination)
    primary_error: WorkbookExportError | None = None
    try:
        _write_and_close(workbook, temporary_path)
        try:
            verify(temporary_path)
        except WorkbookVerificationError:
            raise
        except Exception as error:
            raise WorkbookVerificationError(
                "The generated workbook did not pass verification."
            ) from error
        try:
            os.replace(temporary_path, destination)
        except OSError as error:
            raise WorkbookCommitError(
                "The verified workbook could not replace the destination."
            ) from error
        return destination
    except WorkbookExportError as error:
        primary_error = error
        raise
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            if primary_error is not None:
                primary_error.add_note("The temporary workbook could not be removed.")
            else:
                raise WorkbookCleanupError(
                    "The temporary workbook could not be removed."
                ) from cleanup_error


def _create_temporary_sibling(destination: Path) -> Path:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.",
            suffix=".tmp.xlsx",
            dir=destination.parent,
        )
    except OSError as error:
        raise WorkbookWriteError("The temporary workbook could not be created.") from error

    temporary_path = Path(temporary_name)
    try:
        os.close(descriptor)
    except OSError as error:
        write_error = WorkbookWriteError("The temporary workbook could not be prepared.")
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            write_error.add_note("The temporary workbook could not be removed.")
        raise write_error from error
    return temporary_path


def _write_and_close(workbook: Workbook, temporary_path: Path) -> None:
    write_error: WorkbookWriteError | None = None
    try:
        workbook.save(temporary_path)
    except Exception as error:
        write_error = WorkbookWriteError("The workbook could not be written.")
        write_error.__cause__ = error
    finally:
        try:
            workbook.close()
        except Exception as close_error:
            if write_error is not None:
                write_error.add_note("The workbook could not be closed after the write failed.")
            else:
                raise WorkbookWriteError("The workbook could not be closed.") from close_error
    if write_error is not None:
        raise write_error

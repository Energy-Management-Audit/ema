"""Single-slot intake adapter used only by office conversion tests."""

from ema.core import intake


def intake_stage(ctx, slot, on_result=None):
    result = intake.intake_file(ctx, slot)
    intake._record_result(ctx, result)
    if on_result is not None:
        on_result(result)
    return intake._summary([result])

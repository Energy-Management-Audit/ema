"""Missing chart blocks keep their monthly/table/annual placement and identity."""

from ema.audit.chapter_four_chart_placement import place_chart_groups
from ema.audit.chapter_four_charts import ChartGroup
from ema.core.office.blocks import Caption, Missing, Paragraph, Table


def test_missing_chart_groups_survive_beside_tables_and_totals():
    heading = Paragraph("heading:ch4.gaz", ["Gaz"])
    label = Paragraph("body", ["Consumul de gaze naturale"])
    caption = Caption("caption", "tab", "gas", ["Table"])
    table = Table("months_first", [])
    total = Paragraph("body", ["Total anual 2025: "])
    monthly = Missing("body", "Monthly 2025: missing")
    annual = Missing("body", "Annual: missing")
    groups = {"ch4.gaz": [ChartGroup(label.segments[0], [monthly], [annual])]}
    assert place_chart_groups([heading, label, caption, table, total], groups) == [
        heading,
        label,
        monthly,
        caption,
        table,
        total,
        annual,
    ]
    assert place_chart_groups([heading], groups) == [heading, monthly, annual]

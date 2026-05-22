"""Tests for the comparative-statement ground-truth selection in scripts/build_validation.py.

For tabular jurisdictions (source="comparative"), the builder turns the report's comparative
statement into ground-truth account rows. The selection rules are load-bearing — they decide
what the recall test treats as an appropriation account — so they are tested directly:
amounts convert from thousands to dollars, and non-leaf rows (rollup totals, advance-
appropriation components, and negative reduction/offset lines) are excluded.
"""

from types import SimpleNamespace

from scripts.build_validation import _ground_truth

# A canonical comparative statement: a TITLE-section agency, two leaf accounts, a rollup
# total, and a negative offset line (offsetting collections). Columns are
# 2024 / Budget estimate / Committee recommendation / Δ2024 / Δbudget, in thousands.
_STATEMENT = """\
  COMPARATIVE STATEMENT OF NEW BUDGET (OBLIGATIONAL) AUTHORITY FOR FISCAL YEAR 2024
                          [In thousands of dollars]
            Item                          appropriation  estimate    recommendation   2024  estimate

                            TITLE I

                      MILITARY PERSONNEL

Military Personnel, Army.............  50,041,206  50,679,897  50,702,367  +661,161  +22,470
Military Personnel, Navy.............  36,707,388  38,724,875  38,400,554  +1,693,166  -324,321
Offsetting collections...............  -12,000  -12,000  -12,000  ....  ....
    Total, title I, Military Personnel.  86,748,594  89,404,772  89,102,921  +2,354,327  -301,851
"""


def _comparative(text):
    return _ground_truth(SimpleNamespace(source="comparative"), text)


def test_comparative_ground_truth_converts_thousands_to_dollars():
    rows = {item: amount for _title, _bureau, item, amount in _comparative(_STATEMENT)}
    assert rows["Military Personnel, Army"] == 50_702_367_000
    assert rows["Military Personnel, Navy"] == 38_400_554_000


def test_comparative_ground_truth_carries_agency_title():
    titles = {title for title, _bureau, _item, _amount in _comparative(_STATEMENT)}
    assert titles == {"MILITARY PERSONNEL"}


def test_comparative_ground_truth_drops_totals_and_negative_offsets():
    items = {item for _title, _bureau, item, _amount in _comparative(_STATEMENT)}
    assert "Total, title I, Military Personnel" not in items  # rollup total
    assert "Offsetting collections" not in items  # negative reduction line
    assert items == {"Military Personnel, Army", "Military Personnel, Navy"}

"""Unit tests for the committee-report reader (parsers/committee_report.py).

The reader extracts account-level ground truth from a Senate appropriations
committee report's HTML `<pre>` dump (GPO's authoritative ASCII layout, with
preserved column alignment). These tests use inline snippets mirroring the real
layout of Senate Report 118-198 so they run in CI without a committed fixture.
"""

from parsers.committee_report import extract_pre_text, parse_summary_blocks

# A real-shape 3-line summary block: ALL-CAPS heading, blank line, then the
# Appropriations / Budget estimate / Committee recommendation rows in actual dollars.
BASIC_BLOCK = """\
                     INDUSTRIAL TECHNOLOGY SERVICES

Appropriations, 2024....................................    $212,000,000
Budget estimate, 2025...................................     212,000,000
Committee recommendation................................     225,000,000

The Committee provides $225,000,000 for Industrial Technology Services.
"""


def test_extract_pre_text_pulls_pre_block_and_unescapes():
    html = "<html><body><pre>\nA &amp; B\n$1,000\n</pre></body></html>"
    assert extract_pre_text(html) == "\nA & B\n$1,000\n"


def test_parse_summary_blocks_basic():
    blocks = parse_summary_blocks(BASIC_BLOCK)
    assert len(blocks) == 1
    assert blocks[0].heading == "INDUSTRIAL TECHNOLOGY SERVICES"
    assert blocks[0].committee_recommendation == 225_000_000


# A parenthetical qualifier line sits between the heading and the summary rows; the
# reader must walk past it to the real ALL-CAPS heading.
PARENTHETICAL_BLOCK = """\
                     PERIODIC CENSUSES AND PROGRAMS

                     (INCLUDING TRANSFER OF FUNDS)

Appropriations, 2024....................................  $1,054,000,000
Budget estimate, 2025...................................   1,210,344,000
Committee recommendation................................   1,210,344,000
"""

# A bureau-level rollup sits under a mixed-case header (not an account heading); the
# reader should skip it. Its amount is the sum of the leaf accounts beneath it.
BUREAU_ROLLUP_BLOCK = """\
       National Telecommunications and Information Administration

Appropriations, 2024....................................     $59,000,000
Budget estimate, 2025...................................      67,000,000
Committee recommendation................................      61,650,000
"""


def test_parse_summary_blocks_skips_parenthetical_qualifier():
    blocks = parse_summary_blocks(PARENTHETICAL_BLOCK)
    assert len(blocks) == 1
    assert blocks[0].heading == "PERIODIC CENSUSES AND PROGRAMS"
    assert blocks[0].committee_recommendation == 1_210_344_000


def test_parse_summary_blocks_skips_mixed_case_bureau_header():
    assert parse_summary_blocks(BUREAU_ROLLUP_BLOCK) == []


# The "(INCLUDING TRANSFER OF FUNDS)" qualifier sometimes renders WITHOUT parentheses,
# so it is ALL-CAPS and would be mistaken for the heading. The reader must skip it and
# reach the real account heading above.
UNPARENTHESIZED_QUALIFIER_BLOCK = """\
             COMMUNITY ORIENTED POLICING SERVICES PROGRAMS

                      INCLUDING TRANSFER OF FUNDS

Appropriations, 2024....................................    $664,516,000
Budget estimate, 2025...................................     534,000,000
Committee recommendation................................     548,123,000
"""


def test_parse_summary_blocks_skips_unparenthesized_qualifier():
    blocks = parse_summary_blocks(UNPARENTHESIZED_QUALIFIER_BLOCK)
    assert len(blocks) == 1
    assert blocks[0].heading == "COMMUNITY ORIENTED POLICING SERVICES PROGRAMS"
    assert blocks[0].committee_recommendation == 548_123_000

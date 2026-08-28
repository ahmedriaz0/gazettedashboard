r"""
BISE Faisalabad gazette format.

Sample raw line (via `pdftotext -layout`):
    407995           MEHAK BATOOL                         776
    408001           AKASHA NAZ                           MTHI BIOI   <- failed, subject codes not marks

Fields available: roll_number, name, marks. Failed students show subject
codes in the "Notification" column instead of a number, which our
"\d{3,4}$" requirement naturally excludes (so we only capture passes).

Note on the watermark: this file (and the result.pk copy) has a
"result.pk" watermark stamped diagonally across the page. This shows up
as stray junk lines (single letters like "R", "k", or "t.p") interspersed
between real rows when extracted with `pdftotext -layout`. It does NOT
corrupt the actual data rows — poppler keeps each row's roll/name/marks
intact on one line — so no special handling is needed here, the regex
below just ignores the junk lines since they don't match the pattern.
"""
import re

BOARD_CONFIG = {
    "match_names": ["faisalabad", "fsd"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})\s+(?P<name>[A-Z][A-Z\s\.]*?)\s+(?P<marks>\d{3,4})\s*$",
        re.MULTILINE,
    ),
    "fields": ["roll_number", "name", "marks"],
}

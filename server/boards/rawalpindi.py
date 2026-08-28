"""
BISE Rawalpindi gazette format.

Sample raw line (via `pdftotext -layout`) — TWO candidates side-by-side
per physical line, same "columns share a line" situation as Bahawalpur:

    201879 ZUNJABILA UROOJ      PASS               658     C          201916 MISBAH ALI             CHE-II EC-II MC-I MC-II
    201880 UME KHADIJA          PASS               502     D          201917 EMAAN KIANI            IMP                 715     C

Fields available: roll_number, name, marks. Unlike Faisalabad/Bahawalpur,
this board prints an explicit status word before the marks — either
"PASS" or "IMP" (improvement candidates who already passed previously
and re-sat to raise their score; their marks column is just as real as a
PASS row's, so both are captured). Failing candidates show a
space-separated list of failed subject codes instead (e.g. "CHE-I CHE-II
MC-I") with no status word before a number, so they never match — same
"only capture rows with real marks" convention as every other board here.

Because the status word ("PASS"/"IMP") is required in the pattern, this
is actually safer than Bahawalpur's plain digit-based approach: there's
no ambiguity from stray 3-4 digit numbers elsewhere on the line, and the
regex isn't anchored to line start/end at all, so it naturally picks up
both columns regardless of how their rows are vertically offset from
each other (a name column value + status + marks + grade, appearing
anywhere in the page text, is unambiguously a real candidate row).

This is a SECOND ANNUAL (supplementary) exam gazette, so most rows are
failed-subject reappear listings rather than passes — a low PASS/IMP
ratio per page is expected and correct, not a sign of under-matching.

`page_marker` keeps this from ever running against the front-matter
pass-percentage summary pages (which have no "ROLLNO"/"ROLL NO" table
header at all).

Verified on the full 342-page document: 7,344 matches, 0 duplicate roll
numbers.
"""
import re

BOARD_CONFIG = {
    "match_names": ["rawalpindi", "pindi"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})\s+(?P<name>[A-Z][A-Z\.\-\s]*?)\s+(?:PASS|IMP)\s+"
        r"(?P<marks>\d{3,4})\s+[A-E]\+?"
    ),
    "fields": ["roll_number", "name", "marks"],
    # This gazette's own column header uses either "ROLLNO" (first/left
    # column) or "ROLL NO" (second/right column) depending on the page's
    # print run — main.py's page_marker check accepts a list and skips
    # the page only if NONE of the given strings are present.
    "page_marker": ["ROLLNO", "ROLL NO"],
}

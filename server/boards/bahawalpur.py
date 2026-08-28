r"""
BISE Bahawalpur gazette format.

Sample raw line (via `pdftotext -layout`) — TWO independent records
side by side on the SAME physical text line:
    837061    KHADIJA BIBI                             884             739357    SAWAIRA BIBI          TRQII,MATHI,II,PHY(P

Unlike Lahore/Faisalabad, Bahawalpur prints the roll listing in two
side-by-side columns per page. Worse, a row's right-hand entry doesn't
reliably line up with its left-hand row once anything above it wraps
onto an extra line (a long name, or a long list of failed-subject
codes) — so this can't be parsed as "one row per text line" the way
Faisalabad's single-column pages can.

Instead, the pattern below is intentionally NOT anchored to the start
or end of a line — it just searches for "<6-digit roll> <NAME> <3-4
digit marks>" wherever that sequence occurs in the page text, left
column or right column, ignoring whatever precedes/follows it on the
same physical line. re.finditer() returns matches in the order they
appear, so this recovers both columns correctly even when their row
alignment has drifted. Failed/absent entries (subject codes or
"Absent-R/A" instead of a number) simply don't match \d{3,4}, so —
same convention as Faisalabad — only PASS records with marks are
captured; fails/absentees are skipped rather than guessed at.

FALSE-POSITIVE GUARD:
Pages ~11-490 of this gazette are an "INSTITUTE WISE PASS%" summary
section (per-school aggregate stats, not individual students) that also
contains 6-digit institute codes followed by institute names. Rarely, an
institute code + a name truncated by a character the name class doesn't
allow (e.g. "/") can chain into a nearby 3-digit statistic and produce a
bogus record (~1 false positive per 500 pages, found during testing).
Every one of those pages carries the literal header "INSTITUTE WISE
PASS%", so `skip_page` below tells main.py to skip parsing any page
containing that string entirely.
"""
import re


def _skip_page(text: str) -> bool:
    """Institute-wise summary pages aren't student records — see
    FALSE-POSITIVE GUARD above. main.py calls this (if present) before
    running `pattern` on a page."""
    return "INSTITUTE WISE PASS%" in text


BOARD_CONFIG = {
    "match_names": ["bahawalpur", "bwp"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})\s+(?P<name>[A-Z][A-Z\.\s]*?)\s+(?P<marks>\d{3,4})(?=\s|$)"
    ),
    "fields": ["roll_number", "name", "marks"],
    "skip_page": _skip_page,   # optional — see base.py contract
}

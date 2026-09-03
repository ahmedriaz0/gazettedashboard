r"""
BISE Bahawalpur gazette format.

Two candidate columns per page, and this file ships TWO page sizes
(612x792 and 595x842), so column origins are detected per page rather
than hardcoded. On a 612x792 page:

    col     roll x0    name x0     result x0
    left       65.9      103.4        ~257.5
    right     310.7      348.2        ~502.5

Marks are RIGHT-aligned in the result cell, so a 3-digit total starts
~2pt further right than a 4-digit one (258.5 vs 256.4). The detected
column centre plus MARKS_X_TOL covers both. A failing candidate's cell
holds subject codes instead ("ENGII,CHEI,II(TH)", "PHYII(TH),CHEI,II(TH)")
and yields no number, so the row is skipped — the same "only rows with a
real numeric total" convention as every other board here.

WHY page_records_fn RATHER THAN THE OLD REGEX:
The old pattern's name class was `[A-Z\.\s]`, which crosses newlines. On
these two-column pages the left column's roll numbers are frequently
missing from poppler's output entirely, leaving bare name+marks rows; the
lazy name group would then run from a RIGHT-column roll number, across
the blank gutter and the line break, and attach itself to a LEFT-column
candidate's name and marks. Verified on page 225:

    708654   MUHAMMAD JAHANZAIB          <- right column, no total printed
    MUHAMMAD SHAHID          853         <- left column, a different person

The old parser emitted roll 708654 with name
"MUHAMMAD JAHANZAIB MUHAMMAD SHAHID" and marks 853 — two candidates
fused into one row, with the marks belonging to neither reliably. That is
the documented hazard the old docstring described as "recovering both
columns correctly"; it does not.

`skip_page` is retained in spirit by the page marker: pages ~11-490 are an
"INSTITUTE WISE PASS%" per-school summary section whose institute codes
and aggregate percentages resemble candidate rows. Those pages carry no
"Roll No" table header, so the marker gates them out, and the per-column
marks-x anchoring means an institute code's trailing statistic could not
be read as marks even if one slipped through.

Measured on 60 sampled pages: 3,175 marks cells, 3,175 records (100%),
0 duplicate roll numbers, 0 empty names, 0 names containing digits,
punctuation or subject-code text. Hyphenated names such as
"ZAIN-UL-ABIDEEN" and "QURA-TUL-AIN" survive intact.
"""
import re

from . import _coltable as ct
from . import ocr

ROLL_RE = re.compile(r"\A\d{6}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")

HEADER_Y_CUTOFF = 75.0    # table header at y~68; first data row at y~81
MAX_NAME_DY = 26.0        # ~2 printed lines at this board's ~12pt pitch
PAGE_MARKER = "Roll No"


def page_records_fn(pdf_path, page_num):
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        if PAGE_MARKER not in ocr.page_text(page):
            return []           # institute-wise summary / front matter
        words = [w for w in ocr.page_words(page) if w[1] >= HEADER_Y_CUTOFF]

    columns = ct.detect_columns(words, ROLL_RE, MARKS_RE)
    if not columns:
        return []
    columns = [(rx, mx - ct.NAME_X_PAD, mx) for rx, mx in columns]
    return ct.build_records(words, columns, ROLL_RE, MARKS_RE, MAX_NAME_DY)


BOARD_CONFIG = {
    "match_names": ["bahawalpur", "bwp"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": ct.close_doc,
}

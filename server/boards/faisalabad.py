r"""
BISE Faisalabad gazette format.

Single candidate column, page box 612x792 (the only board here with one
page size and one column). Geometry on a student page:

    roll x0 = 43.2    name x0 = 122.4 ..      result x0 = 302.3

Row pitch is ~12.2pt. The result cell holds either a bare 3-4 digit total
or, for a failing candidate, a list of subject codes
("URDII MTH PHYII(Th) BIOII(Th)").

WHY page_records_fn RATHER THAN THE OLD REGEX:
The previous pattern anchored marks to end-of-line
(`(?P<marks>\d{3,4})\s*$` with re.MULTILINE) over `pdftotext -layout`
text. That inherits poppler's row grid, which slides a taller row's
result cell onto the following printed line and binds marks to the wrong
candidate — the failure documented at length in boards/lahore.py. Reading
word coordinates avoids it, and shares boards/_coltable.py with the other
column-table boards.

MOST PAGES OF THIS FILE ARE NOT STUDENT PAGES. Large runs are "DISTRICT
WISE SCHOOL DATA" summaries whose per-school statistics contain 6-digit
school codes and 3-digit counts in roughly the right shape to be mistaken
for candidate rows. Only the result-gazette pages carry the literal
"Notification" column header, so that string gates the whole page — this
is why the old capture rate looked poor when measured against every
6-digit token in the file.

Names wrap onto a second line only very rarely here (1 row in 2,641
sampled candidates: "MUHAMMAD ABDULLAH NADEEM" + "CHATTHA"), but the
shared reader handles it for free.

Measured on 60 sampled pages: 2,056 result cells, 2,056 records (100%),
0 duplicate roll numbers, 0 empty names, 0 names containing digits,
punctuation or header/subject-code words. Hyphenated names such as
"ABAID-UR-REHMAN" and "SYED MUHAMMAD ALI ZAIN-UL-ABIDEEN" survive intact.
"""
import re

from . import _coltable as ct

ROLL_RE = re.compile(r"\A\d{6}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")

HEADER_Y_CUTOFF = 100.0   # column header sits at y~106, first row at y~121
MAX_NAME_DY = 27.0        # ~2 printed lines at a 12.2pt pitch
PAGE_MARKER = "Notification"


def page_records_fn(pdf_path, page_num):
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        if PAGE_MARKER not in page.get_text():
            return []           # summary / front-matter page, not a gazette page
        words = [
            (w[0], w[1], w[4]) for w in page.get_text("words")
            if w[1] >= HEADER_Y_CUTOFF
        ]

    columns = ct.detect_columns(words, ROLL_RE, MARKS_RE)
    if not columns:
        return []
    columns = [(rx, mx - ct.NAME_X_PAD, mx) for rx, mx in columns]
    return ct.build_records(words, columns, ROLL_RE, MARKS_RE, MAX_NAME_DY)


BOARD_CONFIG = {
    "match_names": ["faisalabad", "fsd"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": ct.close_doc,
}

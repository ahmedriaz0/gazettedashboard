r"""
BISE Rawalpindi gazette format (SECOND ANNUAL / supplementary).

Two candidate columns per page, and this file ships TWO page sizes
(1008x612 and 1080x792), so the column origins are detected per page
rather than hardcoded. On a 1080x792 page:

    col   roll x0    name x0     STAT x0    MARKS x0    GRD x0
    left      4.5       63.0       261.0       374.4      423.3
    right   490.5      549.0       747.0       860.4      909.3

The STAT cell holds "PASS", "IMP", "FAIL", "NOT-IMP", or a list of failed
subject codes; MARKS holds the total only when the candidate has one.

WHY page_records_fn RATHER THAN THE OLD REGEX — this board was the worst
name corruption of the set. The old pattern's name class was
`[A-Z\.\-\s]`, and this gazette's subject codes are all-caps with a
hyphen ("CHE-I", "MC-II", "PHY-II"), as are its status words. Every one of
those satisfies that class, so the lazy name group ran straight through
the STAT column and stored them as part of the candidate's name. Real
rows previously written to the database:

    200068  name = "HIFZA FAIL"                          marks = 648
    200088  name = "UMAMA CHE-I CHE-II MC-I MC-II"       marks = 692
    201578  name = "GMC-II GS-I GS-II"                   marks = 677

The last one has no candidate name in it at all. Measured over the full
342-page document, 660 of the old parser's 4,474 captures (14.8%) carried
subject codes or status words inside the name.

The fix is structural: the name band has to stop at the STAT column, not
at the marks column. `_coltable.detect_x()` locates STAT from its own
PASS/FAIL/IMP keywords, so the boundary adapts to both page sizes.

The old docstring claimed "7,344 matches, 0 duplicate roll numbers" on the
full document; the pattern as committed actually yielded 4,474. Zero
duplicates was never evidence that the rows were right.

`page_marker` still gates front-matter pass-percentage pages, which have
no "ROLLNO"/"ROLL NO" table header. Note the header spelling differs
between the left column ("ROLLNO") and the right ("ROLL NO") depending on
the print run, so both are accepted.

Measured on 60 sampled pages: 1,287 marks cells, 1,287 records (100%),
0 duplicate roll numbers, 0 empty names, 0 names containing subject codes
or status words. Names now run to 6 words
("SYED MUHAMMAD FAHEEM UL HASSAN SHAH").
"""
import re

from . import _coltable as ct
from . import ocr

ROLL_RE = re.compile(r"\A\d{6}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")
STAT_WORDS = ("PASS", "FAIL", "IMP", "NOT-IMP")

HEADER_Y_CUTOFF = 55.0    # column header sits at y~43, first row at y~66
MAX_NAME_DY = 20.0        # ~1 continuation line at this board's ~18pt pitch
PAGE_MARKERS = ("ROLLNO", "ROLL NO")


def page_records_fn(pdf_path, page_num):
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        text = ocr.page_text(page)
        if not any(m in text for m in PAGE_MARKERS):
            return []
        words = [w for w in ocr.page_words(page) if w[1] >= HEADER_Y_CUTOFF]

    detected = ct.detect_columns(words, ROLL_RE, MARKS_RE)
    if not detected:
        return []

    columns = []
    for i, (roll_x, marks_x) in enumerate(detected):
        right = detected[i + 1][0] - ct.NAME_X_PAD if i + 1 < len(detected) else float("inf")
        # The name band must end at STAT, not at MARKS: everything between
        # them is failed-subject-code text that reads as a valid name.
        stat_x = ct.detect_x(
            [w for w in words if roll_x < w[0] < right],
            lambda t: t in STAT_WORDS,
        )
        columns.append((roll_x, (stat_x or marks_x) - ct.NAME_X_PAD, marks_x))

    return ct.build_records(words, columns, ROLL_RE, MARKS_RE, MAX_NAME_DY)


BOARD_CONFIG = {
    "match_names": ["rawalpindi", "pindi"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": ct.close_doc,
}

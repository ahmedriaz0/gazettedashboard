r"""
BISE D.G. Khan (Dera Ghazi Khan) gazette format.

Two candidate columns per page, and this file ships TWO page sizes
(842x595 landscape and 595x842 portrait), so column origins are detected
per page rather than hardcoded. On a landscape page:

    col     roll x0   name x0     9TH x0   10TH x0   RESULT x0
    left       77.0     114.7      270.0     326.3       375.8
    right     422.5     460.2      615.5     671.8       723.2

WHY page_records_fn RATHER THAN THE OLD REGEX:

1. THE RESULT CELL IS NOT ON THE ROLL'S OWN TEXT LINE in `pdftotext
   -layout` output — it is printed ~1.5pt below the roll's baseline, and
   poppler resolves that onto the NEXT line. The -layout text for page
   400 reads

       207806  AQSA MAZHAR      628
       207807  AREEBA FAREED
       207808  AYESHA SULTAN    931 BIO-TH

   so a regex gives 931 to 207808. The word coordinates put 931 at
   y=134.3 against 207807's y=132.8 (dy 1.5) versus 207808's y=147.1
   (dy 12.8): 931 is AREEBA FAREED's. The old parser was mis-assigning
   marks wholesale, not merely dropping rows.

2. An institute banner ("GOVT. GIRLS HIGHER SECONDARY SCHOOL NAWAN KOT",
   "(LAYYAH)") is interleaved between candidates whenever the roster
   changes school, on both columns independently. Those banners start at
   the page margin, left of the name band, which is exactly the test
   _coltable uses to reject a line as a name continuation.

3. A `www.taleem360.com` watermark is stamped diagonally across each page
   and lands mid-row often enough that the old regex's name class broke
   on the stray lowercase characters. Coordinates make it a non-issue:
   it is one mixed-case token, so it fails both the name-token and the
   marks test.

The old module's own docstring conceded "~49.8k clean single-line rows out
of ~91k total candidates — treat this module as best-effort, not
complete", and only allowed a single literal space inside a name so the
lazy match could not bridge a column gap. Neither compromise is needed
once rows are rebuilt from coordinates.

The name band stops at the 9TH column rather than at RESULT, located from
the "9TH"/"10TH" header words so it adapts across both page sizes.

Measured on 60 sampled pages: 1,413 result cells, 1,413 records (100%),
0 duplicate roll numbers, 0 empty names, 0 names containing digits,
punctuation or institute/header words. Names run to 6 words
("MUHAMMAD RABI UR REHMAN KHAN ANJUM").
"""
import re

from . import _coltable as ct
from . import ocr

ROLL_RE = re.compile(r"\A\d{6}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")
CLASS_HEADERS = ("9TH", "10TH")

HEADER_Y_CUTOFF = 85.0    # table header at y~76; first data row at y~118
MAX_NAME_DY = 26.0        # ~2 printed lines at this board's ~14pt pitch
PAGE_MARKER = "Roll No."


def page_records_fn(pdf_path, page_num):
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        if PAGE_MARKER not in ocr.page_text(page):
            return []
        words = [w for w in ocr.page_words(page) if w[1] >= HEADER_Y_CUTOFF]

    detected = ct.detect_columns(words, ROLL_RE, MARKS_RE)
    if not detected:
        return []

    columns = []
    for i, (roll_x, marks_x) in enumerate(detected):
        right = detected[i + 1][0] - ct.NAME_X_PAD if i + 1 < len(detected) else float("inf")
        class_x = ct.detect_x(
            [w for w in words if roll_x < w[0] < right],
            lambda t: t in CLASS_HEADERS,
            min_count=1,
        )
        columns.append((roll_x, (class_x or marks_x) - ct.NAME_X_PAD, marks_x))

    return ct.build_records(words, columns, ROLL_RE, MARKS_RE, MAX_NAME_DY)


BOARD_CONFIG = {
    "match_names": ["dg khan", "dera ghazi khan", "dgkhan", "d.g khan", "d.g. khan"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": ct.close_doc,
}

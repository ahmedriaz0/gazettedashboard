r"""
BISE Lahore gazette format.

WHY THIS BOARD NEEDS page_records_fn (not the default pattern path):

1. NAMES WRAP ONTO A SECOND LINE. This is the whole reason this module
   was rewritten. A long name is printed across two (occasionally three)
   printed lines, with the continuation sitting in the NAME column and
   carrying no roll number of its own:

       257847 MUHAMMAD MOAZZAM   23/10/10 PASS 731 B
              IMRAN

   The candidate's real name is "MUHAMMAD MOAZZAM IMRAN". The previous
   regex captured only "MUHAMMAD MOAZZAM" — the first line — and dropped
   the rest, which is exactly the reported bug. Roughly 1.5 rows per page
   wrap this way (61 found across 40 sampled pages, so on the order of
   ~4,700 across the full 3,128-page document).

2. `pdftotext -layout` MISALIGNS THE ROWS. Because a wrapped row is
   taller than a normal one, poppler's single global text grid slides a
   row's DATE/RESULT cell onto the *following* printed line. In the raw
   -layout text, roll 257873's line looks like it has no result at all
   and the next line reads "AMIN  28/02/08 PASS 572 D" — so a regex
   binds 572 to 257873. The word coordinates show 572 actually belongs
   to 257872, and 257873's real total is 792. Any regex over -layout
   text therefore mis-assigns marks to the wrong candidate, silently and
   plausibly. This is the same "poppler can't represent this table" case
   as sahiwal.py and gujranwala.py, so we take the same way out: read
   word-level coordinates via PyMuPDF and rebuild the rows ourselves.

PAGE GEOMETRY (verified identical on pages 301, 901, 1795, 2401 and 3101
of the 3,128-page file — page box 841x595, landscape, three side-by-side
candidate columns):

    column        roll x0     name x0..      DOB x0    result x0
    left            60.8      90.4 .. 190     200.8       232.0
    middle         305.6     335.2 .. 435     445.6       476.8
    right          550.4     579.6 .. 680     690.4       717.0

Every roll number on a page is matched by exactly one DOB word, on every
page sampled — that 1:1 relationship is what makes the column bands safe
to key off.

ROW-BUILDING ALGORITHM (per page, per column):
  1. A word that fully matches \d{6} at the column's roll x-band anchors
     a new candidate row.
  2. That row's NAME is every word in the column's name x-band whose y
     runs from the row's own printed line down to just above the NEXT
     anchor's line (capped at MAX_NAME_DY). This span is precisely what
     picks up wrapped continuation lines, and it cannot reach into the
     next candidate because it stops short of that candidate's own y.
     Words are joined in (y, x) order, so a two-line name reads in the
     printed order.
  3. The RESULT cell is read only from the row's OWN line (|dy| <= ROW_DY)
     in the column's result x-band. Failing rows print subject codes over
     several lines there ("MATH. II - CHEM. I - SECOND ANNUAL 2026")
     instead of a total; those lines stay out of the name band because
     they sit to the right of the DOB column.
  4. Words above HEADER_Y_CUTOFF are dropped — the page title and the
     repeated "ROLL NO / NAME / DATE OF BIRTH / RESULT STATUS" headers
     sit in the same x-bands as real data.

ONLY PASSING STUDENTS ARE KEPT, matching every other board here: the row
is emitted only if its result cell contains "PASS <3-4 digits>". Failed
and absent candidates print subject codes with no total and are skipped
rather than inserted with marks=None.

MEASURED RESULTS.

Full 3,128-page document, this parser (15.6s):
    165,394 records, 0 duplicate roll numbers, 0 empty names,
    0 names containing digits / punctuation / header or subject-code
    words. 25,022 of them are 3 words or longer (max 7).

Against the old regex over `pdftotext -layout`, on 149 pages sampled
evenly across the document:
    old parser                 : 2,696 records
    this parser                : 7,926 records  (+5,230)
    names the old one had TRUNCATED at the line break : 124
      e.g. "SYED MUHAMMAD MEHDI" -> "SYED MUHAMMAD MEHDI RAZA ZAIDI"
    rows where the old one reported the WRONG MARKS   : 1,632
      e.g. roll 262146 "AHMED RANA" 800 -> 685; the 800 belonged to a
      neighbouring row. This is failure (2) above, and it affected a
      majority of the old parser's own output — the truncated names were
      the visible symptom of a table it was misreading generally.

"""
import re
import threading

import pymupdf as fitz  # PyMuPDF's import is now `pymupdf`; `fitz` still works but is deprecated

ROLL_RE = re.compile(r"\A\d{6}\Z")
PASS_RE = re.compile(r"\bPASS\s+(\d{3,4})\b")

# (roll x0, DOB x0) for each of the three side-by-side columns.
COLUMNS = ((60.8, 200.8), (305.6, 445.6), (550.4, 690.4))
ROLL_X_TOL = 3.0        # roll numbers land on their x0 to within a point
NAME_X_PAD = 6.0        # keeps the DOB word itself out of the name band
ROW_DY = 3.0            # same-printed-line tolerance
MAX_NAME_DY = 30.0      # a name may wrap ~3 printed lines (pitch is ~9.4pt)
COLUMN_WIDTH = 120.0    # how far right of the DOB column a result cell runs
HEADER_Y_CUTOFF = 40.0  # first real data row starts at y=44.1

# One fitz.Document per pdf_path, opened once and shared by all
# ThreadPoolExecutor workers rather than reopened per page — same pattern
# gujranwala.py and sahiwal.py use. MuPDF is not safe for concurrent
# access to one Document, so a per-path lock serializes page reads.
_DOC_CACHE = {}
_LOCKS = {}
_REGISTRY_LOCK = threading.Lock()


def _get_doc_and_lock(pdf_path):
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.get(pdf_path)
        if doc is None:
            doc = fitz.open(pdf_path)
            _DOC_CACHE[pdf_path] = doc
            _LOCKS[pdf_path] = threading.Lock()
        return doc, _LOCKS[pdf_path]


def close_doc(pdf_path):
    """cleanup_fn — main.py calls this in its `finally` block, before it
    tries to os.remove() the temp upload. Without it Windows raises
    PermissionError on a file this module still holds open."""
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.pop(pdf_path, None)
        _LOCKS.pop(pdf_path, None)
    if doc is not None:
        doc.close()


def _extract_column(words, roll_x, dob_x):
    name_min_x = roll_x + ROLL_X_TOL
    name_max_x = dob_x - NAME_X_PAD
    result_min_x = dob_x + NAME_X_PAD

    anchors = sorted(
        (y, int(text)) for x, y, text in words
        if abs(x - roll_x) <= ROLL_X_TOL and ROLL_RE.fullmatch(text)
    )
    if not anchors:
        return []

    # Every printed line that puts SOMETHING in the roll column. A genuine
    # wrapped name line puts nothing there, so this cheaply distinguishes a
    # continuation from any other row (or page footer) that happens to fall
    # inside the wrap window.
    occupied_ys = [y for x, y, _ in words if abs(x - roll_x) <= ROLL_X_TOL]

    def _is_continuation_line(y):
        return not any(abs(y - oy) <= ROW_DY for oy in occupied_ys)

    records = []
    for i, (roll_y, roll_number) in enumerate(anchors):
        # The name owns everything from its own line down to just above
        # the next candidate's line — that span is what carries wrapped
        # continuation lines such as "IMRAN" under "MUHAMMAD MOAZZAM".
        next_y = anchors[i + 1][0] if i + 1 < len(anchors) else roll_y + MAX_NAME_DY
        y_hi = min(next_y - ROW_DY, roll_y + MAX_NAME_DY)

        parts = [
            (round(y, 1), x, text) for x, y, text in words
            if name_min_x <= x < name_max_x and (roll_y - ROW_DY) <= y < y_hi
            and (abs(y - roll_y) <= ROW_DY or _is_continuation_line(y))
        ]
        parts.sort()  # (y, x) -> printed reading order across wrapped lines
        name = " ".join(text for _, _, text in parts) or None

        # The result cell is only ever on the row's OWN line; a failing
        # row's extra subject-code lines below it must not be read here.
        result = " ".join(
            text for _, text in sorted(
                (x, text) for x, y, text in words
                if x >= result_min_x and abs(y - roll_y) <= ROW_DY
            )
        )
        match = PASS_RE.search(result)
        if not match:
            continue  # failed / absent: subject codes, no numeric total

        records.append({
            "roll_number": roll_number,
            "name": name,
            "marks": int(match.group(1)),
            "group": None,
        })
    return records


def page_records_fn(pdf_path, page_num):
    doc, lock = _get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        words = [
            (w[0], w[1], w[4]) for w in page.get_text("words")
            if w[1] >= HEADER_Y_CUTOFF
        ]

    records = []
    for roll_x, dob_x in COLUMNS:
        lo, hi = roll_x - 10.0, dob_x + COLUMN_WIDTH
        records += _extract_column(
            [w for w in words if lo <= w[0] < hi], roll_x, dob_x
        )
    return records


BOARD_CONFIG = {
    "match_names": ["lahore"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": close_doc,
}

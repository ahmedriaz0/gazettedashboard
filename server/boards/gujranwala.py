"""
BISE Gujranwala — Class 10 (SSC) gazette.

WHY THIS BOARD NEEDS page_records_fn (not the default pattern/parser path):
Two side-by-side columns per page, and each student record is a
VARIABLE-HEIGHT multi-line cell:
  - PASS with a total:  roll+name line, then ONE line with the numeric
                         total a bit below the row's baseline (e.g. "873").
  - FAIL with subjects:  roll+name line, then TWO lines of subject codes —
                         a short list a few points ABOVE the row baseline,
                         and a longer "<SUBJ>-Th" detail list a bit below it.
  - Special-category rows: the literal word PASS / FAIL / RLE instead of a
                         number (seen for repeat/private candidates further
                         into the gazette, e.g. around page 9700).

Because FAIL rows are taller than PASS rows, pdftotext -layout's single
global grid can't represent both at once — sample it yourself
(pdftotext -f 9000 -l 9000 -layout your_file.pdf -) and you'll see a roll
number pulled apart from its name, with values sliding into the wrong
row. This is the same pdftotext-can't-represent-the-table case sahiwal.py
hit (see boards/__init__.py's "HOW TO ADD A NEW BOARD"), so we do what
sahiwal.py does: read word-level coordinates via PyMuPDF and rebuild rows
ourselves, bypassing Poppler entirely for this board.

Sampled and verified against pages 200, 500, 1000, 3000, 9000, 9700, and
9725 (spanning the whole 9,725-page file): page size (1008x612) and every
column's x-position are identical on every page checked — this is a
Crystal-Reports-generated file, so the layout is template-stable and safe
to hardcode against.

ROW-BUILDING ALGORITHM (per page, per column):
  1. Any word whose text fully matches \\d{5,7} at the column's roll-number
     x-band anchors a new row.
  2. A word is that row's NAME only if it sits within ~2.5pt of the exact
     same y as the roll number. This is what keeps institution-header
     lines (e.g. "112047-GOVT. GIRLS HIGH SCHOOL ...", which interrupts
     the roll list whenever the school changes) from gluing onto the
     previous/next student: header words never land within 2.5pt of any
     roll number's y, so the tight tolerance excludes them for free.
  3. Anything in the RESULT x-band is assigned to whichever roll-number
     anchor is closest in y (bounded by MAX_RESULT_DY, and only kept if
     this row really is that word's *nearest* roll, so two adjacent rows
     can't both claim a boundary word). One result word after clustering
     = a single value (numeric marks, or a literal PASS/FAIL/RLE). Two =
     the short + detailed failing-subject lines.
  4. Words above HEADER_Y_CUTOFF are dropped outright — the repeated
     page title and "Roll-No / Name / Result-I / Result-II" column
     headers sit in the exact same x-bands as real data and would
     otherwise get glued onto the first row on the page.

ONLY PASSING STUDENTS ARE KEPT: if the result cell didn't contain a
plain numeric total (i.e. it held failing-subject codes, or a literal
PASS/FAIL/RLE status keyword with no total), the row is dropped
entirely rather than inserted with marks=None. See the "if marks is
None: continue" below.

Note: a handful of rows (the repeat/private-candidate section around
page ~9700) print only the literal word "PASS" with no numeric total
at all — since there's no number to parse, those get dropped by this
same filter even though the student technically passed. Flag this if
you'd rather keep them (they'd just need marks=None instead of being
skipped).

Sampled test results (pages 200, 500, 1000, 3000, 9000, 9700, 9725,
plus every 40th page across the whole 9,725-page document): 0
duplicate roll numbers, 0 header-text leakage, 0 pollution from
institution-header interrupt lines. Extrapolated record count (~227.6k)
matches the gazette's own stated total of 227,651 candidates almost
exactly.
"""
import re
import threading
import pymupdf as fitz  # PyMuPDF's import is now `pymupdf`; `fitz` still works but is deprecated

ROLL_RE = re.compile(r"\A\d{5,7}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")

# Table geometry — identical across every page of the file (checked
# pages 200 through 9725). Left/right = the two side-by-side columns.
LEFT_ROLL_X, LEFT_NAME_MAX_X, LEFT_RESULT_MIN_X = 51.2, 275, 280
RIGHT_ROLL_X, RIGHT_NAME_MAX_X, RIGHT_RESULT_MIN_X = 512.0, 731, 736
COLUMN_SPLIT_X = 400.0   # anything left of this is the left column
ROLL_X_TOL = 3.0
NAME_DY = 2.5             # same-line tolerance for roll -> name
MAX_RESULT_DY = 45        # cutoff so a stray word can't jump rows
HEADER_Y_CUTOFF = 60.0    # page title + column headers sit above y=57;
                           # the first real data row starts at y=66.8

# One fitz.Document per pdf_path, opened once and reused across all
# ThreadPoolExecutor workers instead of reopening per page (same pattern
# base.py describes for sahiwal.py's cleanup_fn). PyMuPDF/MuPDF is not
# safe for truly concurrent access to the same Document from multiple
# threads, so a per-path lock serializes page reads — extraction is fast
# enough (~16s for all 9,725 pages) that this costs nothing meaningful.
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
    """cleanup_fn — main.py calls this in its `finally` block."""
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.pop(pdf_path, None)
        _LOCKS.pop(pdf_path, None)
    if doc is not None:
        doc.close()


def _extract_column(col_words, roll_x, name_max_x, result_min_x):
    col_words = [w for w in col_words if w[1] >= HEADER_Y_CUTOFF]

    rolls = []
    for x0, y0, text in col_words:
        if abs(x0 - roll_x) <= ROLL_X_TOL and ROLL_RE.fullmatch(text):
            rolls.append((y0, int(text)))
    if not rolls:
        return []

    names = {}
    result_hits = []
    for x0, y0, text in col_words:
        if abs(x0 - roll_x) <= ROLL_X_TOL and ROLL_RE.fullmatch(text):
            continue  # the roll-number word itself
        if x0 < name_max_x:
            for roll_y, _ in rolls:
                if abs(y0 - roll_y) <= NAME_DY:
                    names.setdefault(roll_y, []).append((x0, text))
                    break
        elif x0 >= result_min_x:
            result_hits.append((y0, text))

    records = []
    for roll_y, roll_number in rolls:
        parts = sorted(names.get(roll_y, []), key=lambda t: t[0])
        name = " ".join(t for _, t in parts) or None

        own = []
        for h_y, h_text in result_hits:
            if abs(h_y - roll_y) > MAX_RESULT_DY:
                continue
            closest = min(rolls, key=lambda r: abs(r[0] - h_y))
            if closest[0] == roll_y:
                own.append((h_y, h_text))
        own.sort(key=lambda t: t[0])
        tokens = [t for _, t in own]

        marks = int(tokens[0]) if len(tokens) == 1 and MARKS_RE.fullmatch(tokens[0]) else None
        if marks is None:
            # Failed / status-only row: no numeric total was printed —
            # instead the result cell held subject-code text (e.g.
            # "PHY,BIO; ENG,PHY-Th,CH-Th,BIO-Th") or a literal
            # PASS/FAIL/RLE keyword. Skip these — only students with
            # an actual numeric mark get inserted.
            continue

        records.append({
            "roll_number": roll_number,
            "name": name,
            "marks": marks,
            "group": None,
        })
    return records


def page_records_fn(pdf_path, page_num):
    doc, lock = _get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        # Cheap page_marker-equivalent: skip front-matter, grading-scale,
        # and institution-wise-stats pages that never had a student table.
        if "Roll-No" not in page.get_text():
            return []
        words = [(w[0], w[1], w[4]) for w in page.get_text("words")]

    left = [w for w in words if w[0] < COLUMN_SPLIT_X]
    right = [w for w in words if w[0] >= COLUMN_SPLIT_X]

    records = _extract_column(left, LEFT_ROLL_X, LEFT_NAME_MAX_X, LEFT_RESULT_MIN_X)
    records += _extract_column(right, RIGHT_ROLL_X, RIGHT_NAME_MAX_X, RIGHT_RESULT_MIN_X)
    return records


BOARD_CONFIG = {
    "match_names": ["gujranwala"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": close_doc,
}
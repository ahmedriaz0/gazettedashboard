r"""
Shared column-table reader for gazettes that `pdftotext -layout` cannot
represent correctly.

WHY THIS EXISTS
---------------
Most of these gazettes print candidates in fixed columns: a roll number
at one x, the name in a band beside it, the result at another x. Two
things repeatedly defeat a regex over `pdftotext -layout` text:

  * A long NAME wraps onto a second printed line that carries no roll
    number, so a regex whose name class has no "\n" in it stops at the
    line break and stores half a name (see boards/lahore.py,
    boards/sargodha.py).
  * A wrapped or failing row is TALLER than a normal one, and poppler's
    single global text grid cannot express that — it slides the row's
    result cell onto the following printed line. A regex then binds
    marks to the WRONG candidate, silently and plausibly.

Reading word coordinates sidesteps both. This module holds the row
rebuilding that boards/lahore.py and boards/sargodha.py each proved out,
so the remaining boards don't each grow their own copy.

CONTRACT
--------
`build_records(words, columns, ...)` takes the page's words as
(x0, y0, text) triples and a list of (roll_x, name_max_x, marks_x)
column origins, and returns [{"roll_number", "name", "marks", "group"}].

`name_max_x` is separate from `marks_x` because on some boards the result
area starts well before the marks number. Rawalpindi prints a STAT column
("PASS" / "FAIL" / a list of failed subject codes) at x=261 with MARKS at
x=374; since subject codes such as "CHE-I" and "MC-II" are all-caps with a
hyphen, they satisfy any reasonable name-token test, and a name band that
ran to the marks column would swallow them. That is precisely the defect
this replaces: the old regex stored names like
"UMAMA CHE-I CHE-II MC-I MC-II".

Per column, per roll anchor:
  1. A word fully matching `roll_re` at `roll_x` (+/- ROLL_X_TOL) anchors
     a row.
  2. The MARKS cell is read from the anchor's OWN printed line only, and
     only from tokens sitting on `marks_x` itself. Anchoring to that exact
     x — rather than "anywhere to the right" — is what excludes institute
     headers whose trailing "... CHAK NO. 101/SB" number lands in the
     general vicinity but never on the column.
  3. The NAME is every word in the name band (between the roll and marks
     columns) from the anchor's own line down to just above the NEXT
     anchor's line, capped at `max_name_dy`. That span is what recovers
     wrapped continuation lines, and it stops short of the next
     candidate. Words are joined in (y, x) order so a wrapped name reads
     in printed order.

A continuation line must put NOTHING to the LEFT of the name band. A
wrapped name is indented into the name column and nothing else; a real
row puts a roll number out at the left margin, and an institute-header
banner ("GOVT. GIRLS HIGHER SECONDARY SCHOOL NAWAN KOT", which D.G. Khan
interleaves between candidates) starts at the page margin too. One test
therefore rejects both, plus page footers like "384  DISTRICT SARGODHA".

`detect_columns()` finds the column origins from the page itself. Several
of these files mix two page sizes (D.G. Khan and Bahawalpur ship both
portrait and landscape pages; Rawalpindi ships 1008x612 and 1080x792), so
hardcoding one geometry the way gujranwala.py can would silently drop
every page of the other size.
"""
import re
import threading

import pymupdf as fitz  # PyMuPDF's import is now `pymupdf`; `fitz` still works but is deprecated

ROLL_X_TOL = 3.0
MARKS_X_TOL = 3.0
NAME_X_PAD = 6.0
ROW_DY = 3.0
# Candidate names are printed in full caps in every one of these gazettes.
# Requiring that keeps mixed-case intruders (the `www.taleem360.com`
# watermark, footer legends like "Def. Means Fee Defaulter") out of names.
# Underscore is allowed, and allowed to lead, because Faisalabad prints a
# family of names that way — "UMM_E_EMAN", "UMM_E _KALSOOM" — and without
# it those rows land in the database with a NULL name.
NAME_TOKEN_RE = re.compile(r"\A[A-Z_][A-Z._'\-]*\Z")


def _cluster(values, tol):
    """Group sorted x-positions into columns, returning (centre, count)."""
    out = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [(sum(c) / len(c), len(c)) for c in out]


def detect_columns(words, roll_re, marks_re, min_rolls=4, min_marks=2):
    """Infer [(roll_x, marks_x), ...] from one page's own words.

    Roll columns are the x-clusters where `roll_re` tokens pile up. For
    each, the marks column is the densest cluster of `marks_re` tokens
    lying to its right but before the next roll column starts.
    """
    roll_xs = [x for x, _, t in words if roll_re.fullmatch(t)]
    roll_cols = [c for c, n in _cluster(roll_xs, ROLL_X_TOL * 2) if n >= min_rolls]
    if not roll_cols:
        return []

    columns = []
    for i, roll_x in enumerate(roll_cols):
        right_limit = roll_cols[i + 1] - ROLL_X_TOL * 2 if i + 1 < len(roll_cols) else float("inf")
        marks_xs = [
            x for x, _, t in words
            if roll_x + NAME_X_PAD < x < right_limit and marks_re.fullmatch(t)
        ]
        clusters = [c for c in _cluster(marks_xs, MARKS_X_TOL * 2) if c[1] >= min_marks]
        if not clusters:
            continue
        # The result column is the densest such cluster, not merely the
        # first: stray numbers can appear inside a name band.
        columns.append((roll_x, max(clusters, key=lambda c: c[1])[0]))
    return columns


def detect_x(words, predicate, min_count=2):
    """Densest x-cluster among words satisfying `predicate(text)`.

    Used to find a column that isn't the roll or marks column — e.g.
    Rawalpindi's STAT column, located from its PASS/FAIL/IMP keywords, to
    mark where that board's name band has to stop.
    """
    xs = [x for x, _, t in words if predicate(t)]
    clusters = [c for c in _cluster(xs, MARKS_X_TOL * 2) if c[1] >= min_count]
    return max(clusters, key=lambda c: c[1])[0] if clusters else None


def build_records(words, columns, roll_re, marks_re, max_name_dy,
                  name_token_re=NAME_TOKEN_RE, marks_from_cell=None):
    """Rebuild candidate rows from word coordinates. See module docstring.

    `marks_from_cell` optionally overrides how a row's result cell becomes
    a marks value; it receives the list of tokens on the anchor's line at
    or right of the marks column and returns an int, or None to skip the
    row. The default keeps a row only when exactly one bare `marks_re`
    token sits on the marks column.
    """
    records = []
    for ci, (roll_x, name_max_x, marks_x) in enumerate(columns):
        right_limit = (
            columns[ci + 1][0] - ROLL_X_TOL * 2
            if ci + 1 < len(columns) else float("inf")
        )
        col = [w for w in words if roll_x - ROLL_X_TOL * 2 <= w[0] < right_limit]

        anchors = sorted(
            (y, int(t)) for x, y, t in col
            if abs(x - roll_x) <= ROLL_X_TOL and roll_re.fullmatch(t)
        )
        if not anchors:
            continue

        name_min_x = roll_x + ROLL_X_TOL

        # Every printed line that puts something to the LEFT of the name
        # band: a real row's roll number, or an institute-header banner
        # starting at the page margin. A wrapped name line has nothing
        # there, which is how the two are told apart.
        occupied = [y for x, y, _ in col if x < name_min_x]

        for i, (roll_y, roll_number) in enumerate(anchors):
            if marks_from_cell is None:
                cell = [
                    t for x, y, t in col
                    if abs(x - marks_x) <= MARKS_X_TOL
                    and abs(y - roll_y) <= ROW_DY and marks_re.fullmatch(t)
                ]
                if len(cell) != 1:
                    continue
                marks = int(cell[0])
            else:
                cell = [
                    t for _, t in sorted(
                        (x, t) for x, y, t in col
                        if x >= marks_x - NAME_X_PAD and abs(y - roll_y) <= ROW_DY
                    )
                ]
                marks = marks_from_cell(cell)
                if marks is None:
                    continue

            next_y = anchors[i + 1][0] if i + 1 < len(anchors) else roll_y + max_name_dy
            y_hi = min(next_y - ROW_DY, roll_y + max_name_dy)

            parts = [
                (round(y, 1), x, t) for x, y, t in col
                if name_min_x <= x < name_max_x
                and (roll_y - ROW_DY) <= y < y_hi
                and name_token_re.fullmatch(t)
                and (abs(y - roll_y) <= ROW_DY
                     or not any(abs(y - o) <= ROW_DY for o in occupied))
            ]
            parts.sort()  # (y, x) -> printed reading order across wrapped lines
            records.append({
                "roll_number": roll_number,
                "name": " ".join(t for _, _, t in parts) or None,
                "marks": marks,
                "group": None,
            })
    return records


# --- shared PyMuPDF document cache -----------------------------------
# One fitz.Document per pdf_path, opened once and shared by all
# ThreadPoolExecutor workers rather than reopened per page. MuPDF is not
# safe for concurrent access to one Document, so a per-path lock
# serializes page reads. Boards expose close_doc as their cleanup_fn;
# without it Windows raises PermissionError when main.py's `finally`
# block tries to os.remove() a file still held open here.
_DOC_CACHE = {}
_LOCKS = {}
_REGISTRY_LOCK = threading.Lock()


def get_doc_and_lock(pdf_path):
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.get(pdf_path)
        if doc is None:
            doc = fitz.open(pdf_path)
            _DOC_CACHE[pdf_path] = doc
            _LOCKS[pdf_path] = threading.Lock()
        return doc, _LOCKS[pdf_path]


def close_doc(pdf_path):
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.pop(pdf_path, None)
        _LOCKS.pop(pdf_path, None)
    if doc is not None:
        doc.close()


def page_words(pdf_path, page_num, header_y):
    """Words as (x0, y0, text), with page headers dropped."""
    doc, lock = get_doc_and_lock(pdf_path)
    with lock:
        page = doc[page_num - 1]  # fitz is 0-indexed; main.py's pages are 1-indexed
        return [
            (w[0], w[1], w[4]) for w in page.get_text("words")
            if w[1] >= header_y
        ]

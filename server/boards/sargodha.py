r"""
BISE Sargodha gazette format.

WHY THIS BOARD NEEDS page_records_fn (not the previous regex + "parser"
post-filter):

1. NAMES WRAP ONTO A SECOND LINE, and the old regex could only ever see
   the first one. Its name class was `[A-Z\.\- ]` — a literal space, no
   newline — so it stopped dead at the line break:

       500004  SYED MUHAMMAD MAALEK        1030
               ASHTAR

   The candidate's real name is "SYED MUHAMMAD MAALEK ASHTAR"; the old
   parser stored "SYED MUHAMMAD MAALEK". Wrapped rows run at roughly 3-4%
   of candidates.

2. Reading word coordinates also retires the "SCHOOL" heuristic the old
   parser needed. Institute-header rows are printed in the roll column
   and look structurally identical to a candidate row:

       100002  THE EDUCATORS (BOYS) BHAKKAR CAMPUS BHAKKAR
       101602  GOVT. HIGH SCHOOL NOON DAGGAR (BHAKKAR)

   The old regex could be fooled by "... CHAK NO. 101/SB", whose trailing
   3-digit token sits exactly where marks belong, so it dropped any name
   containing "SCHOOL" (118 such false matches on the full document —
   and "THE EDUCATORS" would have slipped through that filter had it
   carried a trailing number). Here the marks cell is identified by its
   x-position instead of by "some 3-4 digit run after the name", so a
   header is excluded for the structural reason that it has no number in
   the marks column at all. No name-content heuristic is involved.

PAGE GEOMETRY (page box 841.7x595.4, landscape, three side-by-side
candidate columns; verified identical on pages 1, 50, 200, 500 and 800 of
the 815-page file):

    column      roll x0     name x0..      marks x0
    left           74.8     108.3 .. 220      228.1
    middle        331.6     365.1 .. 477      484.9
    right         588.4     621.9 .. 734      741.7

The marks column sits exactly 153.3pt right of its roll column in all
three cases. Printed row pitch is ~11.25pt.

ROW-BUILDING ALGORITHM (per page, per column) — same shape as lahore.py:
  1. A word fully matching \d{6} at the column's roll x-band anchors a row.
  2. The NAME is every word in the column's name x-band from the row's own
     printed line down to just above the next anchor's line (capped at
     MAX_NAME_DY), joined in (y, x) order. That span is what recovers the
     wrapped continuation line, and it stops short of the next candidate.
  3. MARKS are read only from the row's OWN line in the marks x-band, and
     only if that cell is a bare 3-4 digit number. Failing candidates print
     subject codes there instead ("MATI TILL 2ND A/2026", "BIOII MATII TILL
     2ND A/2026") and institute headers print nothing, so both are skipped
     — same "only rows with a real numeric total" convention as every other
     board here.
  4. Words above HEADER_Y_CUTOFF are dropped (the repeated
     "ROLL NO / NAME / RESULT" column header sits at y~44).

A `www.taleem360.com` watermark is stamped once per page at x~242 — inside
the left column's result band. It is a single token and never a bare 3-4
digit number, so the marks test ignores it. The same watermark shows up
mid-row on Multan and D.G. Khan (see boards/multan.py).

MEASURED RESULTS.

Full 815-page document, this parser (3.7s):
    69,045 records, 0 duplicate roll numbers, 0 empty names, 0 names
    containing digits / punctuation / institute words. 11,684 of them are
    3 words or longer (max 8). The old parser reported 68,835.

Against that old regex over `pdftotext -layout`, on 136 pages sampled
evenly across the document:
    old parser  : 6,665 records
    this parser : 11,596 records  (+4,931)
    names that DIFFER : 2,103, of which only 16 were simple truncations —
      the other ~2,087 were bound to the WRONG CANDIDATE entirely,
      because poppler's grid slides a taller row's cells onto the next
      printed line. Verified against word coordinates: roll 622737 is
      "HIJAB FATIMA" 859, which the old parser reported as
      "RIMSHA SHABIR" 530.
    rows where the old one reported the WRONG MARKS : 2,778
      e.g. roll 622660 "RAFIA RIAZ" 624 -> 857 (the old 857 had been
      handed to 622661, a clean off-by-one-row shift). One old row even
      captured marks=2025 — the examination year.

"""
import re
import threading

import pymupdf as fitz  # PyMuPDF's import is now `pymupdf`; `fitz` still works but is deprecated

ROLL_RE = re.compile(r"\A\d{6}\Z")
MARKS_RE = re.compile(r"\A\d{3,4}\Z")
# Candidate names are printed in full caps. Requiring that of every name
# word keeps two mixed-case intruders out of the name column: the
# `www.taleem360.com` watermark, and the "Def. Means Fee Defaulter" legend
# printed in the page footer (which otherwise lands inside the last row's
# wrap window and appends itself to that candidate's name).
NAME_TOKEN_RE = re.compile(r"\A[A-Z][A-Z.\-']*\Z")

# (roll x0, marks x0) for each of the three side-by-side columns.
COLUMNS = ((74.8, 228.1), (331.6, 484.9), (588.4, 741.7))
ROLL_X_TOL = 3.0
NAME_X_PAD = 6.0        # keeps the marks cell out of the name band
ROW_DY = 3.0            # same-printed-line tolerance
MAX_NAME_DY = 24.0      # a name may wrap ~2 printed lines (pitch is ~11.25pt)
COLUMN_WIDTH = 95.0     # result-cell width; stops short of the NEXT column's
                        # roll x (331.6 / 588.4), which would otherwise fall
                        # inside this column's result band
HEADER_Y_CUTOFF = 55.0  # column header sits at y~44; first data row at y~65

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
    tries to os.remove() the temp upload."""
    with _REGISTRY_LOCK:
        doc = _DOC_CACHE.pop(pdf_path, None)
        _LOCKS.pop(pdf_path, None)
    if doc is not None:
        doc.close()


def _extract_column(words, roll_x, marks_x):
    name_min_x = roll_x + ROLL_X_TOL
    name_max_x = marks_x - NAME_X_PAD

    anchors = sorted(
        (y, int(text)) for x, y, text in words
        if abs(x - roll_x) <= ROLL_X_TOL and ROLL_RE.fullmatch(text)
    )
    if not anchors:
        return []

    # Every printed line that puts SOMETHING in the roll column. A genuine
    # wrapped name line puts nothing there, so this is what separates a
    # continuation from the page footer ("384  DISTRICT SARGODHA", whose
    # 384 sits on the roll x but is too short to be an anchor) and from any
    # other full row that happens to fall inside the wrap window.
    occupied_ys = [y for x, y, _ in words if abs(x - roll_x) <= ROLL_X_TOL]

    def _is_continuation_line(y):
        return not any(abs(y - oy) <= ROW_DY for oy in occupied_ys)

    records = []
    for i, (roll_y, roll_number) in enumerate(anchors):
        # Marks first: an institute-header row has no number here, so it
        # never becomes a record and we skip the name work entirely.
        cell = [
            text for x, y, text in words
            if abs(x - marks_x) <= ROLL_X_TOL and abs(y - roll_y) <= ROW_DY
            and MARKS_RE.fullmatch(text)
        ]
        # A real total is a bare 3-4 digit token sitting ON the marks
        # column (they are left-aligned there, 3- and 4-digit alike).
        # Anchoring to that exact x — rather than "anywhere to the right"
        # — is what excludes institute-header rows: a header like
        # "GOVT. GIRLS HIGH SCHOOL CHAK NO. 101/SB" does put a 3-digit
        # token in the general vicinity, but it falls wherever the header
        # text happens to flow, never on the marks column. Failing rows
        # print subject codes there instead ("MATI TILL 2ND A/2026") and
        # yield nothing. This also makes the row immune to the page
        # watermark landing on its baseline.
        if len(cell) != 1:
            continue

        # The name owns its own line plus any wrapped continuation lines,
        # stopping short of the next candidate's line.
        next_y = anchors[i + 1][0] if i + 1 < len(anchors) else roll_y + MAX_NAME_DY
        y_hi = min(next_y - ROW_DY, roll_y + MAX_NAME_DY)

        parts = [
            (round(y, 1), x, text) for x, y, text in words
            if name_min_x <= x < name_max_x and (roll_y - ROW_DY) <= y < y_hi
            and NAME_TOKEN_RE.fullmatch(text)
            and (abs(y - roll_y) <= ROW_DY or _is_continuation_line(y))
        ]
        parts.sort()  # (y, x) -> printed reading order across wrapped lines
        name = " ".join(text for _, _, text in parts) or None

        records.append({
            "roll_number": roll_number,
            "name": name,
            "marks": int(cell[0]),
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
    for roll_x, marks_x in COLUMNS:
        lo, hi = roll_x - 10.0, marks_x + COLUMN_WIDTH
        records += _extract_column(
            [w for w in words if lo <= w[0] < hi], roll_x, marks_x
        )
    return records


BOARD_CONFIG = {
    "match_names": ["sargodha", "sarghoda"],
    "fields": ["roll_number", "name", "marks"],
    "page_records_fn": page_records_fn,
    "cleanup_fn": close_doc,
}

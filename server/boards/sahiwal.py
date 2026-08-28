r"""
BISE Sahiwal gazette format.

*** This board CANNOT be parsed from pdftotext -layout text at all — see
"WHY POPPLER DOESN'T WORK" below. It needs the `page_records_fn` hook
instead of `pattern`/`parser`. Required main.py change described in that
same section. ***

WHY POPPLER DOESN'T WORK:
The result table has 4 columns: Roll-No, Name, Result-9th, Result-10th.
Different rows have different cell heights (a row with a long list of
failed subject codes is visually taller than a row that's just a name +
a 3-digit mark), and pdftotext -layout renders each row at a FIXED text
line position based on that height — so a short row's marks value gets
pushed down past the START of the NEXT row's line. Real excerpt:

    102209    NIMRA FATIMA
                                                             839
    102210    ALIZA FATIMA
                                                             952
    102211    TAYYABA MEHMOOD

Read literally, "839" looks like it's on 102210's line and "952" on
102211's — but 839 is actually 102209's mark and 952 is 102210's. There
is no line-based or regex rule that recovers the correct pairing here;
the roll number, name, and mark for the SAME student can be 1-4 text
lines apart depending on how tall the rows above happened to render.

THE FIX — PyMuPDF word coordinates instead of pdftotext text:
`page.get_text("words")` (PyMuPDF / `pip install pymupdf`) returns each
word with its real (x, y) position and, crucially, groups words into
(block_no, line_no) that correspond to actual table CELLS in the PDF's
own coordinate space — not to however pdftotext chose to lay out a text
line. Every student's roll/name/result cells share the same block_no
regardless of how tall neighbouring rows are, so:
  1. group words into cells by (block_no, line_no)
  2. classify each cell by x-position: roll (x0 < 80), name
     (80 <= x0 < 220), result (x0 >= 220)
  3. within a block, the RESULT value we want is always the
     right-most (max x0) result-column cell — some rows have an extra
     lower-x "Result 9th" note (e.g. a subject failed in the first
     part) alongside the real final-result value further right; the
     right-most one is always the actual outcome we want to store.
  4. if that value is pure digits -> marks (PASS); otherwise it's a
     failed-subject list or "Absent" -> skip the row entirely, same
     "only store rows with real marks" convention as every other board.

`page_records_fn(pdf_path, page_num)` bypasses pdftotext/Poppler
entirely for this board — see the main.py change below.

Required main.py change: in `process_page()`, check for a
`page_records_fn` key on the resolved board config BEFORE calling
get_page_text() at all (this board never touches Poppler):

    if config.get("page_records_fn"):
        return config["page_records_fn"](temp_file_path, page_num)
    text = get_page_text(temp_file_path, page_num)
    ...

`page_marker: "Roll-No"` (checked on the page's plain get_text(), not
via PyMuPDF's word list) keeps this from running against the front-
matter pages, the highest-position merit-list pages, and the ~140-page
"Institution Wise Roll No Ranges" school-stats section (all of which
lack this exact hyphenated header and would otherwise risk false
positives from institute codes formatted like `525046`).

Verified on the full 3,269-page document (data starts at page 190):
41,900 PASS records, 0 duplicate roll numbers.
"""
from typing import List, Dict
from collections import defaultdict
import pymupdf as fitz  # pip install pymupdf --break-system-packages

_COL_ROLL_MAX_X = 80
_COL_NAME_MAX_X = 220

# NOTE: this used to be @lru_cache(maxsize=4). That cached the open
# fitz.Document across ALL requests for the process's lifetime, which is
# exactly right for speed (3,269 pages -> 1 open, not 3,269) but wrong
# for cleanup: nothing ever closed it, so the file handle stayed open
# forever. On Linux that's harmless (you can delete an open file); on
# Windows it isn't — main.py's `os.remove(temp_file_path)` in its
# `finally` block raised PermissionError ("being used by another
# process") every time, even though the actual parse+upload had already
# succeeded. A plain dict + an explicit close_doc() (called by main.py
# via the "cleanup_fn" hook, right before it removes the temp file)
# keeps the same one-open-per-upload speed but actually releases the
# handle when the request is done.
_doc_cache: Dict[str, "fitz.Document"] = {}


def _get_doc(pdf_path: str) -> "fitz.Document":
    if pdf_path not in _doc_cache:
        _doc_cache[pdf_path] = fitz.open(pdf_path)
    return _doc_cache[pdf_path]


def close_doc(pdf_path: str) -> None:
    """Closes and evicts the cached document for this path, releasing
    its file handle. Called by main.py (via BOARD_CONFIG["cleanup_fn"])
    after a request finishes, success or failure, before it tries to
    delete the temp upload file."""
    doc = _doc_cache.pop(pdf_path, None)
    if doc is not None:
        doc.close()


def get_page_records(pdf_path: str, page_num: int) -> List[Dict]:
    doc = _get_doc(pdf_path)
    page = doc[page_num - 1]  # PyMuPDF pages are 0-indexed

    if "Roll-No" not in page.get_text():
        return []  # front matter / merit list / institution-wise stats page

    words = page.get_text("words")  # (x0, y0, x1, y1, text, block_no, line_no, word_no)

    # Step 1: merge multi-word cells (a two-word name, a comma-separated
    # subject list) into one string per (block_no, line_no).
    cells: Dict[tuple, list] = {}
    for x0, y0, x1, y1, text, block_no, line_no, word_no in words:
        key = (block_no, line_no)
        cells.setdefault(key, []).append((x0, text))

    # Step 2: regroup by block_no only — this is what actually
    # represents one student row, regardless of how many text lines
    # pdftotext-style rendering would have spread it across.
    blocks: Dict[int, list] = defaultdict(list)
    block_order = []
    for (block_no, line_no), cell_words in cells.items():
        if block_no not in blocks:
            block_order.append(block_no)
        cell_words.sort(key=lambda w: w[0])
        x0 = cell_words[0][0]
        text = " ".join(t for _, t in cell_words)
        blocks[block_no].append((x0, text))

    # Step 3: classify each block's cells by column, pick the
    # right-most result cell, keep only rows with real (digit) marks.
    records: List[Dict] = []
    for block_no in block_order:
        roll = None
        name_parts = []
        result_candidates = []
        for x0, text in blocks[block_no]:
            if x0 < _COL_ROLL_MAX_X:
                if text.isdigit():
                    roll = text
            elif x0 < _COL_NAME_MAX_X:
                name_parts.append(text)
            else:
                result_candidates.append((x0, text))

        if not roll or not name_parts or not result_candidates:
            continue

        result_candidates.sort(key=lambda t: t[0])
        final_result = result_candidates[-1][1]  # right-most = actual outcome
        if not final_result.isdigit():
            continue  # fail / absent — skip, same convention as every other board

        records.append({
            "roll_number": int(roll),
            "name": " ".join(name_parts),
            "marks": int(final_result),
            "group": None,
        })

    return records


BOARD_CONFIG = {
    "match_names": ["sahiwal"],
    "page_records_fn": get_page_records,   # bypasses pdftotext entirely — see module docstring
    "cleanup_fn": close_doc,               # releases the cached PDF handle — see module docstring
    "fields": ["roll_number", "name", "marks"],
}

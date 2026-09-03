r"""
Tesseract OCR as a second source of page words, for the pages Poppler and
PyMuPDF cannot read.

WHY THIS EXISTS
---------------
Every parser in this package ultimately wants the same thing: the page's
words as (x0, y0, text) in page points, so boards/_coltable.py can rebuild
rows from column geometry instead of from a flattened text grid. That
normally comes from the PDF's own text layer via `page.get_text("words")`.

Some pages don't have one, or have one that lies:

  * A scanned or image-only page yields ZERO words. Every board here then
    returns [] for that page — silently, since an empty page is
    indistinguishable from a front-matter page.
  * A diagonal watermark can inject stray glyphs between a name and its
    marks, or scramble the text layer's reading order so roll numbers
    drop out of a block entirely (both documented in boards/multan.py's
    "Still NOT recovered" list).

Rendering the page and reading it with Tesseract
(https://github.com/tesseract-ocr/tesseract) sidesteps both: OCR sees what
is actually printed, at real coordinates, whether or not a text layer
exists or agrees.

HOW IT PLUGS IN
---------------
`page_words(page)` and `page_text(page)` are drop-in replacements for
`page.get_text("words")` / `page.get_text()`, and every coordinate board
calls them instead. What they return depends on OCR_MODE:

    off     never run Tesseract; identical to the old behaviour.
    auto    (default) use the embedded text layer, and fall back to OCR
            only for a page whose text layer is empty. Boards that were
            measured against real gazettes keep exactly the numbers they
            were verified with, and scanned pages stop being dropped.
    force   ignore the text layer and OCR every page. Use this on a
            document whose text layer is present but wrong. It costs
            0.7-1.3 s of CPU per page here, against a few ms for
            `page.get_text` — at PARSE_MAX_WORKERS=4 that turns the
            9,725-page Gujranwala gazette from a couple of minutes into
            roughly half an hour — and it carries OCR's own error rate on
            names and marks. Hence not the default.

HOW GOOD IS IT
--------------
Measured by running `force` over pages that DO have a good text layer and
diffing the records against that layer's — 14 pages, two per coordinate
board, 677 reference records:

    recovered (roll matched)   654   96.6%
      ... with identical marks 652   99.7% of those
      ... with identical name  628   96.0% of those

And end to end, through `auto` rather than `force`: six gazette pages
re-rendered into image-only PDFs (no text layer at all, which is what a
scan looks like to both poppler and PyMuPDF), run through their own board
unchanged and diffed against the same pages of the real file —

    faisalabad   82 rows   82 recovered   82 marks   82 names
    sargodha    183 rows  178 recovered  178 marks  172 names
    rawalpindi   49 rows   49 recovered   49 marks   45 names
                314        309  (98.4%)   100%        96.8%

Those pages return ZERO records without this module. Note the inputs were
rendered from vector sources, so they are clean, straight and evenly lit:
a real scan will do worse, and how much worse is worth measuring on the
first real one rather than assuming from these numbers.

The residual misses are mostly rows whose roll number OCR read wrong,
which drop out rather than land under a wrong roll.

The safety net for OCR errors is the parsers themselves: `roll_re`,
`marks_re` and `NAME_TOKEN_RE` accept only tokens of the right SHAPE, so a
misread character usually drops the token rather than corrupting a record.
That is also why OCR_MIN_CONF defaults to 0 — shape validation filters
garbage better than a confidence threshold, and a confidence cut-off would
silently drop good marks cells.

It is not airtight, and the gap is worth knowing: a table rule read as a
digit turns a valid 3-digit mark into a valid 4-digit one (754 -> 7154,
880 -> 8380 in the sample above), which `marks_re`'s `\d{3,4}` accepts.
Two rows in 677. If that matters more than coverage does, the place to
catch it is a plausibility bound on marks in the board module, not a
confidence threshold here.

WHAT OCR DOES NOT FIX
---------------------
boards/multan.py is the one board still parsed by a regex over flattened
text, and it does not work over OCR text: this gazette prints a vertical
rule between the roll and name columns, which Tesseract reads as a
character stuck to the roll number ("111882/SIDRA RIAZ" as ONE token).
The pattern needs `\d{6}` followed by spaces, so it matches nothing —
measured 0 records on OCR text against 73/66/75 from poppler on the same
pages. No amount of layout reconstruction helps, because the damage is
inside a single OCR token. A scanned Multan gazette would have to be
converted to a coordinate parser like every other board here; see
boards/__init__.py.

COORDINATES
-----------
Tesseract reports pixel boxes in the rendered image; they are scaled back
to page points by 72/OCR_DPI, which is the same space `page.get_text` uses.
Two deliberate differences from PyMuPDF's boxes:

  * A word's y is taken from its LINE's box, not its own. _coltable's row
    matching compares `abs(y - roll_y) <= ROW_DY`, and per-word ink tops
    vary by a point or two between digits and letters (an all-caps name
    against a row of digits), which eats into that budget for no reason.
    Words Tesseract puts on one line therefore share one y. Under --psm 11
    a printed row can still come back as more than one "line", so this
    tightens the spread rather than eliminating it — ROW_DY covers the
    rest.
  * OCR boxes hug the ink, while PyMuPDF's include the font's full line
    height, so OCR y values sit slightly lower than text-layer ones for
    the same row. That is well inside every HEADER_Y_CUTOFF margin in this
    package, but it is why those cutoffs should not be tightened to the
    point where a few points matter.

INSTALLING TESSERACT
--------------------
  Docker/Linux  apt-get install -y tesseract-ocr tesseract-ocr-eng
                (already in server/Dockerfile)
  Windows       the UB-Mannheim build, https://github.com/UB-Mannheim/tesseract
                `winget install -e --id UB-Mannheim.TesseractOCR`
                Found automatically at its default install location; set
                TESSERACT_BIN (full path) or TESSERACT_BIN_DIR to override.

In `auto` mode a missing binary is not fatal — it logs once and behaves
like `off`. In `force` mode it raises, because the caller asked for OCR
specifically and silently not doing it would be worse.
"""
import os
import shutil
import subprocess
import threading

import pymupdf as fitz

from . import _coltable as ct

# --- configuration ---------------------------------------------------
MODE = os.environ.get("OCR_MODE", "auto").strip().lower()
# 300 measured better overall than 400 or 500 and renders ~1.8x faster than
# 400: the extra pixels help Bahawalpur slightly and hurt D.G. Khan and
# Sargodha, because these are vector PDFs whose glyphs are already sharp at
# 300 — upsampling only magnifies the table rules Tesseract then reads as
# characters. Raise it for a genuinely low-resolution SCAN, where the
# trade-off is the other way round.
DPI = int(os.environ.get("OCR_DPI", "300"))
LANG = os.environ.get("OCR_LANG", "eng")
# --psm 11 = "sparse text: find as much text as possible in no particular
# order". That is exactly the job here. Every layout-aware mode (3 auto, 4
# single column, 6 single uniform block) first tries to decide what the
# page's blocks and reading order ARE, and on a gazette it decides wrong:
# it reads a two-candidate-per-line row as running text, glues adjacent
# cells into one word ("MUHAMMADTAYYABDAR", "ASIMNASIR"), turns column
# rules and dotted leaders into character noise, and on the ruled D.G.
# Khan / Bahawalpur / Gujranwala tables produces nothing usable at all.
# psm 11 skips that analysis and just locates text. Reading order is no
# loss to us — the parsers rebuild rows from x/y, never from order.
#
# Measured, one page per board, OCR records vs. the same page's text-layer
# records (matched roll / exactly equal name AND marks), at OCR_DPI=300:
#
#     board        psm 6            psm 11
#     faisalabad     0%   /   0%    100%  / 100%
#     lahore        81%   /  75%     92%  /  88%
#     sargodha      80%   /  71%     99%  /  97%
#     gujranwala     0%   /   0%    100%  / 100%
#     bahawalpur     0%   /   0%     94%  /  86%
#     dgkhan         0%   /   0%     93%  /  86%
#     rawalpindi    84%   /  84%    100%  / 100%
#
# psm 12 (11 plus orientation detection) scored identically on every one
# of those and costs an extra detection pass, so 11 it is.
PSM = os.environ.get("OCR_PSM", "11")
# Keep every token Tesseract emits by default; see the note on OCR_MIN_CONF
# in the module docstring.
MIN_CONF = float(os.environ.get("OCR_MIN_CONF", "0"))
# Two OCR "lines" whose tops sit within this many points are one printed
# line, when rebuilding layout text. Row pitch in these gazettes is 12pt at
# the tightest (boards/faisalabad.py), so this stays well clear of merging
# two real rows. Only affects ocr_text(); ocr_words() reports y unrounded
# and the parsers apply their own ROW_DY.
LINE_Y_TOL_PT = 3.0

_WINDOWS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Tesseract-OCR\tesseract.exe"),
)


def _resolve_binary():
    """Same dynamic-resolution shape main.py uses for the Poppler tools:
    PATH on Linux/Docker, a known install location on a Windows dev box."""
    explicit = os.environ.get("TESSERACT_BIN")
    if explicit:
        return explicit
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    bin_dir = os.environ.get("TESSERACT_BIN_DIR")
    if bin_dir:
        return os.path.join(bin_dir, "tesseract.exe" if os.name == "nt" else "tesseract")
    for candidate in _WINDOWS_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


TESSERACT_BIN = _resolve_binary()

_warned = False


def _warn_missing_once():
    global _warned
    if not _warned:
        _warned = True
        print("[!] OCR_MODE=auto but the tesseract binary was not found — "
              "pages with no text layer will stay empty. Install Tesseract "
              "or set TESSERACT_BIN. (See boards/ocr.py.)")


def available() -> bool:
    return TESSERACT_BIN is not None


def enabled() -> bool:
    """True when OCR may run at all for this process."""
    return MODE in ("auto", "force")


def forced() -> bool:
    """True when the text layer is to be ignored entirely."""
    return MODE == "force"


# --- OCR -------------------------------------------------------------
def _run_tesseract(png_bytes: bytes) -> str:
    """Image bytes in on stdin, Tesseract's TSV out on stdout.

    Piping avoids writing one temp image per page, which matters: main.py
    runs PARSE_MAX_WORKERS of these concurrently over documents up to
    9,725 pages.
    """
    if TESSERACT_BIN is None:
        if forced():
            raise RuntimeError(
                "OCR_MODE=force but the tesseract binary was not found. "
                "Install Tesseract or set TESSERACT_BIN. (See boards/ocr.py.)"
            )
        _warn_missing_once()
        return ""
    result = subprocess.run(
        [TESSERACT_BIN, "-", "-", "-l", LANG, "--psm", PSM, "--dpi", str(DPI), "tsv"],
        input=png_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        if forced():
            raise RuntimeError(
                f"tesseract exited {result.returncode}: "
                f"{result.stderr.decode('utf-8', 'replace').strip()[:400]}"
            )
        return ""
    # Tesseract writes UTF-8. Decode explicitly rather than letting the
    # OS codepage decide — the exact bug fixed for pdftotext in main.py.
    return result.stdout.decode("utf-8", "replace")


def _parse_tsv(tsv: str):
    """TSV rows -> [(x_px, y_px, text)], with each word's y taken from its
    line's box so a printed line has ONE y. See COORDINATES above.

    Columns: level page block par line word left top width height conf text
    """
    line_tops = {}
    words = []
    for row in tsv.splitlines()[1:]:          # row 0 is the header
        cols = row.split("\t", 11)
        if len(cols) < 12:
            continue
        try:
            level = int(cols[0])
            key = (cols[2], cols[3], cols[4])  # block, par, line
            left, top = int(cols[6]), int(cols[7])
            conf = float(cols[10])
        except ValueError:
            continue
        if level == 4:                         # a line box
            line_tops[key] = top
            continue
        if level != 5:                         # 1-3 are page/block/paragraph
            continue
        text = cols[11].strip()
        if not text or conf < MIN_CONF:
            continue
        words.append((left, line_tops.get(key, top), text))
    return words


def _render_png(page) -> bytes:
    # Greyscale, no alpha: Tesseract binarises internally anyway, and this
    # is far less data to pipe than RGBA.
    zoom = DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom),
                          colorspace=fitz.csGRAY, alpha=False)
    return pix.tobytes("png")


# One page is usually asked for its text (the board's page-marker check)
# and then for its words, so a naive implementation would OCR it twice.
# Small bounded cache, keyed by document path + page number.
_CACHE = {}
_CACHE_ORDER = []
_CACHE_MAX = 32
_CACHE_LOCK = threading.Lock()


def _ocr_words_px(page):
    key = (getattr(page.parent, "name", None), page.number)
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]
    words = _parse_tsv(_run_tesseract(_render_png(page)))
    with _CACHE_LOCK:
        _CACHE[key] = words
        _CACHE_ORDER.append(key)
        while len(_CACHE_ORDER) > _CACHE_MAX:
            _CACHE.pop(_CACHE_ORDER.pop(0), None)
    return words


def ocr_words(page):
    """Page words as (x0, y0, text) in PAGE POINTS, straight from OCR."""
    scale = 72.0 / DPI
    return [(x * scale, y * scale, t) for x, y, t in _ocr_words_px(page)]


def ocr_text(page) -> str:
    """OCR words rebuilt into `pdftotext -layout`-style text.

    The regex board (boards/multan.py) and every board's page-marker check
    read a flat string with columns still separated by runs of spaces, so
    Tesseract's plain text output — which collapses the gutter between two
    side-by-side candidates — is not enough. Words are placed at
    round(x / char_width) instead, which reproduces the column spacing.
    """
    words = _ocr_words_px(page)
    if not words:
        return ""

    # One character cell, derived from the render DPI rather than measured
    # per page: Tesseract's box widths vary with the glyphs on the line, so
    # a median of width/len is skewed by short tokens. 12 chars per inch is
    # the pitch pdftotext -layout assumes for these gazettes' body text.
    char_w = max(DPI / 12.0, 1.0)

    # Group into printed lines with a tolerance, not by equal y. Under
    # --psm 11 Tesseract finds text without deciding what the page's lines
    # are, so two cells of ONE printed row can come back as separate
    # "lines" whose tops differ by a pixel or two. Keyed on exact y, a page
    # marker straddling that split ("Roll No | Name") would never be found
    # as one string.
    tol = max(DPI * LINE_Y_TOL_PT / 72.0, 1.0)
    lines = {}
    for x, y, t in sorted(words, key=lambda w: w[1]):
        row = next((r for r in lines if abs(r - y) <= tol), y)
        lines.setdefault(row, []).append((x, t))

    out = []
    for y in sorted(lines):
        row = ""
        for x, t in sorted(lines[y]):
            col = int(x / char_w)
            # `<=`, not `<`: at `==` the word would be appended with zero
            # padding and fuse to its neighbour ("Roll NoName",
            # "814247SHABANA JAMEEL"), which is precisely what stops a
            # page marker or a board's regex from matching.
            if col <= len(row):
                col = len(row) + 1
            row += " " * (col - len(row)) + t
        out.append(row)
    return "\n".join(out)


# --- the entry points boards call ------------------------------------
def page_words(page):
    """Drop-in for `page.get_text("words")`, as (x0, y0, text) triples,
    with OCR applied per OCR_MODE. See "HOW IT PLUGS IN" above."""
    if forced():
        return ocr_words(page)
    words = [(w[0], w[1], w[4]) for w in page.get_text("words")]
    if words or not enabled():
        return words
    return ocr_words(page)             # image-only page


def page_text(page) -> str:
    """Drop-in for `page.get_text()`, with OCR applied per OCR_MODE."""
    if forced():
        return ocr_text(page)
    text = page.get_text()
    if text.strip() or not enabled():
        return text
    return ocr_text(page)


def page_words_for_pdf(pdf_path, page_num):
    """`page_words` addressed by path + 1-based page, for callers that
    don't already hold a page (main.py). Uses _coltable's shared document
    cache, so remember _coltable.close_doc() in cleanup."""
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        return page_words(doc[page_num - 1])


def page_text_for_pdf(pdf_path, page_num) -> str:
    """`page_text` addressed by path + 1-based page. See above."""
    doc, lock = ct.get_doc_and_lock(pdf_path)
    with lock:
        return page_text(doc[page_num - 1])



if __name__ == "__main__":
    # Dry-run one page before trusting a board to it:
    #   python -m boards.ocr <file.pdf> <page> [text|words]
    import sys

    path, page_no = sys.argv[1], int(sys.argv[2])
    what = sys.argv[3] if len(sys.argv) > 3 else "text"
    print(f"tesseract: {TESSERACT_BIN}  mode={MODE} dpi={DPI} psm={PSM}")
    doc = fitz.open(path)
    pg = doc[page_no - 1]
    if what == "words":
        for w in ocr_words(pg):
            print(f"{w[0]:8.1f} {w[1]:8.1f}  {w[2]}")
    else:
        print(ocr_text(pg))
    doc.close()

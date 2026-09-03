"""
Board registry. This is the ONLY file that needs to know every board
module exists — nothing else in the app imports the board files
directly.

HOW TO ADD A NEW BOARD:
1. Sample the PDF: run
     pdftotext -f <page> -l <page> -layout your_file.pdf -
   on a page containing real student rows (skip intro/summary pages) and
   look at the raw text. If rows look scrambled or mis-paired even
   though the raw text "looks fine" on screen, try opening it with
   PyMuPDF instead (`page.get_text("words")`) — pdftotext -layout can
   silently misplace values when row heights vary (see sahiwal.py) or
   scramble reading order entirely under certain watermarks.
2. Copy the closest-matching existing module as a template:
     - multan.py       — the ONLY board still parsed by regex over
                         `pdftotext -layout` text. Try this shape first;
                         it is much less code when it works.
     - faisalabad.py   — coordinate-based, single column, one page size.
                         The simplest page_records_fn here.
     - bahawalpur.py   — coordinate-based, two columns, right-aligned marks
     - lahore.py / sargodha.py — coordinate-based, three columns, names
                         that WRAP onto extra printed lines
     - dgkhan.py / rawalpindi.py — coordinate-based, two columns, plus a
                         result area that has to be excluded from the name
                         band by its own x (see each docstring)
     - gujranwala.py / sahiwal.py — coordinate-based with hardcoded
                         geometry (single, stable page size)

   MOST BOARDS NEED COORDINATES, NOT A REGEX. `pdftotext -layout` flattens
   a gazette's variable-height rows onto one global text grid, so a taller
   row (a wrapped name, a multi-line failed-subject list) pushes its own
   result cell onto the following text line. A regex then binds marks to
   the WRONG candidate — silently, and producing plausible-looking rows.
   Every board here that was measured against word coordinates turned out
   to be doing this. If a board's rows vary in height at all, go straight
   to boards/_coltable.py, which does the row rebuilding for you: give it
   the column origins (it can detect them per page) and it returns
   roll_number/name/marks/group with wrapped names joined.

   See boards/base.py for the full BOARD_CONFIG contract (pattern /
   page_marker / skip_page / parser / page_records_fn — use only the ones
   your board actually needs).
3. Add "<newboard>" to `match_names` (lowercase substrings that should
   map an incoming board dropdown value to this module).
4. Import and register it below, in BOARD_MODULES.
5. Test standalone before wiring into the API: dry-run your
   pattern/parser/page_records_fn across the WHOLE document (not just
   the sample page) and check for a plausible total record count and
   zero duplicate roll numbers before trusting it against Supabase.
   Zero duplicates is NOT on its own evidence of correctness — several
   modules here claimed it while assigning marks to the wrong students.
   Also check: how many rows come back with an empty name, how many names
   contain digits, punctuation or subject-code words, and — the one that
   actually catches row misalignment — spot-check a handful of records
   against `page.get_text("words")` coordinates rather than against
   `pdftotext -layout` output, which is what misleads in the first place.

That's it. main.py's upload/search endpoints never need to change —
only process_page()'s hook-dispatch logic does, and only if a genuinely
new KIND of quirk shows up (not for every new board).
"""
from . import lahore, faisalabad, bahawalpur, dgkhan, sargodha, rawalpindi, sahiwal, gujranwala, multan, generic

# Every board module lives here. Order doesn't matter.
BOARD_MODULES = {
    "Lahore": lahore.BOARD_CONFIG,
    "Faisalabad": faisalabad.BOARD_CONFIG,
    "Bahawalpur": bahawalpur.BOARD_CONFIG,
    "DG Khan": dgkhan.BOARD_CONFIG,
    "Sargodha": sargodha.BOARD_CONFIG,
    "Rawalpindi": rawalpindi.BOARD_CONFIG,
    "Sahiwal": sahiwal.BOARD_CONFIG,
    "Gujranwala": gujranwala.BOARD_CONFIG,
    "Multan": multan.BOARD_CONFIG,
}

GENERIC_CONFIG = generic.BOARD_CONFIG


def resolve_board(board_label: str):
    """
    Maps a free-text board name (e.g. "BISE Lahore", "Faisalabad Board")
    to (normalized_name, config). Falls back to the generic config if
    nothing matches.
    """
    label_lower = board_label.lower()
    for normalized_name, config in BOARD_MODULES.items():
        if any(alias in label_lower for alias in config["match_names"]):
            return normalized_name, config
    return "Generic", GENERIC_CONFIG

"""
Base contract every board module follows.

Each board file (lahore.py, faisalabad.py, bahawalpur.py, dgkhan.py,
sargodha.py, rawalpindi.py, sahiwal.py, ...) defines a BOARD_CONFIG dict.
Only "match_names" and "fields" are always required — everything else is
opt-in, used only by the boards whose PDF actually needs it.

BOARD_CONFIG = {
    "match_names": ["lahore"],       # REQUIRED. Lowercase substrings that
                                      # map an incoming `board` form value
                                      # to this module — see resolve_board().

    "fields": ["roll_number", "name", "marks"],   # REQUIRED. Informational
                                      # — what this board's gazette actually
                                      # gives us.

    "pattern": re.compile(           # Used by the DEFAULT path in
        r"...",                      # main.py's process_page(): named
        re.MULTILINE,                # groups (?P<roll_number>...),
    ),                                # (?P<name>...), (?P<marks>...),
                                      # optionally (?P<group>...). Pass any
                                      # flags directly as re.compile()'s 2nd
                                      # arg. Skipped entirely if "parser" or
                                      # "page_records_fn" is present.

    "page_marker": "Roll No",        # OPTIONAL. A string, or a list of
                                      # strings (ANY match counts — see
                                      # rawalpindi.py). If present, main.py
                                      # skips a page entirely unless the
                                      # marker text appears in it. Use this
                                      # to keep a board's pattern from ever
                                      # running against front-matter /
                                      # merit-list / institution-stats pages.

    "skip_page": some_function,      # OPTIONAL. Callable(page_text) -> bool.
                                      # main.py calls it AFTER the
                                      # page_marker check; True means skip
                                      # the whole page. Use this for a
                                      # specific known false-positive
                                      # source that page_marker alone can't
                                      # exclude (see bahawalpur.py).

    "parser": some_function,         # OPTIONAL. Callable(page_text) ->
                                      # List[{"roll_number","name","marks",
                                      # "group"}]. REPLACES the default
                                      # pattern.finditer() loop entirely —
                                      # use this when matches need post-
                                      # filtering a bare regex can't express
                                      # (see sargodha.py).

    "page_records_fn": some_function, # OPTIONAL. Callable(pdf_path,
                                      # page_num) -> List[{"roll_number",
                                      # "name","marks","group"}]. If
                                      # present, main.py calls this INSTEAD
                                      # of get_page_text()/pdftotext
                                      # entirely for this board — use this
                                      # when pdftotext -layout can't
                                      # represent the table correctly at
                                      # all (see sahiwal.py, which reads
                                      # word coordinates via PyMuPDF).

    "cleanup_fn": some_function,     # OPTIONAL. Callable(pdf_path) -> None.
                                      # main.py calls this in its `finally`
                                      # block, BEFORE it tries to delete the
                                      # temp upload file. Needed by any
                                      # board that keeps a file handle open
                                      # across the whole request (currently
                                      # sahiwal.py, which caches an open
                                      # PyMuPDF Document to avoid reopening
                                      # the PDF once per page) — without
                                      # this, Windows raises PermissionError
                                      # on os.remove() even though the
                                      # parse+upload already succeeded.
}

Why named groups instead of positional tuples: as boards diverge (e.g. a
board with "group" but no "name", or a different field order), positional
tuple-unpacking silently breaks. Named groups make each board file
self-describing and safe to reorder.

Precedence in main.py's process_page() (first match wins):
  1. page_records_fn  (bypasses pdftotext entirely)
  2. page_marker check (skip page if marker absent)
  3. skip_page check   (skip page if flagged)
  4. parser            (replaces the regex loop)
  5. pattern.finditer() (default)

cleanup_fn runs separately, in main.py's `finally` block, after all of
the above — not part of this precedence chain.
"""

# All possible output columns in the `student_results` Supabase table.
# Any field NOT produced by a board's regex/parser is left as None.
ALL_FIELDS = ["roll_number", "name", "marks", "group"]

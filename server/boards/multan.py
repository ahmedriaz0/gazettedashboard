r"""
BISE Multan gazette format.

Sample raw line (via `pdftotext -layout`) — NOTE: this gazette prints two
candidates side-by-side per physical line (left column + right column),
unlike Lahore/Faisalabad which are one-candidate-per-line:

    100003 ADEELA MUMTAZ                         869                      100063 NIDA BATOOL
    100121 DUA IMRAN                              1143                       100181 QURAT UL AIN                        ABSENT

Fields available: roll_number, name, marks (no group/DOB info present;
this gazette is SSC-only, confirmed by sampling pages 1, 500, 700, 900
and 1043 of a 1043-page sample file — all show the same
"Secondary School Certificate (Ist Annual) Examination" header, so
"group" is never populated here).

Why this needed its own module instead of reusing an existing one
(verified against the real 1043-page / ~87.6k-row gazette):
  - lahore.py:      0 matches. Multan has no "DD/MM/YY ... PASS" token.
  - faisalabad.py:  ~45k matches instead of ~87.6k. Its regex anchors
                    marks to end-of-line ($), which only catches the
                    RIGHT-hand column here and silently drops almost
                    every LEFT-hand candidate — a ~50% silent data-loss
                    bug, not a clean failure.
  - generic.py:     0 matches. No "PASS" keyword appears anywhere.

Failed/absent handling: failing/absent candidates show either the literal
word "ABSENT" or a wrapped list of subject codes ("PHY-A CH-B BIO-A TILL
SA-2026") in place of marks. Neither is followed by a bare 3-4 digit
token, so the pattern below naturally skips them — same philosophy as
faisalabad.py, no special-casing needed.

Known edge case (rare, does not corrupt data): a handful of rows (6 out
of 87,652 sampled — ~0.007%) carry an extra remark line like
"RCD Attested Admission Form is Required" that pushes the right-hand
column's roll number onto its own separate output line, decoupling it
from that candidate's name/marks. Without a length cap, the non-greedy
name group would backtrack across the column gap and merge two
candidates into one garbled record. Capping the name group at 30 chars
(real names topped out at 25 chars in the full sample) makes those
specific matches fail to form at all, so the affected candidate is
skipped rather than corrupted. This trades ~6 dropped rows out of 87.6k
for zero corrupted rows — verified by diffing matches with/without the
cap on the full document.

LINE-BREAK HANDLING (why the name is single-line but the separator is not)
-------------------------------------------------------------------------
It is tempting to "fix" wrapped rows by letting the name group span line
breaks (i.e. `[A-Z\.\s]` instead of `[A-Z\. ]`). Measured against the full
1043-page gazette, that is wrong on both counts:

  1. Names in this gazette NEVER wrap. Every candidate's name is emitted
     on one line. What wraps is the Result column (subject-code lists),
     and — the actual bug — the marks value, which poppler often places
     one or two lines BELOW its own name when row heights vary:

         100220 RABIA IRSHAD

                                     1138

  2. Letting the name cross "\n" therefore never recovers a real name; it
     only lets the lazy group backtrack over the blank gutter and stitch
     TWO candidates together. On a 149-page sample it produced exactly 4
     such matches, all corrupt, e.g.
     name='LARAIB\n\n        ASMA TAHIR' — two different students.

So the name class stays single-line (`[A-Z\. ]`) to keep that corruption
impossible, and the SEPARATOR between name and marks is what was widened
to cross up to two "\n". Keeping the spaces in the separator (rather than
in the name class) also matters because it stops leading/trailing padding
from eating into the 30-char name cap described above.

Measured on the full 1043-page document: 67,408 -> 69,005 distinct rolls
(+1,597, +2.37%), with zero records changed, zero lost, and zero names
containing a line break. The change is strictly additive.

Still NOT recovered (known, unfixed — these need coordinate-based parsing
like sahiwal.py, not a better regex):
  - Rows where a diagonal watermark injects stray characters between the
    name and the marks ("100145 IQRA RIAZ  o 758", "100151 KANEEZ FATIMA
    0 932"). The name class rejects the lowercase/digit noise, so the row
    is skipped rather than mis-parsed.
  - Blocks where poppler's reading order drops the roll numbers entirely,
    leaving bare names and bare marks in separate runs (see page 16).
"""
import re

BOARD_CONFIG = {
    "match_names": ["multan"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})[ ]+"
        # Name stays SINGLE-LINE on purpose — see LINE-BREAK HANDLING above.
        r"(?P<name>[A-Z][A-Z\. ]{0,29}?)"
        # Separator, deliberately NOT part of the name: spaces, optionally
        # crossing up to two line breaks, so a marks value that poppler
        # pushed onto a later line still binds to its own candidate.
        r"[ ]*(?:\n[ ]*){0,2}"
        r"(?P<marks>\d{3,4})\b"
    ),
    "fields": ["roll_number", "name", "marks"],
}

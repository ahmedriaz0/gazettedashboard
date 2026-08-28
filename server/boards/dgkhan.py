r"""
BISE D.G. Khan (Dera Ghazi Khan) gazette format.

Sample raw line (via `pdftotext -layout`), two columns per page:
    200017 BUSHRA ANAM                                            972
    200003 ALEESHA BATOOL                               668  GOVT.GIRLS HIGH SCHOOL AALI WALA (DERA GHAZI KHAN)

Fields available: roll_number, name, marks. Same pass/fail convention as
Faisalabad/Bahawalpur: failed students show subject codes instead of a
number, which "\d{3,4}" naturally excludes.

This is the messiest of the boards sampled for this project:

1. An institute-name banner line ("GOVT.GIRLS HIGH SCHOOL ... (DERA GHAZI
   KHAN)") is interleaved between student rows every time the roster
   switches institute, on both columns independently, so it can appear
   mid-block rather than only between blocks. `page_marker: "Roll No"`
   (the gazette's column header) at least keeps this pattern from ever
   running on the front-matter statistical pages.
2. Long names/subject lists wrap to a second output line the same way as
   Bahawalpur, dropping that record rather than corrupting it.
3. A watermark occasionally injects a stray single/double letter or digit
   right at the start of a line (e.g. "m 200020 FARKHANDA BIBI", "o DERA
   GHAZI KHAN") which usually just breaks that one row's match (roll
   number must be the first thing matched) rather than polluting a
   neighboring one.

Net effect: ~49.8k clean single-line rows out of ~91k total candidates
(pass+fail+absent) on this board — treat this module as best-effort, not
complete. As with Bahawalpur, the "name" group only allows a single
literal space between words so the lazy match can't bridge across a
column gap and stitch two students' data together.
"""
import re

BOARD_CONFIG = {
    "match_names": ["dg khan", "dera ghazi khan", "dgkhan", "d.g khan", "d.g. khan"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})[ \t]+(?P<name>[A-Z][A-Z.]*(?: [A-Z][A-Z.]*)*)[ \t]+(?P<marks>\d{3,4})(?!\d)"
    ),
    "fields": ["roll_number", "name", "marks"],
    "page_marker": "Roll No",
}

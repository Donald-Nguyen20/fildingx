"""core/doc_naming.py — read a VP1 document name without asking a model.

Plant filenames follow a published convention:

    VP1-<Unit>-<Scope>-<Discipline>-<System>-<Number>[-<Rev>] <Title>.<ext>
    e.g. VP1-C-L3-G-HNC-50056-Rev.D Operation Manual for IDF.pdf

Everything before the title is recorded fact, not inference: the discipline
letter states which trade the document belongs to, and the number states which
document it *is*. Asking a language model to guess that back out of the text is
slower, costs money, needs a network, and -- measured over 40 real files --
answers differently on each run. Parsing it is exact, instant and repeatable.

What a model is still needed for is the part the name does not carry: what the
document is actually *about*. "Electrical" is in the name; "Cable Schedule" is
not. So this module owns the facts and leaves the judgement to the caller.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass

# The scope field is usually a lot (L1..L4) but the EPC contractor's own
# documents put a word there instead, so it cannot be pinned to "L" + digit.
# Discipline is normally one letter; a handful of names use two (PM). System
# codes run from one character (H) to six. All three widths come from measuring
# the real library rather than from the naming standard, which documents only
# the common case.
_DOC_ID = re.compile(
    r"VP1[-_ ]([A-Z0-9]{1,4})"      # unit
    r"[-_ ]((?:L\d)|[A-Z]{2,4})"    # scope: lot, or a contractor word
    r"[-_ ]([A-Z]{1,2})"            # discipline
    r"[-_ ]([A-Z0-9]{1,6})"         # system code
    r"[-_ ](\d{3,6})",              # document number
    re.IGNORECASE,
)

# Two revision spellings live side by side in the library: an explicit
# "Rev.D" / "_Rev B" / "REV 0", and a bare letter hung straight off the
# document number ("...-GCB-20001-D Operation and Maintenance..."). The bare
# form is why a Rev-only pattern reported "no revision" for whole document sets.
#
# The guard in front of REV is a lookbehind rather than \b because underscore
# counts as a word character: against "..._Rev.B.pdf" there is no word boundary
# at all, so \bREV never matched the underscore-separated spelling.
_REV_EXPLICIT = re.compile(r"(?<![A-Z])REV\.?\s*([A-Z]{1,2}\d{0,2}|\d{1,2})\b", re.IGNORECASE)
_REV_BARE = re.compile(r"^[-_ ]([A-Z]{1,2}\d{0,2}|\d{1,2})(?=[\s_.]|$)", re.IGNORECASE)

DISCIPLINES = {
    "A":  "Architectural",
    "C":  "Civil / Structural",
    "E":  "Electrical",
    "F":  "Commissioning / Testing",
    "G":  "General (O&M, Manual)",
    "I":  "Instrumentation & Control",
    "M":  "Mechanical",
    "P":  "Piping",
    "Q":  "Quality",
    "R":  "Process / PFD",
    "PM": "Project Management",
}

LOTS = {
    "L1": "Boiler & Fuel",
    "L2": "Turbine & Generator",
    "L3": "Balance of Plant",
    "L4": "Civil / Common",
}

# Fallback for the ~12% of names outside the convention -- vendor manuals,
# training decks, operator notes. Order matters: the first match wins, so the
# more specific phrases come before the generic ones.
_KEYWORD_RULES = (
    ("P&ID / Diagram",       r"p\s*&\s*i\s*d|piping and instrument|single line|\bsld\b|schematic|block diagram|\bdiagram\b"),
    ("Drawing",              r"\bdrawing|\bdwg\b|\blayout\b|general arrangement|plan view|isometric"),
    ("O&M Manual",           r"o\s*&\s*m|operation and maintenance|instruction manual|user manual|\bmanual\b"),
    ("Operation",            r"^operation|operating|\bstart-?up\b|shut-?down"),
    ("Maintenance",          r"^maintenance|overhaul|\brepair\b|replenish|lubricat|greasing"),
    ("Commissioning / Test", r"commission|\btests?\b|testing|inspection|\bitp\b|trial run|pre-?operation"),
    ("Procedure",            r"procedure|method statement|work instruction|guideline|\bsop\b"),
    ("Datasheet / Spec",     r"data\s*sheet|datasheet|specification|\bspecs?\b"),
    ("Report / Record",      r"\breports?\b|certificate|\brecord|log\s*sheet|minutes|punch"),
    ("List / Schedule",      r"\blists?\b|schedule|register|\bindex\b|bill of material|\bbom\b"),
    ("Calculation",          r"calculat|sizing|\banalysis\b|\bstudy\b|\bcalc\b"),
    ("Training",             r"training|course|lesson|classroom|\bojt\b|presentation"),
)
_KEYWORDS = tuple((label, re.compile(rx, re.IGNORECASE)) for label, rx in _KEYWORD_RULES)

UNCLASSIFIED = "Other / Unclassified"


@dataclass(frozen=True)
class DocName:
    """The convention fields of one filename. Absent fields are empty strings."""
    unit:       str
    scope:      str
    discipline: str
    system:     str
    number:     str
    revision:   str

    @property
    def doc_id(self) -> str:
        """The document's identity, revision excluded -- what makes two files
        two copies of one document rather than two documents."""
        return "-".join((f"VP1-{self.unit}", self.scope, self.discipline,
                         self.system, self.number)).upper()

    @property
    def discipline_label(self) -> str:
        return DISCIPLINES.get(self.discipline.upper(), "")

    @property
    def lot_label(self) -> str:
        return LOTS.get(self.scope.upper(), "")


def parse(filename: str) -> DocName | None:
    """Pull the convention fields out of a filename, or None if it has none."""
    match = _DOC_ID.search(filename)
    if not match:
        return None
    unit, scope, discipline, system, number = match.groups()
    return DocName(
        unit=unit.upper(), scope=scope.upper(), discipline=discipline.upper(),
        system=system.upper(), number=number,
        revision=_find_revision(filename, match.end()),
    )


def _find_revision(filename: str, after: int) -> str:
    """Read the revision code, whichever of the two spellings was used."""
    tail = filename[after:]
    bare = _REV_BARE.match(tail)
    if bare:
        return bare.group(1).upper()
    explicit = _REV_EXPLICIT.search(tail)
    if explicit:
        return explicit.group(1).upper()
    return ""


def keyword_category(filename: str) -> str:
    """Classify a filename that does not follow the convention. May return ''."""
    for label, pattern in _KEYWORDS:
        if pattern.search(filename):
            return label
    return ""


def classify(filename: str) -> str:
    """Best offline label for one file. Never fails; may return UNCLASSIFIED.

    The discipline letter is preferred over the words in the title because it
    is stated rather than guessed -- but it is coarse, so a name carrying no
    convention falls back to what its wording suggests.
    """
    doc = parse(filename)
    if doc and doc.discipline_label:
        return doc.discipline_label
    return keyword_category(filename) or UNCLASSIFIED


def duplicate_sets(filenames: list[str]) -> tuple[list[dict], list[dict]]:
    """Split repeated documents into the two cases that need different actions.

    A search result routinely shows one document more than once, but for two
    unrelated reasons, and lumping them together -- as a single "Multiple
    Revisions" heading did -- hides which problem is on screen:

      * several revisions of one document (Rev.D beside Rev.E), where the
        question is which one is current;
      * one identical file stored in several folders, where there is no
        question of currency at all, only of which copy to open.

    Returns (revisions, copies), each a list of
    {"base": <document id>, "files": [(filename, index), ...]}.
    """
    by_doc:  dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    by_name: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)

    for index, name in enumerate(filenames):
        doc = parse(name)
        if doc:
            by_doc[doc.doc_id].append((name, index))
        else:
            # No document number to group on, but an exact repeat of a filename
            # is a duplicate by inspection -- no model required to see it.
            by_name[name.strip().lower()].append((name, index))

    revisions: list[dict] = []
    copies:    list[dict] = []

    for doc_id, entries in by_doc.items():
        if len(entries) < 2:
            continue
        distinct = {name.strip().lower() for name, _ in entries}
        target = revisions if len(distinct) > 1 else copies
        target.append({"base": doc_id, "files": entries})

    for _key, entries in by_name.items():
        if len(entries) > 1:
            copies.append({"base": entries[0][0], "files": entries})

    revisions.sort(key=lambda d: d["base"])
    copies.sort(key=lambda d: d["base"])
    return revisions, copies

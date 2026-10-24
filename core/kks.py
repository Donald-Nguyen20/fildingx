"""
core/kks.py — the KKS equipment-tag pattern, shared by Create DB and DB Search.

Create DB (core/create_index_v3.py) stores every tag it finds in the kks_tags
table; DB Search looks a typed tag up there. Both have to read a tag the same
way, and this module is Qt-free so the search tab can use it without importing
the indexer window.
"""
import re

# A KKS tag with its unit prefix -- 00 (common plant), 10 (unit 1) or 20
# (unit 2): "10HAC10", "10HAC10 AA001", "20LAB30-CP001", "10HAC10AA001 XB01".
# KKS has no I or O, so they are left out of the letter class, and only upper
# case counts, which keeps ordinary words out. A tag written without the unit
# prefix ("HBK11CP002") is not picked up.
#
# Measured over the 8,082 documents in Databasev3, a looser one-or-two digit
# prefix finds 873,410 tags, 97.4% of them on 00/10/20. Nearly all the rest is
# "_0LAC30AP010" / "*0LAB11", the vendors' shorthand for "the same tag on
# either unit" -- not tag 00, so not read as one -- and the remainder is panel
# names, curve numbers and dates ("2DCP10", "1STP42", "17JUL15").
_L = '[A-HJ-NP-Z]'
KKS_RE = re.compile(
    rf'(?<![A-Z0-9])(?:00|10|20){_L}{{3}}\d{{2}}'
    rf'(?:[ \-]?{_L}{{2}}\d{{3}})?'
    rf'(?:[ \-]?{_L}{{2}}\d{{2}})?'
    r'(?![A-Z0-9])'
)
_SEP = re.compile(r'[ \-]')


def norm(tag: str) -> str:
    """The form kks_tags.tag_norm holds: upper case, spaces and dashes out."""
    return _SEP.sub('', tag).upper()


# What a reader types for a tag on whichever unit: "MAW85 AA001", "MAW85".
_UNITLESS_RE = re.compile(
    rf'{_L}{{3}}\d{{2}}(?:[ \-]?{_L}{{2}}\d{{3}})?(?:[ \-]?{_L}{{2}}\d{{2}})?')
UNITS = ('00', '10', '20')


def search_globs(text: str) -> list:
    """GLOB patterns on kks_tags.tag_norm that a typed tag stands for; [] when
    the whole of text is not one tag.

    "10hac10 aa001" and "10HAC10-AA001" both give ["10HAC10AA001*"], so a tag
    is found however each document happens to space it, and so is every longer
    tag it begins ("10HAC10" finds "10HAC10AA001"). Typed without its unit
    prefix ("MAW85 AA001") it stands for the tag on every unit: one pattern per
    prefix rather than a "[012]0" class, so each lookup still uses the
    tag_norm index.
    """
    text = (text or '').strip().upper()
    if KKS_RE.fullmatch(text):
        return [norm(text) + '*']
    if _UNITLESS_RE.fullmatch(text):
        return [unit + norm(text) + '*' for unit in UNITS]
    return []


# ── OCR misreads of a tag ────────────────────────────────────────────────────
# OCR swaps digits and look-alike letters: "1OHLV51" for 10HLV51, "LOPGE87 CT501"
# for 10PGE87 CT501, "CT5O1" for CT501. KKS has no I or O and a unit prefix is
# 00, 10 or 20, so a candidate is rewritten only when swapping back gives a tag
# KKS_RE accepts. Measured on 207,000 pages of clean text layer, a looser first
# version also turned numbers into tags ("2065630" -> "20GSG30") and joined
# separate words ("0 DSTL14"), hence the guards:
#   - the unit prefix is two adjacent characters, read as digits only from O, I,
#     l, L and | (D is a real KKS letter, so it is never read as 0);
#   - the closing two digits are real digits, and the three letters between
#     hold at least two real letters;
#   - with no real digit in the unit prefix ("LOCAL10") it must be followed by
#     an equipment part ("LOPGE87 CT501") to be taken for a tag at all.
# A vertical label split by OCR ("I OMAW85") is left to the drawing pass, which
# sees where the pieces sit.
_TO_DIGIT = str.maketrans({'O': '0', 'Q': '0', 'D': '0', 'I': '1', 'L': '1', 'l': '1',
                           '|': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6'})
_TO_LETTER = str.maketrans({'5': 'S', '8': 'B', '2': 'Z', '6': 'G'})
_FUZZY_TAG = re.compile(
    r'(?<![A-Za-z0-9])([0-9OIlL|]{2})([A-Z0-9]{3})(\d{2})'
    r'(?:([ \-])([A-Z0-9]{2})([0-9OQDIlLSBZG]{3}))?(?![A-Za-z0-9])')


def fix_ocr_text(text: str) -> str:
    """OCR text with misread tags put right, everything else untouched."""
    def fix(m):
        unit, letters = m.group(1), m.group(2)
        if sum(c.isalpha() for c in letters) < 2:
            return m.group(0)
        system = unit.translate(_TO_DIGIT) + letters.translate(_TO_LETTER) + m.group(3)
        if not KKS_RE.fullmatch(system):
            return m.group(0)
        comp_ok = False
        rest = m.group(0)[m.end(3) - m.start():]
        if m.group(5):
            comp = m.group(5).translate(_TO_LETTER) + m.group(6).translate(_TO_DIGIT)
            if KKS_RE.fullmatch(system + m.group(4) + comp):
                comp_ok, rest = True, m.group(4) + comp
        if not any(c.isdigit() for c in unit) and not comp_ok:
            return m.group(0)
        return system + rest
    return _FUZZY_TAG.sub(fix, text or '')


# ── Tags on a drawing, from OCR boxes ────────────────────────────────────────
# A P&ID writes a tag as two labels: the system part over the equipment part,
# or, standing vertically, the system part left of it ("10MAW85" | "AA001").
# OCR reads each label as its own box, so the tag is put back together from
# where the boxes sit. A box is a single label here, so it is read as a tag
# part even with no real digit in its unit prefix ("I OMAW85", a vertical
# label) -- the context fix_ocr_text has to do without.
# A pipe size label ("DN100") has an equipment part's shape and sits beside the
# tags on a P&ID; on the A1 test sheet it made "10MAW85 DN100".
_PIPE_SIZE = 'DN'
_SYS_PART = re.compile(rf'(?:00|10|20){_L}{{3}}\d{{2}}')
_COMP_PART = re.compile(rf'{_L}{{2}}\d{{3}}')
_STRIP = re.compile(r'[\s\-]')


def fix_ocr_part(text: str):
    """A drawing label as a tag part -- '10MAW85', 'AA001' or '10MAW85 AA001' --
    with misreads put right, or None when it is not one."""
    t = _STRIP.sub('', text or '').upper()

    def system(s):
        c = s[:2].translate(_TO_DIGIT) + s[2:5].translate(_TO_LETTER) + s[5:].translate(_TO_DIGIT)
        return c if _SYS_PART.fullmatch(c) else None

    def comp(s):
        c = s[:2].translate(_TO_LETTER) + s[2:].translate(_TO_DIGIT)
        return c if _COMP_PART.fullmatch(c) else None

    if len(t) == 7:
        return system(t)
    if len(t) == 5:
        return comp(t)
    if len(t) == 12 and system(t[:7]) and comp(t[7:]):
        return f"{system(t[:7])} {comp(t[7:])}"
    return None


def _overlap(a0, a1, b0, b1):
    return max(0, min(a1, b1) - max(a0, b0)) / max(1, min(a1 - a0, b1 - b0))


def pair_tags(boxes) -> list:
    """Full tags read off a drawing: sorted unique 'SYSTEM EQUIPMENT' strings.

    boxes are OCR boxes (x0, y0, x1, y1, text, score) in one coordinate frame.
    An equipment part takes the nearest system part beside it -- to its left
    for vertical labels, above it for horizontal ones -- within 2.5 times its
    own width (or height). Measured on an A1 P&ID: 70 of 86 tags at 300 dpi,
    85 at 600, against 58 without the misread fix."""
    def vertical(b):
        return (b[3] - b[1]) > 1.5 * (b[2] - b[0])

    tags, systems, comps = set(), [], []
    for b in boxes:
        part = fix_ocr_part(b[4])
        if part is None:
            # a whole tag inside a longer line ("VALVE 10HAC10 AA001 OPEN")
            for m in KKS_RE.finditer(fix_ocr_text(b[4])):
                n = norm(m.group(0))
                if len(n) >= 12 and n[7:9] != _PIPE_SIZE:
                    tags.add(f"{n[:7]} {n[7:12]}")
        elif len(part) != 7 and part[-5:-3] == _PIPE_SIZE:
            continue
        elif len(part) == 7:
            systems.append((part, b))
        elif len(part) == 5:
            comps.append((part, b))
        else:
            tags.add(part)
    for part, c in comps:
        best = None
        for spart, s in systems:
            if vertical(c) and vertical(s):
                w = c[2] - c[0]
                gap = c[0] - s[2]
                ok = -w < gap < 2.5 * w and _overlap(s[1], s[3], c[1], c[3]) > 0.4
            elif not vertical(c) and not vertical(s):
                h = c[3] - c[1]
                gap = c[1] - s[3]
                ok = -h < gap < 2.5 * h and _overlap(s[0], s[2], c[0], c[2]) > 0.4
            else:
                ok = False
            if ok and (best is None or gap < best[0]):
                best = (gap, spart)
        if best:
            tags.add(f"{best[1]} {part}")
    return sorted(tags)

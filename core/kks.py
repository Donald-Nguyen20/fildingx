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


def search_key(text: str):
    """text as a normalised tag when the whole of it is one, else None.

    "10hac10 aa001" and "10HAC10-AA001" both give "10HAC10AA001", so a tag is
    found however each document happens to space it.
    """
    text = (text or '').strip().upper()
    return norm(text) if KKS_RE.fullmatch(text) else None

"""logic_query.py — read-only lookup over the Toshiba DCS engineering databases.

Companion to db_query.py. That one answers "which document mentions this";
this one answers "what makes this signal go true" -- the control logic itself,
read from the CAD databases the logic was designed in (one SQLite file per
controller) rather than from the text layer of a logic-diagram PDF.

Usage:
    python logic_query.py cpus   <dcs_folder>
    python logic_query.py find   <dcs_folder> <text> [limit]
    python logic_query.py why    <dcs_folder> <signal|ref>
    python logic_query.py tree   <dcs_folder> <signal|ref> [depth]
    python logic_query.py trace  <dcs_folder> <signal|ref> [depth]

A signal is addressed by name. When one name exists in several places the
answer carries a `ref` per location -- "<db file>|<sheet>|<net>" -- which any
command accepts in place of the name to pin the lookup to one of them.

Every result is a JSON object on stdout. Failures are {"error": ...} with a
non-zero exit, so a caller never has to parse prose to find out it got nothing.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from paths import APP_DIR                                    # noqa: E402
from ui.dcs_logic import cond_tree, dbreader                 # noqa: E402
from ui.dcs_logic import project_index, sheet_render         # noqa: E402
from ui.dcs_logic import signal_graph                        # noqa: E402

MAX_DEPTH = 40
MAX_EDGES = 150
# A plant-wide signal such as MFT is read on thirty-odd sheets. Listing them all
# buries the answer, so the caller gets a handful and a count of the rest.
MAX_ALSO_AT = 8

# cond_tree renders its formulas for a Vietnamese UI. Translated here rather
# than in the module so ui/dcs_logic stays a verbatim copy of its upstream.
# Longest first: "KHÔNG-VÀ" must not be rewritten as "KHÔNG-" + "AND".
_FORMULA_WORDS = [
    ("KHÔNG-VÀ(", "NAND("), ("KHÔNG-HOẶC(", "NOR("),
    ("HOẶC(", "OR("), ("VÀ(", "AND("), ("đảo(", "NOT("),
    ("chốt: SET=", "LATCH: SET="), ("hằng số = ", "CONST = "),
    ("≥ ngưỡng", "≥ threshold"), ("≤ ngưỡng", "≤ threshold"),
    ("so sánh", "compare"), ("(đệm)", "(buffer)"), ("(trễ)", "(delay)"),
    ("qua ", "via "),
]
# formula() also returns the operator on its own, without the bracket that the
# substitutions above key on. Anything not listed is a block name; leave it be.
_OP_WORDS = {"VÀ": "AND", "HOẶC": "OR", "KHÔNG-VÀ": "NAND", "KHÔNG-HOẶC": "NOR",
             "đảo": "NOT", "chốt SR": "SR latch", "hằng số": "constant",
             "đệm": "buffer", "trễ": "delay", "so sánh": "compare"}
_NOTE_WORDS = {"gioi han do sau": "depth limit reached", "vong lap": "loop"}
_LEAF_KINDS = {
    "cross": "cross-reference", "source": "source", "opaque": "unresolved",
    "const-empty": "unconnected",
}


def _english(text: str) -> str:
    """Formula text as the rest of this program speaks it."""
    for vi, en in _FORMULA_WORDS:
        text = text.replace(vi, en)
    return text


# ── locating things ───────────────────────────────────────────────────────

def _dcs_dbs(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        raise ValueError("Not a folder: %s" % folder)
    dbs = sorted(glob.glob(os.path.join(folder, "*.db")))
    if not dbs:
        raise ValueError("No .db file in %s" % folder)
    return dbs


def _index_for(dbs: list[str], folder: str) -> str:
    """Signal index for this folder, kept beside the app.

    Named after a hash of the folder so a second unit's databases get their own
    index instead of evicting this one on every switch, and kept out of the DCS
    folder itself, which holds the design masters and is not ours to write to.
    """
    tag = hashlib.sha1(os.path.abspath(folder).lower().encode()).hexdigest()[:8]
    out = os.path.join(APP_DIR, "dcs_index_%s.db" % tag)
    return project_index.ensure(dbs, out_path=out)


def _ref(db: str, sheet, net: str) -> str:
    return "%s|%s|%s" % (os.path.basename(db), sheet, net)


def _cpu_paths(dbs: list[str]) -> dict:
    """{cpu number: file} -- what signal_graph needs to cross the C-NET."""
    out = {}
    for p in dbs:
        try:
            no = dbreader.db_meta(p).get("cpuno")
        except Exception:
            continue
        if no is not None:
            out[no] = p
    return out


def _hit(row: tuple) -> dict:
    """One row of project_index.find/locate_full as a location."""
    name, cpuname, cpuno, sheetlbl, db, sheet, net = row
    return {"name": name, "cpu": cpuname, "cpu_no": cpuno, "sheet": sheetlbl,
            "ref": _ref(db, sheet, net), "_db": db, "_sheet": sheet, "_net": net}


def _resolve(folder: str, target: str) -> dict:
    """A name or a ref -> the one place to read. Raises with suggestions."""
    dbs = _dcs_dbs(folder)
    if "|" in target:
        fname, sheet, net = target.split("|", 2)
        db = os.path.join(folder, fname)
        if not os.path.exists(db):
            raise LookupError("No such database in this folder: %s" % fname)
        return {"name": signal_graph._name_of(db, int(sheet), net) or net,
                "ref": target, "_db": db, "_sheet": int(sheet), "_net": net,
                "_dbs": dbs, "also_at": [], "also_at_omitted": 0}

    idx = _index_for(dbs, folder)
    rows = [(target, r[0], r[1], r[2], r[3], r[4], r[5])
            for r in project_index.locate_full(target, out_path=idx)]
    if not rows:
        raise LookupError(json.dumps(
            {"error": "No signal is named exactly %r." % target,
             "did_you_mean": _suggest(target, idx)}, ensure_ascii=False))
    hits = [_hit(r) for r in rows]
    first = dict(hits[0])
    first["_dbs"] = dbs
    rest = [_public(h) for h in hits[1:]]
    first["also_at"] = rest[:MAX_ALSO_AT]
    first["also_at_omitted"] = max(0, len(rest) - MAX_ALSO_AT)
    return first


def _public(hit: dict) -> dict:
    return {k: v for k, v in hit.items() if not k.startswith("_")}


def _where(at: dict) -> dict:
    """The location fields every command repeats back to its caller."""
    return {"signal": at["name"], "ref": at["ref"], "cpu": at.get("cpu"),
            "sheet": at.get("sheet"), "also_at": at["also_at"],
            "also_at_omitted": at["also_at_omitted"]}


def _suggest(target: str, idx: str) -> list:
    """Nearest names to one that missed.

    The whole phrase first; failing that the longest word in it, since an
    operator's wording rarely matches the drawing's ("all CWP running" against
    "ALL CWP RUN") while one distinctive word usually does.
    """
    for query in _search_terms(target):
        rows = project_index.find(query, limit=10, out_path=idx)
        if rows:
            return [_public(_hit(r)) for r in rows]
    return []


def _search_terms(target: str) -> list:
    words = sorted((w for w in target.split() if len(w) > 2), key=len, reverse=True)
    return [target] + words[:3]


# ── the numbers the drawing sets ──────────────────────────────────────────
#
# A tree that says "COMPARE >=" and "through a timer" is structurally right and
# operationally useless: the question behind it is always "at what value" and
# "after how long". Both are in the databases, as block parameters, and the
# vendor's macro manual (6F6S0280, Control Logic Programming Manual) states what
# each parameter slot holds:
#
#   DI - Delay Initiation (T:para / R:disp)   2 = delay time T1, in seconds
#   H/ - Signal Monitor (High) (S & R:para)   2 = set S1, 3 = reset R1, 4 = unit
#
# Every one of those blocks also exists in a "T:input" / "S & R:input" variant
# where the value arrives on a wire and the parameter slots hold nothing that
# means anything. Printing those would put a confident wrong figure on a plant
# document, so the two sets below are built by reading the ":para" marker out of
# the macro catalogue -- not by listing codes by hand, which would quietly rot
# the first time a block is added.

_PARAM_CACHE: dict = {}
_CODE_SETS = None


def _code_sets() -> tuple:
    """(timers, comparators, all pass-through blocks), by macro code."""
    global _CODE_SETS
    if _CODE_SETS is None:
        timers, comparators = set(), set()
        try:
            catalogue = sheet_render._macro_pins()
        except Exception:
            catalogue = {}
        for spec in catalogue.values():
            if not isinstance(spec, dict):
                continue
            code = (spec.get("macrocode") or "").upper()
            name = spec.get("name") or ""
            if not code:
                continue
            if "T:para" in name:
                timers.add(code)
            if "S & R:para" in name:
                comparators.add(code)
        passes = {c.upper() for c, s in cond_tree._sem().items()
                  if isinstance(s, dict) and s.get("op") == "PASS"}
        _CODE_SETS = (timers, comparators, passes)
    return _CODE_SETS


def _sheet_params(db: str, sheet) -> dict:
    """{block: {parameter number: value}} for one sheet, read once."""
    key = (db, sheet)
    if key not in _PARAM_CACHE:
        found: dict = {}
        try:
            cur = dbreader.connect(db).cursor()
            for bid, pno, val in cur.execute(
                    "SELECT p.BLOCK_ID,p.PARAMNO,p.PARAMVALUE FROM CAD_BLOCK_PARAM p "
                    "JOIN CAD_BLOCK b ON b.BLOCK_ID=p.BLOCK_ID WHERE b.ID=?", (sheet,)):
                found.setdefault(bid, {})[str(pno)] = dbreader._clean(val)
        except Exception:
            found = {}
        _PARAM_CACHE[key] = found
    return _PARAM_CACHE[key]


def _threshold(producer: dict, params: dict) -> str:
    """A comparator's setting, worded as the drawing sets it."""
    _timers, comparators, _passes = _code_sets()
    if (producer.get("code") or "").upper() not in comparators:
        return ""
    slots = params.get(producer.get("bid")) or {}
    setting, reset, unit = slots.get("2", ""), slots.get("3", ""), slots.get("4", "")
    if not setting:
        return ""
    unit = "" if unit in ("", "-") else " " + unit
    # Set and reset differing is a deadband, not a typo: between the two the
    # output holds its last state. Quoting one figure would hide that.
    if reset and reset != setting:
        return "%s%s, reset %s" % (setting, unit, reset)
    return "%s%s" % (setting, unit)


def _delays(producers: dict, params: dict, net: str, count: int) -> list:
    """The setting of each timer folded away above a node, in `via` order.

    cond_tree walks straight through a pass-through block and keeps only its
    name, so the block -- and its setting -- is no longer on the node. It is
    still reachable: the pin the parent read is that block's output, so
    following producers back from there re-walks exactly what was folded.
    Blocks that carry no parameter time still take their slot, so that what
    comes back stays aligned with the names already in `via`.
    """
    timers, _comparators, passes = _code_sets()
    out: list = []
    seen: set = set()
    while net and net not in seen and len(out) < count:
        seen.add(net)
        producer = producers.get(net)
        code = ((producer or {}).get("code") or "").upper()
        if not producer or code not in passes:
            break
        slots = params.get(producer.get("bid")) or {}
        out.append(slots.get("2", "") if code in timers else "")
        feeds = [n for (n, _neg) in producer.get("ins") or [] if n]
        if not feeds:
            break
        net = feeds[0]
    return out


def _annotate(node: dict, pin_net=None) -> None:
    """Attach settings to a built tree, in place, before it is rendered."""
    db, sheet = node.get("db"), node.get("sheet")
    if not db or sheet is None:
        return
    try:
        producers = cond_tree._producers(db, sheet)
        params = _sheet_params(db, sheet)
    except Exception:
        return
    if node.get("via") and pin_net:
        node["_delays"] = _delays(producers, params, pin_net, len(node["via"]))
    own = producers.get(node.get("net")) or {}
    if node.get("type") == "cmp":
        setting = _threshold(own, params)
        if setting:
            node["_setpoint"] = setting
    feeds = own.get("ins") or []
    for i, child in enumerate(node.get("children") or []):
        _annotate(child, feeds[i][0] if i < len(feeds) else None)


# ── rendering ─────────────────────────────────────────────────────────────

def _render(node: dict, out: list, depth: int = 0) -> None:
    neg = "NOT " if node.get("neg") else ""
    kind = node["type"]
    if kind == "gate":
        head = neg + node["op"]
        if node["op"] == "SR":
            head += " (priority=%s)" % node.get("priority", "reset")
    elif kind == "const":
        head = "CONST=%d" % node.get("val", 0)
    elif kind == "cmp":
        head = "%sCOMPARE %s" % (neg, node.get("rel", ""))
    elif kind == "opaque":
        head = "%svia %s" % (neg, node.get("block", "?"))
    else:
        head = neg + _LEAF_KINDS.get(node.get("kind", ""), node.get("kind", "leaf"))
    line = "%s%s  %s" % ("  " * depth, head, node.get("label") or node.get("net") or "")
    setting = node.get("_setpoint")
    if setting:
        line += "  [%s]" % setting
    note = _NOTE_WORDS.get(node.get("note", ""))
    if note:
        line += "  [%s]" % note
    via = node.get("via")
    if via:
        delays = node.get("_delays") or []
        line += "  (through %s)" % ", ".join(
            "%s %ss" % (v, delays[i]) if i < len(delays) and delays[i] else str(v)
            for i, v in enumerate(via))
    out.append(line.rstrip())
    for child in node.get("children", []):
        _render(child, out, depth + 1)


def _leaf_rows(tree: dict) -> list:
    seen, rows = set(), []
    for leaf in cond_tree.leaves(tree):
        label = leaf.get("label") or leaf.get("net") or ""
        key = (label, leaf.get("kind"))
        if key in seen:
            continue
        seen.add(key)
        row = {"signal": label, "kind": _LEAF_KINDS.get(leaf.get("kind", ""),
                                                        leaf.get("kind", "")),
               "sheet": leaf.get("sheetlbl"), "cpu_no": leaf.get("cpu"),
               "ref": _ref(leaf["db"], leaf["sheet"], leaf["net"])
                      if leaf.get("db") else ""}
        if leaf.get("_setpoint"):
            row["setpoint"] = leaf["_setpoint"]
        rows.append(row)
    return rows


# ── commands ──────────────────────────────────────────────────────────────

def cmd_cpus(folder: str) -> dict:
    out = []
    for p in _dcs_dbs(folder):
        try:
            meta = dbreader.db_meta(p)
        except Exception as e:
            out.append({"file": os.path.basename(p), "error": str(e)})
            continue
        out.append({"file": os.path.basename(p), "cpu_no": meta.get("cpuno"),
                    "cpu": meta.get("cpuname"), "project": meta.get("projname")})
    return {"folder": folder, "controllers": out}


def cmd_find(folder: str, text: str, limit: int = 40) -> dict:
    dbs = _dcs_dbs(folder)
    idx = _index_for(dbs, folder)
    rows = project_index.find(text, limit=limit, out_path=idx)
    hits = [{k: v for k, v in _hit(r).items() if not k.startswith("_")} for r in rows]
    return {"query": text, "count": len(hits), "matches": hits}


def cmd_why(folder: str, target: str) -> dict:
    at = _resolve(folder, target)
    text, op = cond_tree.formula(at["_db"], at["_sheet"], at["_net"])
    return dict(_where(at), cause=_english(text) or None,
                operator=_OP_WORDS.get(op, op),
                note=None if text else
                     "This net has no resolvable producer on its sheet -- it is an "
                     "input, a cross-reference, or a block whose semantics are unknown.")


def cmd_tree(folder: str, target: str, depth: int = 12) -> dict:
    at = _resolve(folder, target)
    depth = max(1, min(int(depth), MAX_DEPTH))
    tree = cond_tree.build(at["_db"], at["_sheet"], at["_net"], depth=depth)
    _annotate(tree, at["_net"])
    lines: list = []
    _render(tree, lines)
    return dict(_where(at), depth=depth, tree="\n".join(lines),
                inputs=_leaf_rows(tree))


def cmd_trace(folder: str, target: str, depth: int = 3,
              direction: str = "both") -> dict:
    at = _resolve(folder, target)
    depth = max(1, min(int(depth), 8))
    nodes, edges, start = signal_graph.trace_project(
        at["_db"], at["_sheet"], at["_net"], direction=direction, depth=depth,
        cpu_paths=_cpu_paths(at["_dbs"]))
    by_id = {n["id"]: n for n in nodes}

    def name(nid):
        n = by_id.get(nid) or {}
        return "%s [%s/%s]" % (n.get("label", "?"), n.get("cpu", "?"),
                               n.get("sheetlbl", "?"))

    lines = ["%s  ->  %s   (%s%s)" % (
        name(e["src"]), name(e["dst"]), e["kind"],
        ", " + str(e["block"]) if e.get("block") else "")
        for e in edges[:MAX_EDGES]]
    return dict(_where(at), direction=direction, depth=depth, nodes=len(nodes),
                edges=len(edges), truncated=len(edges) > MAX_EDGES,
                flow="\n".join(lines))


_COMMANDS = {"cpus": (1, cmd_cpus), "find": (2, cmd_find), "why": (2, cmd_why),
             "tree": (2, cmd_tree), "trace": (2, cmd_trace)}


def main() -> None:
    # Signal names come out of the plant's databases, not out of this program,
    # and json.dumps is called with ensure_ascii=False. Whatever encoding the
    # calling shell would have picked, one accented character in a drawing would
    # otherwise end the command with a traceback instead of an answer.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    if not args or args[0] not in _COMMANDS:
        _fail("Usage: logic_query.py <%s> <dcs_folder> [args]"
              % "|".join(_COMMANDS))
    cmd, rest = args[0], args[1:]
    need, fn = _COMMANDS[cmd]
    if len(rest) < need:
        _fail("%s needs %d argument(s), got %d" % (cmd, need, len(rest)))
    try:
        print(json.dumps(fn(*rest), ensure_ascii=False, indent=2))
    except LookupError as e:
        # _resolve already formatted this one, suggestions and all.
        msg = str(e)
        print(msg if msg.startswith("{") else
              json.dumps({"error": msg}, ensure_ascii=False, indent=2))
        sys.exit(1)
    except Exception as e:
        _fail("%s: %s" % (type(e).__name__, e))


def _fail(msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False, indent=2))
    sys.exit(1)


if __name__ == "__main__":
    main()
